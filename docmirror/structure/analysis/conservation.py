# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror information-conservation checks.

The conservation gate is deliberately read-only: it summarizes whether the
current Mirror projection preserved enough provenance to explain empty tables,
logical rows, candidate audit, and quarantine. It never mutates the parse
result and never repairs extraction output.
"""

from __future__ import annotations

from typing import Any


def _structure(parse_result: Any) -> dict[str, Any]:
    info = getattr(parse_result, "parser_info", None)
    spe = getattr(info, "structure", None) if info else None
    return spe if isinstance(spe, dict) else {}


def _has_table_skip_reason(parse_result: Any, spe: dict[str, Any]) -> bool:
    physical_count = sum(len(getattr(page, "tables", []) or []) for page in getattr(parse_result, "pages", []) or [])
    logical_count = len(getattr(parse_result, "logical_tables", []) or [])
    if physical_count or logical_count:
        return True
    reason = spe.get("table_extraction_skipped_reason")
    if reason:
        return True
    primary = spe.get("primary")
    return primary in {"section_led", "prose_led", "scan_led"}


def _logical_rows_with_missing_provenance(parse_result: Any) -> int:
    missing = 0
    for table in getattr(parse_result, "logical_tables", []) or []:
        for row in getattr(table, "rows", []) or []:
            source_page = int(getattr(row, "source_page", 0) or 0)
            source_physical_id = str(getattr(row, "source_physical_id", "") or "")
            raw_source_row_index = getattr(row, "source_row_index", None)
            source_row_index = -1 if raw_source_row_index is None else int(raw_source_row_index)
            if source_page <= 0 or not source_physical_id or source_row_index < 0:
                missing += 1
    return missing


def _has_candidate_audit(parse_result: Any, spe: dict[str, Any]) -> bool:
    competitors = spe.get("competitors")
    if isinstance(competitors, dict) and competitors:
        return True
    annex = getattr(parse_result, "annex", None)
    hypotheses = getattr(annex, "hypotheses", None) if annex else None
    if hypotheses:
        return True
    for page in getattr(parse_result, "pages", []) or []:
        for table in getattr(page, "tables", []) or []:
            if getattr(table, "extraction_layer", "") or getattr(table, "metadata", None):
                return True
    return False


def _quarantine_items_without_reason(items: Any) -> int:
    if not items:
        return 0
    missing = 0
    for item in list(items):
        if not isinstance(item, dict):
            continue
        if not (item.get("reason") or item.get("quality_skip_reason") or item.get("skip_reason")):
            missing += 1
    return missing


def mirror_conservation_summary(parse_result: Any) -> dict[str, Any]:
    """Return a compact Mirror conservation summary for API meta/TQG checks."""
    spe = _structure(parse_result)
    physical_count = sum(len(getattr(page, "tables", []) or []) for page in getattr(parse_result, "pages", []) or [])
    logical_tables = list(getattr(parse_result, "logical_tables", []) or [])
    logical_count = len(logical_tables)
    logical_rows = sum(len(getattr(table, "rows", []) or []) for table in logical_tables)
    annex = getattr(parse_result, "annex", None)
    evidence_summary = getattr(annex, "evidence_summary", None) if annex else None
    hypotheses = list(getattr(annex, "hypotheses", None) or []) if annex else []
    if evidence_summary is None:
        try:
            from docmirror.models.ehl import summarize_parse_result_evidence

            evidence_summary = summarize_parse_result_evidence(parse_result)
        except Exception:
            evidence_summary = None
    if not hypotheses:
        try:
            from docmirror.models.ehl import build_mirror_hypotheses

            hypotheses = build_mirror_hypotheses(parse_result)
        except Exception:
            hypotheses = []

    issues: list[dict[str, Any]] = []
    if not _has_table_skip_reason(parse_result, spe):
        issues.append(
            {
                "code": "empty_tables_without_reason",
                "severity": "error",
                "message": "No physical/logical tables and no table skip reason in SPE.",
            }
        )

    missing_provenance = _logical_rows_with_missing_provenance(parse_result)
    if missing_provenance:
        issues.append(
            {
                "code": "logical_row_provenance_missing",
                "severity": "error",
                "count": missing_provenance,
            }
        )

    if (physical_count or logical_count or spe.get("table_extraction") == "full") and not _has_candidate_audit(
        parse_result, spe
    ):
        issues.append(
            {
                "code": "candidate_audit_missing",
                "severity": "warning",
                "message": "No SPE competitors, annex hypotheses, or table extraction metadata found.",
            }
        )

    q_phys = spe.get("quarantined_physical_tables")
    q_log = spe.get("quarantined_logical_tables_annex")
    missing_q = _quarantine_items_without_reason(q_phys) + _quarantine_items_without_reason(q_log)
    if missing_q:
        issues.append(
            {
                "code": "quarantine_reason_missing",
                "severity": "error",
                "count": missing_q,
            }
        )

    error_count = sum(1 for issue in issues if issue.get("severity") == "error")
    warning_count = len(issues) - error_count
    return {
        "passed": error_count == 0,
        "issue_count": len(issues),
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
        "metrics": {
            "physical_table_count": physical_count,
            "logical_table_count": logical_count,
            "logical_row_count": logical_rows,
            "evidence_span_count": int(getattr(evidence_summary, "total_spans", 0) or 0),
            "hypothesis_count": len(hypotheses),
        },
    }
