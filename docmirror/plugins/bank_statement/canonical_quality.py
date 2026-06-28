# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Canonical Quality Floor (CQF) — bank statement export audit (ADR-BS-06).

Redefines coverage as canonical_extracted / canonical_expected where canonical rows
satisfy date + (amount with income/expense direction). Drives community degraded
status and honest coverage metrics (BS-013, BS-009).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def is_canonical_row(norm: dict[str, Any]) -> bool:
    """BS-A1: date plus directional amount."""
    if not norm.get("date"):
        return False
    direction = norm.get("direction")
    amount = norm.get("amount")
    if direction in ("income", "expense") and amount not in (None, "", 0, 0.0):
        try:
            return float(amount) != 0.0
        except (TypeError, ValueError):
            return bool(amount)
    return False


def canonical_expected_from_parse_result(parse_result: Any) -> int:
    """Expected canonical rows — LTQG sum(passed) SSOT when enabled."""
    if parse_result is None:
        return 0
    from docmirror.structure.analysis.spe_consumer import read_ltqg_summary, read_structure_spe
    from docmirror.tables.access import get_logical_tables
    from docmirror.tables.compose.ledger_quality import sum_passed_data_row_estimates

    spe = read_structure_spe(parse_result)
    summary = read_ltqg_summary(spe, parse_result)
    if summary.get("enabled"):
        return int(summary.get("expected_data_rows") or 0)

    logical_tables = get_logical_tables(parse_result)
    if logical_tables:
        return sum_passed_data_row_estimates(logical_tables)

    from docmirror.structure.analysis.spe_consumer import mirror_expected_primary_rows

    return mirror_expected_primary_rows(parse_result, spe)


@dataclass(frozen=True)
class CQFResult:
    canonical_expected: int
    canonical_extracted: int
    coverage_ratio: float
    canonical_ratio: float
    extract_status: str  # success | low_coverage | degraded

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_expected": self.canonical_expected,
            "canonical_extracted": self.canonical_extracted,
            "coverage_ratio": round(self.coverage_ratio, 4),
            "canonical_ratio": round(self.canonical_ratio, 4),
            "extract_status": self.extract_status,
        }


def resolve_extract_status(
    *,
    coverage_ratio: float,
    canonical_ratio: float,
) -> str:
    """Map CQF ratios to export status (community / finance alignment)."""
    if coverage_ratio >= 0.80 and canonical_ratio >= 0.80:
        return "success"
    if coverage_ratio < 0.50 or canonical_ratio < 0.50:
        return "degraded"
    return "low_coverage"


def audit_cqf(
    records: list[dict[str, Any]],
    *,
    canonical_expected: int,
) -> CQFResult:
    """Audit extracted records against canonical expected denominator."""
    canonical_extracted = sum(1 for rec in records if is_canonical_row(rec.get("normalized") or {}))
    expected = max(int(canonical_expected or 0), 0)
    if expected <= 0:
        coverage_ratio = 1.0 if canonical_extracted > 0 else 0.0
        canonical_ratio = coverage_ratio
    else:
        coverage_ratio = min(canonical_extracted / expected, 1.0)
        canonical_ratio = canonical_extracted / expected

    status = resolve_extract_status(
        coverage_ratio=coverage_ratio,
        canonical_ratio=canonical_ratio,
    )
    return CQFResult(
        canonical_expected=expected,
        canonical_extracted=canonical_extracted,
        coverage_ratio=coverage_ratio,
        canonical_ratio=canonical_ratio,
        extract_status=status,
    )


__all__ = [
    "CQFResult",
    "audit_cqf",
    "canonical_expected_from_parse_result",
    "is_canonical_row",
    "resolve_extract_status",
]
