#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate or execute the mandatory P1 6+1 real-document Golden matrix."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docmirror/configs/stability/ga_6plus1.yaml"
ALLOWED_SOURCE_CLASSES = {"real", "desensitized_real"}
_OBSERVATION_PREFIX = "DOCMIRROR_GA_OBSERVATION="


def _load() -> dict[str, Any]:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}


def validate_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = str(data.get("status") or "")
    if status not in {"pending_baseline", "frozen"}:
        errors.append("status must be pending_baseline or frozen")
    if list(data.get("worker_matrix") or []) != [1, 2, 4]:
        errors.append("worker_matrix must be exactly [1, 2, 4]")
    if float(data.get("case_timeout_seconds") or 0) <= 0:
        errors.append("case_timeout_seconds must be positive")
    required = list(data.get("required_domains") or [])
    cases = list(data.get("cases") or [])
    domains = [str(case.get("domain") or "") for case in cases if isinstance(case, dict)]
    if len(required) != 7 or len(set(required)) != 7:
        errors.append("required_domains must contain exactly seven unique 6+1 domains")
    if sorted(domains) != sorted(required):
        errors.append(f"case domains do not exactly cover required_domains: {domains}")
    for case in cases:
        case_id = str(case.get("id") or "<missing-id>")
        if case.get("skip_if_fixture_missing") is not None:
            errors.append(f"{case_id}: GA case must not declare skip_if_fixture_missing")
        if case.get("source_class") not in ALLOWED_SOURCE_CLASSES:
            errors.append(f"{case_id}: source_class must be real or desensitized_real")
        checksum = str(case.get("fixture_sha256") or "")
        if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
            errors.append(f"{case_id}: invalid fixture_sha256")
        policy = case.get("parse_policy")
        if not isinstance(policy, dict) or not policy.get("doc_type_hint"):
            errors.append(f"{case_id}: explicit parse_policy.doc_type_hint is required")
        if not case.get("expected_document_type"):
            errors.append(f"{case_id}: expected_document_type is required")
        if not case.get("expected_fact_fingerprint"):
            errors.append(f"{case_id}: expected_fact_fingerprint is required")
        fingerprint = str(case.get("expected_fact_fingerprint") or "")
        if status == "frozen" and (
            len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint)
        ):
            errors.append(f"{case_id}: frozen expected_fact_fingerprint must be sha256")
    return errors


async def _observe(case: dict[str, Any], workers: int | None) -> dict[str, Any]:
    from docmirror.input.entry.factory import PerceiveOptions, perceive_document
    from docmirror.input.entry.options import normalize_parse_policy

    fixture = ROOT / str(case["fixture"])
    if not fixture.is_file():
        raise FileNotFoundError(f"required GA fixture missing: {fixture.relative_to(ROOT)}")
    actual_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    if actual_sha != case["fixture_sha256"]:
        raise ValueError(f"fixture checksum mismatch: {case['id']}: {actual_sha}")
    policy = normalize_parse_policy(**dict(case["parse_policy"]))
    sealed = await perceive_document(fixture, PerceiveOptions(policy=policy, max_workers=workers))
    document_type = str(sealed.entities.document_type or "")
    domain_specific = sealed.entities.domain_specific or {}
    error = sealed.error
    return {
        "id": case["id"],
        "workers": workers,
        "status": sealed.status.value,
        "error_code": str(error.code or "") if error is not None else "",
        "error_message": str(error.message or "") if error is not None else "",
        "document_type": document_type,
        "user_doc_type_hint": domain_specific.get("user_doc_type_hint"),
        "user_doc_type_hint_strength": domain_specific.get("user_doc_type_hint_strength"),
        "plugin_document_type": domain_specific.get("plugin_document_type"),
        "classification_source": domain_specific.get("classification_source"),
        "fact_fingerprint": sealed.fact_fingerprint(),
        "integrity_fingerprint": sealed.integrity_fingerprint,
    }


def _observe_isolated(data: dict[str, Any], case: dict[str, Any], workers: int) -> dict[str, Any]:
    """Run one case in a clean process to isolate caches and peak memory."""
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--_observe",
        str(case["id"]),
        "--workers",
        str(workers),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=float(data["case_timeout_seconds"]),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"exceeded {data['case_timeout_seconds']}s") from exc
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "GA child failed")
    line = next((item for item in completed.stdout.splitlines() if item.startswith(_OBSERVATION_PREFIX)), "")
    if not line:
        raise RuntimeError("GA child emitted no structured observation")
    return json.loads(line.removeprefix(_OBSERVATION_PREFIX))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--print-observed", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--worker-matrix",
        action="store_true",
        help="execute every case at all manifest worker counts and require identical fact fingerprints",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="execute only the named case; may be repeated (manifest validation still covers all cases)",
    )
    parser.add_argument("--_observe", dest="child_case", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    data = _load()
    errors = validate_manifest(data)
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if args.child_case:
        selected = next((case for case in data["cases"] if case["id"] == args.child_case), None)
        if selected is None:
            print(f"unknown GA case: {args.child_case}", file=sys.stderr)
            return 2
        try:
            observed = asyncio.run(_observe(selected, args.workers))
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(_OBSERVATION_PREFIX + json.dumps(observed, ensure_ascii=False, sort_keys=True))
        return 0
    if args.manifest_only:
        print("6+1 GA manifest OK (7 mandatory real-document cases)")
        return 0

    selected_cases = list(data["cases"])
    if args.case_ids:
        selected = set(args.case_ids)
        known = {str(case["id"]) for case in selected_cases}
        unknown = sorted(selected - known)
        if unknown:
            print(f"unknown GA case(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        selected_cases = [case for case in selected_cases if case["id"] in selected]

    worker_counts = list(data["worker_matrix"]) if args.worker_matrix else [args.workers]
    observations: list[dict[str, Any]] = []
    for case in selected_cases:
        case_observations: list[dict[str, Any]] = []
        for workers in worker_counts:
            try:
                observed = _observe_isolated(data, case, workers)
            except Exception as exc:
                errors.append(f"{case['id']} workers={workers}: {exc}")
                continue
            observations.append(observed)
            case_observations.append(observed)
            if observed["status"] == "failure":
                errors.append(
                    f"{case['id']} workers={workers}: parse failed: "
                    f"{observed['error_code']}: {observed['error_message']}"
                )
            if observed["document_type"] != case["expected_document_type"]:
                errors.append(
                    f"{case['id']} workers={workers}: document_type={observed['document_type']} "
                    f"expected={case['expected_document_type']}"
                )
            expected = str(case["expected_fact_fingerprint"])
            if not args.print_observed and observed["fact_fingerprint"] != expected:
                errors.append(f"{case['id']} workers={workers}: fact fingerprint mismatch")
        fingerprints = {item["fact_fingerprint"] for item in case_observations}
        if args.worker_matrix and len(fingerprints) != 1:
            errors.append(f"{case['id']}: worker matrix produced different fact fingerprints")
    if args.print_observed:
        print(json.dumps(observations, ensure_ascii=False, indent=2))
    if errors:
        print("6+1 GA Golden FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    if args.case_ids:
        print(f"6+1 GA Golden selected cases OK ({len(selected_cases)}/{len(data['cases'])}, no skips)")
    else:
        print("6+1 GA Golden OK (7/7, no skips)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
