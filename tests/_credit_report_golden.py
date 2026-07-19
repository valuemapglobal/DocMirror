# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Privacy-safe golden helpers for private credit-report fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

GOLDEN_COLLECTIONS = (
    "credit_accounts",
    "credit_lines",
    "repayment_records",
    "overdue_records",
    "inquiry_records",
    "public_records",
)
SENSITIVE_FIELDS = (
    "subject_name",
    "id_number",
    "unified_social_credit_code",
    "zhongzheng_code",
    "report_number",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def value_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_hash(record: Any) -> str:
    if not isinstance(record, dict):
        return value_hash(record)
    normalized = record.get("normalized") if isinstance(record.get("normalized"), dict) else {}
    if normalized:
        return value_hash(normalized)
    excluded = {
        "source",
        "source_refs",
        "source_cell_refs",
        "confidence",
        "extraction_status",
        "audit",
        "bbox",
        "page",
    }
    return value_hash({key: value for key, value in record.items() if key not in excluded})


def build_candidate_case(
    output: dict[str, Any],
    *,
    case_id: str,
    source_path: Path,
    source_pages: int,
    truth_scope: str,
) -> dict[str, Any]:
    """Create a redacted candidate snapshot; it is explicitly not approved truth."""
    data = output.get("data") if isinstance(output.get("data"), dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    return {
        "case_id": case_id,
        "source_sha256": sha256_file(source_path),
        "source_pages": int(source_pages),
        "report_subtype": str(fields.get("report_subtype") or "unknown"),
        "content_mode": str(fields.get("content_mode") or "unknown"),
        "review_status": "candidate",
        "truth_scope": truth_scope,
        "generated_from": "current_extractor_output_not_ground_truth",
        "expected": {
            "counts": {name: len(data.get(name) or []) for name in GOLDEN_COLLECTIONS},
            "sensitive_field_hashes": {
                field: value_hash(fields[field]) for field in SENSITIVE_FIELDS if fields.get(field) not in (None, "")
            },
            "record_hashes": {
                name: sorted(record_hash(record) for record in data.get(name) or []) for name in GOLDEN_COLLECTIONS
            },
        },
    }


def compare_output_to_case(output: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    """Compare every truth item declared by a golden case with exact equality."""
    data = output.get("data") if isinstance(output.get("data"), dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    checks: list[dict[str, Any]] = []
    for key, value in (expected.get("counts") or {}).items():
        actual = len(data.get(key) or [])
        checks.append({"path": f"counts.{key}", "expected": value, "actual": actual, "matched": actual == value})
    for key, value in (expected.get("sensitive_field_hashes") or {}).items():
        actual = value_hash(fields.get(key))
        checks.append(
            {"path": f"sensitive_field_hashes.{key}", "expected": value, "actual": actual, "matched": actual == value}
        )
    for key, value in (expected.get("record_hashes") or {}).items():
        actual = sorted(record_hash(record) for record in data.get(key) or [])
        checks.append({"path": f"record_hashes.{key}", "expected": value, "actual": actual, "matched": actual == value})
    matched = sum(bool(check["matched"]) for check in checks)
    return {
        "exact": bool(checks) and matched == len(checks),
        "matched": matched,
        "total": len(checks),
        "precision": matched / len(checks) if checks else 0.0,
        "mismatches": [check for check in checks if not check["matched"]],
    }


__all__ = [
    "GOLDEN_COLLECTIONS",
    "build_candidate_case",
    "compare_output_to_case",
    "record_hash",
    "sha256_file",
    "value_hash",
]
