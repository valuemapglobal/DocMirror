# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG bank_statement plugin oracles — CQF / style meta from edition payload."""

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.report import GateReport


def _edition_properties(edition: dict[str, Any] | None) -> dict[str, Any]:
    if not edition:
        return {}
    document = edition.get("document") or {}
    props = document.get("properties") or {}
    if isinstance(props, dict):
        return props
    return {}


def run_bank_statement_edition_oracle(
    edition: dict[str, Any] | None,
    spec: dict[str, Any],
    report: GateReport,
) -> None:
    """Validate bank plugin CQF/style properties on edition JSON."""
    props = _edition_properties(edition)
    if not props:
        report.passed = False
        report.failures.append("bank_statement oracle: edition document.properties missing")
        return

    min_canonical = spec.get("min_canonical_ratio")
    if min_canonical is not None:
        ratio = float(props.get("canonical_ratio") or 0.0)
        ok = ratio >= float(min_canonical)
        report.checks["canonical_ratio"] = ok
        report.metrics["canonical_ratio"] = ratio
        if not ok:
            report.passed = False
            report.failures.append(
                f"canonical_ratio {ratio:.4f} < {float(min_canonical):.4f}"
            )

    min_coverage = spec.get("min_coverage_ratio")
    if min_coverage is not None:
        cov = float(props.get("coverage_ratio") or 0.0)
        ok = cov >= float(min_coverage)
        report.checks["coverage_ratio"] = ok
        report.metrics["coverage_ratio"] = cov
        if not ok:
            report.passed = False
            report.failures.append(f"coverage_ratio {cov:.4f} < {float(min_coverage):.4f}")

    expected_status = spec.get("extract_status")
    if expected_status is not None:
        status = str(props.get("extract_status") or "")
        ok = status == str(expected_status)
        report.checks["extract_status"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"extract_status expected {expected_status!r}, got {status!r}")

    min_records = spec.get("min_edition_records")
    if min_records is not None:
        data = (edition or {}).get("data") or {}
        records = data.get("records") or []
        count = len(records)
        ok = count >= int(min_records)
        report.checks["edition_records"] = ok
        report.metrics["edition_records"] = count
        if not ok:
            report.passed = False
            report.failures.append(f"edition records {count} < {int(min_records)}")

    forbidden_status = spec.get("forbidden_extract_status")
    if forbidden_status is not None:
        status = str(props.get("extract_status") or "")
        ok = status != str(forbidden_status)
        report.checks["forbidden_extract_status"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"extract_status must not be {forbidden_status!r}")
