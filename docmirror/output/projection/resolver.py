"""Projection resolver helpers for edition and artifact outputs."""

from __future__ import annotations

from typing import Any


def _resolve_dgc_status(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata") or {}
    if metadata.get("dgc_status"):
        return str(metadata["dgc_status"])
    domain = metadata.get("domain") or metadata.get("detected_type") or payload.get("plugin", {}).get("name", "")
    try:
        from docmirror.plugins._runtime.plugin_registry import resolve_dgc_status

        return str(resolve_dgc_status(str(domain)))
    except Exception:
        return "unresolved"


def _source_ids(item: dict[str, Any]) -> tuple[list[Any], list[Any]]:
    source_fact_ids = item.get("source_fact_ids") or item.get("source_ids") or []
    evidence_ids = item.get("evidence_ids") or []
    return list(source_fact_ids), list(evidence_ids)


def build_projection_lineage(payload: dict[str, Any]) -> dict[str, Any]:
    """Build compact lineage metadata for an edition payload."""
    edition = payload.get("edition", "community")
    metadata = payload.get("metadata") or {}
    data = payload.get("data") or {}
    fields = data.get("fields") or {}
    records = data.get("records") or []
    dgc_status = _resolve_dgc_status(payload)
    edition_fact_ids = list(metadata.get("source_fact_ids") or [])
    edition_evidence_ids = list(metadata.get("evidence_ids") or [])

    field_lineages: list[dict[str, Any]] = []
    for name, value in fields.items():
        if isinstance(value, dict):
            source_fact_ids, evidence_ids = _source_ids(value)
            if value.get("source_refs") and not source_fact_ids:
                source_fact_ids = []
        else:
            source_fact_ids, evidence_ids = [], []
        if source_fact_ids or evidence_ids or (isinstance(value, dict) and value.get("source_refs")):
            field_lineages.append(
                {
                    "target": f"{edition}.data.fields.{name}",
                    "source_fact_ids": [item for item in source_fact_ids if item not in edition_fact_ids],
                    "evidence_ids": [item for item in evidence_ids if item not in edition_evidence_ids],
                    "dgc_status": dgc_status,
                }
            )

    record_lineages: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        source_fact_ids, evidence_ids = _source_ids(record)
        if source_fact_ids or evidence_ids:
            record_lineages.append(
                {
                    "target": f"{edition}.data.records[{index}]",
                    "source_fact_ids": source_fact_ids,
                    "evidence_ids": evidence_ids,
                    "dgc_status": dgc_status,
                }
            )

    summary = {
        "total_fields": len(fields),
        "materialized_field_lineages": len(field_lineages),
        "total_records": len(records),
        "materialized_record_lineages": len(record_lineages),
    }
    if records and not record_lineages:
        summary["record_lineage_scope"] = "edition_level"

    return {
        "edition_lineage": {
            "edition": edition,
            "plugin": payload.get("plugin", {}).get("name", ""),
            "support_level": metadata.get("support_level", ""),
            "dgc_status": dgc_status,
            "source_fact_ids": edition_fact_ids,
            "evidence_ids": edition_evidence_ids,
        },
        "field_lineages": field_lineages,
        "record_lineages": record_lineages,
        "projection_summary": summary,
    }


def build_partial_result_envelope(
    partial_output: dict[str, Any],
    *,
    domain: str | None = None,
    support_level: str | None = None,
) -> dict[str, Any]:
    total_pages = int(partial_output.get("total_pages") or 0)
    success_pages = partial_output.get("success_pages") or []
    failed_pages = partial_output.get("failed_pages") or []
    partial_pages = partial_output.get("partial_pages") or []
    skipped_pages = partial_output.get("skipped_pages") or []
    failure_count = len(failed_pages) + len(partial_pages)
    skipped_count = len(skipped_pages)
    partial = bool(failure_count or skipped_count)
    retention = float(partial_output.get("retention_rate", 0.0) or 0.0)
    if total_pages and "retention_rate" not in partial_output:
        retention = len(success_pages) / total_pages
    status_reason = "complete"
    if skipped_count:
        status_reason = "Some pages were skipped"
    elif failure_count:
        status_reason = "Some pages failed or were partially parsed"
    envelope = {
        "partial_result": partial,
        "document_id": partial_output.get("document_id", ""),
        "total_pages": total_pages,
        "success_count": len(success_pages),
        "failure_count": failure_count,
        "skipped_count": skipped_count,
        "page_level_retention": retention,
        "needs_review": partial,
        "output_status": "partial" if partial else "complete",
        "status_reason": status_reason,
        "failed_page_details": list(failed_pages) + list(partial_pages),
        "skipped_page_numbers": list(skipped_pages),
    }
    if domain is not None:
        envelope["domain"] = domain
    if support_level is not None:
        envelope["support_level"] = support_level
    return envelope


def build_quality_decision_block(report: Any) -> dict[str, Any]:
    if hasattr(report, "to_dict"):
        return report.to_dict()
    if isinstance(report, dict):
        return report
    return {"version": 2, "decision": "needs_review", "decision_reason": "unavailable"}


__all__ = ["build_partial_result_envelope", "build_projection_lineage", "build_quality_decision_block"]
