# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG conservation oracles for Mirror information preservation."""

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.report import GateReport


def _api_from_result(mirror_or_api: Any, spec: dict[str, Any]) -> dict[str, Any]:
    if hasattr(mirror_or_api, "to_mirror_json_vnext"):
        return mirror_or_api.to_mirror_json_vnext(
            mirror_level=spec.get("mirror_level"),
            include_text=spec.get("include_text"),
        )
    if hasattr(mirror_or_api, "model_dump"):
        dumped = mirror_or_api.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return mirror_or_api if isinstance(mirror_or_api, dict) else {}


def _document(api: dict[str, Any]) -> dict[str, Any]:
    if isinstance(api.get("pages"), list):
        doc = dict(api.get("document") or {})
        doc["pages"] = api.get("pages") or []
        if api.get("blocks") and not doc.get("text"):
            texts = [
                str(block.get("text") or block.get("content") or "")
                for block in api.get("blocks") or []
                if isinstance(block, dict)
                and str(block.get("type") or block.get("role") or "") in {"text", "title", "paragraph"}
            ]
            doc["text"] = "\n".join(text for text in texts if text)
            doc.setdefault("raw_text", doc["text"])
        return doc
    if isinstance(api.get("document"), dict):
        return api["document"]
    data = api.get("data") or {}
    doc = data.get("document") or {}
    return doc if isinstance(doc, dict) else {}


def _pages(api: dict[str, Any]) -> list[dict[str, Any]]:
    pages = _document(api).get("pages") or []
    return [page for page in pages if isinstance(page, dict)]


def _table_blocks(api: dict[str, Any]) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for page in _pages(api):
        for table in page.get("tables") or []:
            if isinstance(table, dict):
                tables.append(table)
    return tables


def _text_blocks(api: dict[str, Any]) -> list[dict[str, Any]]:
    from docmirror.models.mirror.page_access import page_flow_texts

    texts: list[dict[str, Any]] = []
    if isinstance(api.get("blocks"), list):
        text_like = {"text", "title", "heading", "header", "paragraph", "footer", "footnote"}
        for block in api.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            if str(block.get("type") or block.get("role") or "") in text_like and (
                block.get("text") or block.get("content")
            ):
                texts.append(block)
        if texts:
            return texts
    doc = _document(api)
    for page in _pages(api):
        page_num = int(page.get("page_number") or 0)
        if page_num:
            for text in page_flow_texts(doc, page_num):
                if isinstance(text, dict):
                    texts.append(text)
            continue
        for text in page.get("texts") or []:
            if isinstance(text, dict):
                texts.append(text)
    return texts


def _logical_tables(api: dict[str, Any]) -> list[dict[str, Any]]:
    tables = _document(api).get("logical_tables") or []
    return [table for table in tables if isinstance(table, dict)]


def _synthesize_conservation(api: dict[str, Any]) -> dict[str, Any]:
    texts = _text_blocks(api)
    tables = _table_blocks(api)
    logical = _logical_tables(api)
    evidence = api.get("evidence") if isinstance(api.get("evidence"), dict) else {}
    evidence_count = 0
    for value in evidence.values():
        if isinstance(value, list):
            evidence_count += len(value)
    if not evidence_count:
        evidence_count = sum(1 for text in texts if text.get("evidence_ids")) + sum(
            1 for table in tables if table.get("evidence_ids")
        )
    return {
        "passed": True,
        "error_count": 0,
        "warning_count": 0,
        "issues": [],
        "metrics": {
            "physical_table_count": len(tables),
            "logical_table_count": len(logical),
            "logical_row_count": _logical_row_count(api, {"metrics": {}}),
            "evidence_span_count": evidence_count,
            "hypothesis_count": len((api.get("diagnostics") or {}).get("hypotheses") or []),
        },
    }


def _synthesize_ehl(api: dict[str, Any], conservation: dict[str, Any]) -> dict[str, Any]:
    diagnostics = api.get("diagnostics") if isinstance(api.get("diagnostics"), dict) else {}
    hypotheses = diagnostics.get("hypotheses") or []
    metrics = conservation.get("metrics") or {}
    return {
        "evidence_summary": {"total_spans": int(metrics.get("evidence_span_count") or 0)},
        "hypotheses": hypotheses,
        "quarantine": diagnostics.get("quarantine") or {},
    }


def _logical_row_count(api: dict[str, Any], conservation: dict[str, Any]) -> int:
    metrics = conservation.get("metrics") or {}
    if metrics.get("logical_row_count") is not None:
        return int(metrics.get("logical_row_count") or 0)
    total = 0
    for table in _logical_tables(api):
        if table.get("row_count") is not None:
            total += int(table.get("row_count") or 0)
        else:
            total += len(table.get("rows") or [])
    return total


def _check_min(report: GateReport, name: str, actual: int, minimum: Any, label: str) -> None:
    if minimum is None:
        return
    expected = int(minimum)
    ok = actual >= expected
    report.checks[name] = ok
    report.metrics[label] = actual
    if not ok:
        report.passed = False
        report.failures.append(f"{label} expected >= {expected}, got {actual}")


def _check_bool(report: GateReport, name: str, ok: bool, failure: str) -> None:
    report.checks[name] = ok
    if not ok:
        report.passed = False
        report.failures.append(failure)


def run_mirror_conservation_oracle(
    mirror_or_api: Any,
    spec: dict[str, Any],
    *,
    case_id: str,
    track: str = "",
    tier: str = "regression",
) -> GateReport:
    """Validate ``meta.conservation`` from a ParseResult or serialized mirror."""
    report = GateReport(case_id=case_id, track=track, tier=tier)
    api = _api_from_result(mirror_or_api, spec)
    meta = api.get("meta") if isinstance(api.get("meta"), dict) else {}
    conservation = meta.get("conservation") or _synthesize_conservation(api)
    if not conservation:
        report.passed = False
        report.failures.append("conservation oracle: missing meta.conservation")
        return report

    expected_passed = spec.get("passed")
    if expected_passed is not None:
        ok = bool(conservation.get("passed")) is bool(expected_passed)
        report.checks["conservation_passed"] = ok
        if not ok:
            report.passed = False
            report.failures.append(
                f"conservation passed expected {bool(expected_passed)!r}, got {conservation.get('passed')!r}"
            )

    max_errors = spec.get("max_errors")
    if max_errors is not None:
        error_count = int(conservation.get("error_count") or 0)
        ok = error_count <= int(max_errors)
        report.checks["conservation_max_errors"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"conservation error_count expected <= {max_errors}, got {error_count}")

    required_issue = spec.get("required_issue_code")
    if required_issue:
        issues = conservation.get("issues") or []
        ok = any(isinstance(issue, dict) and issue.get("code") == required_issue for issue in issues)
        report.checks["conservation_required_issue"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"conservation missing issue code {required_issue!r}")

    required_issues = spec.get("required_issue_codes") or []
    for code in required_issues:
        issues = conservation.get("issues") or []
        ok = any(isinstance(issue, dict) and issue.get("code") == code for issue in issues)
        report.checks[f"conservation_required_issue_{code}"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"conservation missing issue code {code!r}")

    forbidden_issues = spec.get("forbidden_issue_codes") or []
    for code in forbidden_issues:
        issues = conservation.get("issues") or []
        ok = not any(isinstance(issue, dict) and issue.get("code") == code for issue in issues)
        report.checks[f"conservation_forbidden_issue_{code}"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"conservation contains forbidden issue code {code!r}")

    min_evidence = spec.get("min_evidence_spans")
    if min_evidence is not None:
        metrics = conservation.get("metrics") or {}
        count = int(metrics.get("evidence_span_count") or 0)
        ok = count >= int(min_evidence)
        report.checks["conservation_min_evidence"] = ok
        report.metrics["evidence_span_count"] = count
        if not ok:
            report.passed = False
            report.failures.append(f"evidence_span_count expected >= {min_evidence}, got {count}")

    metrics = conservation.get("metrics") or {}
    pages = _pages(api)
    texts = _text_blocks(api)
    tables = _table_blocks(api)
    logical = _logical_tables(api)
    doc = _document(api)
    ehl = meta.get("ehl") or _synthesize_ehl(api, conservation)

    _check_min(report, "conservation_min_pages", len(pages), spec.get("min_pages"), "page_count")
    _check_min(report, "conservation_min_text_blocks", len(texts), spec.get("min_text_blocks"), "text_block_count")
    _check_min(
        report,
        "conservation_min_text_chars",
        len(str(doc.get("text") or "")),
        spec.get("min_text_chars"),
        "text_char_count",
    )
    _check_min(
        report,
        "conservation_min_physical_tables",
        int(metrics.get("physical_table_count") or len(tables)),
        spec.get("min_physical_tables"),
        "physical_table_count",
    )
    _check_min(
        report,
        "conservation_min_logical_tables",
        int(metrics.get("logical_table_count") or len(logical)),
        spec.get("min_logical_tables"),
        "logical_table_count",
    )
    _check_min(
        report,
        "conservation_min_logical_rows",
        _logical_row_count(api, conservation),
        spec.get("min_logical_rows"),
        "logical_row_count",
    )
    _check_min(
        report,
        "conservation_min_hypotheses",
        int(metrics.get("hypothesis_count") or len(ehl.get("hypotheses") or [])),
        spec.get("min_hypotheses"),
        "hypothesis_count",
    )

    max_warnings = spec.get("max_warnings")
    if max_warnings is not None:
        warning_count = int(conservation.get("warning_count") or 0)
        ok = warning_count <= int(max_warnings)
        report.checks["conservation_max_warnings"] = ok
        report.metrics["warning_count"] = warning_count
        if not ok:
            report.passed = False
            report.failures.append(f"conservation warning_count expected <= {max_warnings}, got {warning_count}")

    if spec.get("require_ehl"):
        summary = ehl.get("evidence_summary") or {}
        ok = bool(summary) and int(summary.get("total_spans") or 0) > 0
        _check_bool(report, "conservation_require_ehl", ok, "expected non-empty meta.ehl.evidence_summary")

    if spec.get("require_raw_text"):
        _check_bool(
            report,
            "conservation_require_raw_text",
            bool(doc.get("raw_text")),
            "expected document.raw_text in the supplied forensic evaluation payload",
        )

    if spec.get("require_page_dimensions"):
        ok = all(page.get("width") is not None and page.get("height") is not None for page in pages) and bool(pages)
        _check_bool(report, "conservation_require_page_dimensions", ok, "expected every page to expose width/height")

    if spec.get("require_text_evidence"):
        ok = any(text.get("evidence_ids") for text in texts)
        _check_bool(report, "conservation_require_text_evidence", ok, "expected at least one text block evidence_ids")

    if spec.get("require_table_evidence"):
        ok = any(table.get("evidence_ids") for table in tables)
        _check_bool(report, "conservation_require_table_evidence", ok, "expected at least one table evidence_ids")

    if spec.get("require_table_layer"):
        ok = any(table.get("extraction_layer") for table in tables)
        _check_bool(report, "conservation_require_table_layer", ok, "expected at least one table extraction_layer")

    if spec.get("require_candidate_audit"):
        hypotheses = ehl.get("hypotheses") or []
        ok = any(isinstance(item, dict) and item.get("method") == "bcs" for item in hypotheses)
        _check_bool(report, "conservation_require_candidate_audit", ok, "expected BCS candidate hypotheses in meta.ehl")

    if spec.get("require_quarantine_annex"):
        quarantine = ehl.get("quarantine")
        ok = isinstance(quarantine, dict) and bool(quarantine)
        _check_bool(report, "conservation_require_quarantine_annex", ok, "expected non-empty meta.ehl.quarantine")

    return report
