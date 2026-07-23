#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Measure and enforce P1 long-document latency, RSS, and timeout baselines."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docmirror/configs/stability/performance_baseline.yaml"
_RESULT_PREFIX = "DOCMIRROR_PERF_RESULT="


def _load() -> dict[str, Any]:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}


def validate_manifest(data: dict[str, Any], *, require_approved: bool = False) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != "docmirror.performance_baseline.v1":
        errors.append("unexpected performance baseline schema_version")
    if require_approved and data.get("status") != "approved":
        errors.append("performance baseline status must be approved")
    cases = list(data.get("cases") or [])
    if len(cases) < 2:
        errors.append("at least two performance cases are required")
    workload_classes = {str(case.get("workload_class") or "") for case in cases}
    if not {"long_document", "table_dense"} <= workload_classes:
        errors.append("performance cases must cover long_document and table_dense workloads")
    for case in cases:
        case_id = str(case.get("id") or "<missing-id>")
        checksum = str(case.get("fixture_sha256") or "")
        if len(checksum) != 64:
            errors.append(f"{case_id}: invalid fixture_sha256")
        workload_class = str(case.get("workload_class") or "")
        minimum_pages = 20 if workload_class == "long_document" else 2
        if int(case.get("page_count") or 0) < minimum_pages:
            errors.append(f"{case_id}: page_count must be at least {minimum_pages} for {workload_class}")
        if not case.get("expected_document_type"):
            errors.append(f"{case_id}: expected_document_type is required")
        if int(case.get("repetitions") or 0) < 3:
            errors.append(f"{case_id}: at least three measured repetitions are required")
        if float(case.get("timeout_seconds") or 0) <= 0:
            errors.append(f"{case_id}: timeout_seconds must be positive")
        policy = case.get("parse_policy")
        if not isinstance(policy, dict) or not policy.get("doc_type_hint"):
            errors.append(f"{case_id}: explicit parse_policy.doc_type_hint is required")
        if require_approved:
            ceilings = case.get("ceilings") or {}
            for metric in ("p50_ms", "p95_ms", "peak_rss_mb"):
                if not isinstance(ceilings.get(metric), (int, float)) or float(ceilings[metric]) <= 0:
                    errors.append(f"{case_id}: approved ceiling {metric} must be positive")
    return errors


def _case(data: dict[str, Any], case_id: str) -> dict[str, Any]:
    for case in data.get("cases") or []:
        if str(case.get("id")) == case_id:
            return dict(case)
    raise KeyError(case_id)


def _rss_mb() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS reports bytes; Linux reports KiB.
    divisor = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
    return value / divisor


async def _run_one(case: dict[str, Any]) -> dict[str, Any]:
    from docmirror.input.entry.factory import PerceiveOptions, perceive_document
    from docmirror.input.entry.options import normalize_parse_policy

    fixture = ROOT / str(case["fixture"])
    actual_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    if actual_sha != case["fixture_sha256"]:
        raise ValueError(f"fixture checksum mismatch: {actual_sha}")
    policy = normalize_parse_policy(**dict(case["parse_policy"]))
    started = time.perf_counter()
    sealed = await perceive_document(
        fixture,
        PerceiveOptions(policy=policy, max_workers=int(case.get("workers") or 1)),
    )
    view = sealed.to_read_view()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "elapsed_ms": round(elapsed_ms, 3),
        "peak_rss_mb": round(_rss_mb(), 3),
        "document_type": view.entities.document_type,
        "page_count": view.page_count,
        "status": view.status.value,
        "fact_fingerprint": sealed.fact_fingerprint(),
    }


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _execute_child(case: dict[str, Any]) -> dict[str, Any]:
    timeout = float(case["timeout_seconds"])
    command = [sys.executable, str(Path(__file__).resolve()), "--_run-one", str(case["id"])]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"exceeded {timeout:.1f}s") from exc
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "benchmark child failed")
    line = next((item for item in completed.stdout.splitlines() if item.startswith(_RESULT_PREFIX)), "")
    if not line:
        raise RuntimeError("benchmark child emitted no structured result")
    return json.loads(line.removeprefix(_RESULT_PREFIX))


def _measure_case(case: dict[str, Any]) -> dict[str, Any]:
    for _ in range(int(case.get("warmups") or 0)):
        _execute_child(case)
    runs = [_execute_child(case) for _ in range(int(case["repetitions"]))]
    latencies = [float(run["elapsed_ms"]) for run in runs]
    fingerprints = {str(run["fact_fingerprint"]) for run in runs}
    for run in runs:
        if run["document_type"] != case["expected_document_type"]:
            raise ValueError(f"document_type={run['document_type']} expected={case['expected_document_type']}")
        if int(run["page_count"]) != int(case["page_count"]):
            raise ValueError(f"page_count={run['page_count']} expected={case['page_count']}")
        if run["status"] == "failure":
            raise ValueError("parse status is failure")
    return {
        "id": case["id"],
        "runs": runs,
        "p50_ms": round(_percentile(latencies, 0.50), 3),
        "p95_ms": round(_percentile(latencies, 0.95), 3),
        "peak_rss_mb": round(max(float(run["peak_rss_mb"]) for run in runs), 3),
        "timeout_seconds": float(case["timeout_seconds"]),
        "fact_deterministic": len(fingerprints) == 1,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--print-observed", action="store_true")
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--_run-one", dest="child_case", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    data = _load()
    if args.child_case:
        try:
            observed = asyncio.run(_run_one(_case(data, args.child_case)))
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(_RESULT_PREFIX + json.dumps(observed, ensure_ascii=False, sort_keys=True))
        return 0

    errors = validate_manifest(data, require_approved=args.require_approved)
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if args.manifest_only:
        print(f"Performance baseline manifest OK (status={data.get('status')})")
        return 0

    cases = list(data["cases"])
    if args.case_ids:
        selected = set(args.case_ids)
        known = {str(case["id"]) for case in cases}
        unknown = sorted(selected - known)
        if unknown:
            print(f"unknown performance case(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        cases = [case for case in cases if case["id"] in selected]

    observations: list[dict[str, Any]] = []
    for case in cases:
        try:
            observed = _measure_case(case)
        except Exception as exc:
            errors.append(f"{case['id']}: {exc}")
            continue
        observations.append(observed)
        if not observed["fact_deterministic"]:
            errors.append(f"{case['id']}: repeated fact fingerprints differ")
        if data.get("status") == "approved":
            ceilings = case["ceilings"]
            for metric in ("p50_ms", "p95_ms", "peak_rss_mb"):
                if float(observed[metric]) > float(ceilings[metric]):
                    errors.append(f"{case['id']}: {metric}={observed[metric]} exceeds ceiling={ceilings[metric]}")
    if args.print_observed or observations:
        print(
            json.dumps(
                {
                    "environment": {
                        "platform": platform.platform(),
                        "python": platform.python_version(),
                    },
                    "observations": observations,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    if errors:
        print("Performance/RSS baseline FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Performance/RSS baseline OK ({len(observations)} workload cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
