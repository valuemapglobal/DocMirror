#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Observe deterministic Community projection contracts from one source tree."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
_OBSERVATION_PREFIX = "DOCMIRROR_COMMUNITY_OBSERVATION="


def projection_fingerprint(payload: dict[str, Any]) -> str:
    """Hash the complete persisted Community JSON contract."""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _value_fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def projection_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Return reviewable invariants without exposing private field values."""
    datasets = payload.get("datasets") if isinstance(payload.get("datasets"), list) else []
    return {
        "schema": payload.get("schema"),
        "document_type": (payload.get("document") or {}).get("type"),
        "document_sha256": _value_fingerprint(payload.get("document")),
        "section_count": len(payload.get("sections") or []),
        "sections_sha256": _value_fingerprint(payload.get("sections")),
        "datasets": [
            {
                "name": dataset.get("name"),
                "row_count": dataset.get("row_count"),
                "record_ids_sha256": _value_fingerprint([row.get("record_id") for row in dataset.get("rows") or []]),
                "rows_sha256": _value_fingerprint(dataset.get("rows") or []),
            }
            for dataset in datasets
            if isinstance(dataset, dict)
        ],
        "warning_codes": [
            warning.get("code") for warning in payload.get("warnings") or [] if isinstance(warning, dict)
        ],
        "warnings_sha256": _value_fingerprint(payload.get("warnings") or []),
    }


async def _observe(
    code_root: Path,
    fixture_root: Path,
    case: dict[str, Any],
    workers: int,
    output_dir: Path | None,
) -> dict[str, Any]:
    sys.path.insert(0, str(code_root))
    from docmirror.input.entry.factory import PerceiveOptions, perceive_document
    from docmirror.input.entry.options import normalize_parse_policy
    from docmirror.server.output_builder import build_community_projection

    fixture = fixture_root / str(case["fixture"])
    policy = normalize_parse_policy(**dict(case["parse_policy"]))
    sealed = await perceive_document(fixture, PerceiveOptions(policy=policy, max_workers=workers))
    before = sealed.fact_fingerprint()
    payload = build_community_projection(sealed, file_path=str(fixture))
    if payload is None:
        raise RuntimeError(f"{case['id']}: Community projector returned no payload")
    if sealed.fact_fingerprint() != before or not sealed.verify_integrity():
        raise RuntimeError(f"{case['id']}: Community projector changed the sealed snapshot")
    package_version = __import__("docmirror").__version__
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{case['id']}-{package_version}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return {
        "id": case["id"],
        "package_version": package_version,
        "core_fact_fingerprint": before,
        "community_projection_fingerprint": projection_fingerprint(payload),
        "summary": projection_summary(payload),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-root", type=Path, default=ROOT)
    parser.add_argument("--fixture-root", type=Path, default=ROOT)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    fixture_root = args.fixture_root.resolve()
    manifest = yaml.safe_load((fixture_root / "docmirror/configs/stability/ga_6plus1.yaml").read_text(encoding="utf-8"))
    cases = list(manifest.get("cases") or [])
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case.get("id") in selected]
    observations = [
        asyncio.run(
            _observe(
                args.code_root.resolve(),
                fixture_root,
                case,
                args.workers,
                args.output_dir.resolve() if args.output_dir else None,
            )
        )
        for case in cases
    ]
    print(_OBSERVATION_PREFIX + json.dumps(observations, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
