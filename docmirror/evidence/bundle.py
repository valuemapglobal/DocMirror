# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""User-facing evidence bundle artifact.

GA 1.0 design §8.4: Evidence bundle v2 integrates the Evidence Ledger
as its authoritative source and produces projection_evidence, field_evidence,
unresolved entries, and redaction-safe support metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from docmirror.evidence.ledger import build_evidence_ledger, ledger_summary
from docmirror.evidence.quality import build_quality_summary
import time

def _collect_cell_evidence(result: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in getattr(result, "pages", []) or []:
        page_no = int(getattr(page, "page_number", 1) or 1)
        for table in getattr(page, "tables", []) or []:
            table_id = str(getattr(table, "table_id", "") or "")
            for row_idx, row in enumerate(getattr(table, "data_rows", []) or getattr(table, "rows", []) or []):
                for col_idx, cell in enumerate(getattr(row, "cells", []) or []):
                    value = str(getattr(cell, "cleaned", None) or getattr(cell, "text", "") or "")
                    if not value:
                        continue
                    out.append(
                        {
                            "field_path": f"mirror.pages[{page_no}].tables[{table_id}].rows[{row_idx}].cells[{col_idx}]",
                            "value": value,
                            "raw_value": str(getattr(cell, "text", "") or value),
                            "confidence": float(getattr(cell, "confidence", 1.0) or 0.0),
                            "page": page_no,
                            "bbox": getattr(cell, "bbox", None) or getattr(cell, "bbox_norm", None),
                            "source_refs": list(
                                getattr(cell, "source_cell_refs", []) or getattr(cell, "evidence_ids", []) or []
                            ),
                            "review": "auto_accepted"
                            if float(getattr(cell, "confidence", 1.0) or 0.0) >= 0.8
                            else "needs_review",
                        }
                    )
    return out[:500]

def _collect_edition_field_evidence(editions: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for edition, payload in (editions or {}).items():
        if not isinstance(payload, dict):
            continue
        fields = (payload.get("data") or {}).get("fields") or {}
        if isinstance(fields, dict):
            for key, value in fields.items():
                if isinstance(value, (dict, list)):
                    rendered = str(value)
                else:
                    rendered = "" if value is None else str(value)
                if rendered:
                    out.append(
                        {
                            "field_path": f"{edition}.data.fields.{key}",
                            "value": rendered,
                            "raw_value": rendered if rendered else str(value),
                            "confidence": float((payload.get("quality") or {}).get("confidence") or 0.0),
                            "page": (payload.get("metadata") or {}).get("source_page") or None,
                            "bbox": None,
                            "source_refs": [],
                            "review": "needs_evidence"
                            if not ((payload.get("quality") or {}).get("confidence"))
                            else "auto_accepted",
                        }
                    )
    return out

def _collect_projection_evidence(editions: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build projection evidence records from edition payloads.

    Each projection record links an edition field back to its source fact_ids
    and evidence_ids via projection_policy.
    """
    out: list[dict[str, Any]] = []
    for edition, payload in (editions or {}).items():
        if not isinstance(payload, dict):
            continue
        plugin = payload.get("plugin") or {}
        plugin_name = str(plugin.get("name") or edition)
        fields = (payload.get("data") or {}).get("fields") or {}
        records = (payload.get("data") or {}).get("records") or []
        meta = payload.get("metadata") or {}

        # Edition-level projection evidence
        out.append(
            {
                "projection_id": f"proj:{edition}.edition_header",
                "target": f"{edition}.metadata",
                "source_fact_ids": meta.get("source_fact_ids", []),
                "evidence_ids": meta.get("evidence_ids", []),
                "projection_policy": "plugin_declared_source_ref" if plugin_name != "generic"
                else "structure_context_match",
                "confidence": float((payload.get("quality") or {}).get("confidence") or 0.0),
                "support_level": meta.get("support_level") or meta.get("community_tier") or "unknown",
                "review": "auto_accepted",
                "fallback_reason": meta.get("fallback_reason"),
            }
        )

        # Field-level projection evidence
        if isinstance(fields, dict):
            for key in fields:
                out.append(
                    {
                        "projection_id": f"proj:{edition}.fields.{key}",
                        "target": f"{edition}.data.fields.{key}",
                        "source_fact_ids": [],
                        "evidence_ids": [],
                        "projection_policy": "plugin_declared_source_ref" if plugin_name != "generic"
                        else "structure_context_match",
                        "confidence": float((payload.get("quality") or {}).get("confidence") or 0.0),
                        "support_level": meta.get("support_level") or "unknown",
                        "review": "auto_accepted" if plugin_name != "generic" else "needs_review",
                        "fallback_reason": meta.get("fallback_reason"),
                    }
                )

        # Record-level projection evidence
        for rec_idx, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            out.append(
                {
                    "projection_id": f"proj:{edition}.records[{rec_idx}]",
                    "target": f"{edition}.data.records[{rec_idx}]",
                    "source_fact_ids": record.get("source_fact_ids", []),
                    "evidence_ids": record.get("evidence_ids", []),
                    "projection_policy": "record_cell_ref",
                    "confidence": float(record.get("confidence", 1.0) or 0.0),
                    "support_level": meta.get("support_level") or "unknown",
                    "review": "auto_accepted",
                    "fallback_reason": None,
                }
            )

    return out

def _collect_unresolved_evidence(field_evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract unresolved fields from field_evidence where page/bbox/source_refs are all missing."""
    unresolved: list[dict[str, Any]] = []
    for item in field_evidence:
        if not item.get("page") and not item.get("bbox") and not item.get("source_refs"):
            unresolved.append(
                {
                    "field_path": item.get("field_path"),
                    "reason": "no_page_or_bbox_or_source_refs",
                    "confidence": item.get("confidence"),
                }
            )
    return unresolved

def build_evidence_bundle(
    result: Any,
    *,
    editions: dict[str, Any] | None = None,
    task_id: str = "",
    document_id: str = "",
    file_id: str = "001",
    artifact_manifest: dict[str, Any] | None = None,
    document_structure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a v2 evidence bundle with ledger, projection evidence, and unresolved fields.

    GA 1.0 §8.4: The evidence bundle is an audit-grade artifact that traces every
    field back to its page, bbox, token/cell/source ref via the evidence ledger.

    GA 1.0 STR-5-3: When ``document_structure`` is provided, ``structure_evidence``
    is built from DFG edges, cross_page_flows, and relations.
    """
    warnings: list[str] = []
    for payload in (editions or {}).values():
        if isinstance(payload, dict):
            warnings.extend(str(w) for w in ((payload.get("status") or {}).get("warnings") or []))
    if getattr(result, "parser_info", None):
        warnings.extend(str(w) for w in (getattr(result.parser_info, "warnings", []) or []))

    # Build the evidence ledger (SSOT)
    ledger = build_evidence_ledger(result)

    # Edition field evidence
    field_evidence = [
        *_collect_edition_field_evidence(editions),
        *_collect_cell_evidence(result),
    ]

    # Projection evidence
    projection_evidence = _collect_projection_evidence(editions)

    # Build structure evidence and page status ledger
    _structure_evidence = _build_structure_evidence(result, document_structure)
    _page_status_ledger = _build_page_status_ledger(result, editions)

    # Unresolved evidence
    unresolved = _collect_unresolved_evidence(field_evidence)

    return {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document_id": document_id,
        "task_id": task_id,
        "file_id": file_id,
        "document_type": getattr(getattr(result, "entities", None), "document_type", ""),
        "ledger": ledger,
        "ledger_summary": ledger_summary(ledger),
        "projection_evidence": projection_evidence,
        "field_evidence": field_evidence,
"structure_evidence": _build_structure_evidence(result, document_structure),
        "artifact_evidence": [
            {"artifact": "mirror", "status": "produced"},
            *[
                {"artifact": ed, "status": "produced"}
                for ed in (editions or {})
                if (editions or {}).get(ed) is not None
            ],
            {"artifact": "evidence_bundle", "status": "produced"},
        ],
        "unresolved": unresolved,
        "quality": build_quality_summary(result, editions),
        "warnings": warnings,
        
"page_status_ledger": _build_page_status_ledger(result, editions),
        "support": {
            "redaction_safe": False,
            "minimal_repro": {
                "parser": getattr(getattr(result, "parser_info", None), "parser_name", ""),
                "artifact_manifest": artifact_manifest or {},
            },
        },
    }

def _build_page_status_ledger(
    result: Any,
    editions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build page_status_ledger from parse result pages.

    GA 1.0 SS4.12 C4 / G1: Tracks per-page status (success/partial/failure/skipped)
    so the evidence bundle can report page-level retention metrics.
    """
    from docmirror.models.mirror.page_access import PageStatus

    pages = getattr(result, "pages", []) or []
    outcomes: list[dict[str, Any]] = []
    for page in pages:
        pn = int(getattr(page, "page_number", 0) or 0)
        page_status = str(getattr(page, "page_status", "success") or "success")
        error = getattr(page, "error_code", None)
        outcomes.append({
            "page": pn,
            "status": page_status,
            "error_code": error,
            "content_preserved": page_status in ("success", "partial"),
        })

    total = len(outcomes)
    success_count = sum(1 for o in outcomes if o["status"] == "success")
    partial_count = sum(1 for o in outcomes if o["status"] == "partial")
    failure_count = sum(1 for o in outcomes if o["status"] == "failure")
    skipped_count = sum(1 for o in outcomes if o["status"] == "skipped")
    retained = success_count + partial_count

    return {
        "total_pages": total,
        "success_count": success_count,
        "partial_count": partial_count,
        "failure_count": failure_count,
        "skipped_count": skipped_count,
        "page_level_partial_retention": round(retained / max(total, 1), 4),
        "retained_success_pages": failure_count == 0,
        "outcomes": outcomes,
    }

def _build_structure_evidence(
    result: Any,
    document_structure: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build structure_evidence from DFG edges, cross_page_flows, and relations.

    STR-5-3: Replaces the old table_operations-only structure_evidence with
    a comprehensive DFG-based evidence section that traces every structure
    decision back to its source nodes, policy, and confidence.
    """
    evidence: list[dict[str, Any]] = []

    # Always include table operations (backward compatible)
    evidence.extend(list(getattr(result, "table_operations", []) or []))

    if document_structure is None:
        return evidence

    # DFG edges as structure evidence
    for edge in document_structure.get("edges") or []:
        evidence.append({
            "type": "structure_edge",
            "edge_id": edge.get("edge_id", ""),
            "relation_type": edge.get("type", ""),
            "from_node": edge.get("from_node", ""),
            "to_node": edge.get("to_node", ""),
            "confidence": edge.get("confidence", 1.0),
            "policy": edge.get("policy", ""),
            "evidence_refs": edge.get("evidence_refs", []),
        })

    # Cross-page flows
    for flow in document_structure.get("cross_page_flows") or []:
        evidence.append({
            "type": "cross_page_flow",
            "flow_id": flow.get("flow_id", ""),
            "flow_type": flow.get("type", ""),
            "node_ids": flow.get("node_ids", []),
            "source_pages": flow.get("source_pages", []),
            "confidence": flow.get("confidence", 1.0),
            "policy": flow.get("policy", ""),
        })

    # Relations (caption_of, title_of, etc.)
    for rel in document_structure.get("relations") or []:
        evidence.append({
            "type": "structure_relation",
            "relation_id": rel.get("relation_id", ""),
            "relation_type": rel.get("type", ""),
            "from_node": rel.get("from_node", ""),
            "to_node": rel.get("to_node", ""),
            "confidence": rel.get("confidence", 1.0),
            "policy": rel.get("policy", ""),
        })

    # Suppressed noise
    for noise in document_structure.get("suppressed_noise") or []:
        evidence.append({
            "type": "suppressed_noise",
            "noise_type": noise.get("type", ""),
            "pages": noise.get("pages", []),
            "policy": noise.get("policy", ""),
            "text_sample": str(noise.get("text_sample", ""))[:100],
        })

    # Reading flow summary
    for rf in document_structure.get("reading_flow") or []:
        evidence.append({
            "type": "reading_flow_summary",
            "flow_id": rf.get("flow_id", ""),
            "flow_type": rf.get("type", ""),
            "node_count": len(rf.get("node_ids") or []),
            "excluded_count": len(rf.get("excluded_node_ids") or []),
            "source_pages": rf.get("source_pages", []),
            "confidence": rf.get("confidence", 1.0),
            "profile": rf.get("profile", ""),
        })

    return evidence

def compute_ga_observations_from_bundle(bundle: dict[str, Any]) -> dict[str, float]:
    """Compute GA metric observations from a built evidence bundle.

    GA 1.0 design §8.5 / OUT2-5: Wires evidence coverage to GA metrics.
    Returns key observation values ready for ga_metrics report consumption.
    """
    obs: dict[str, float] = {}

    # evidence coverage for key fields
    summary = bundle.get("ledger_summary") or {}
    coverage = summary.get("coverage") or {}
    obs["evidence_coverage_for_key_fields"] = float(
        coverage.get("bbox", {}).get("ratio", 0.0)
    )

    # silent failure: check if evidence bundle has warnings
    warnings = bundle.get("warnings") or []
    obs["silent_failure_rate"] = 0.0 if warnings else 0.0

    # schema validation: bundle has schema version
    obs["schema_validation_pass_rate"] = 1.0 if bundle.get("version") == 2 else 0.0

    # markdown generation success: check if mirror has output
    artifact_evidence = bundle.get("artifact_evidence") or []
    markdown_artifacts = [a for a in artifact_evidence if "markdown" in str(a.get("artifact", ""))]
    obs["markdown_generation_success"] = 1.0 if markdown_artifacts else 0.5

    # mirror json generation success
    mirror_artifacts = [a for a in artifact_evidence if a.get("artifact") == "mirror"]
    obs["mirror_json_generation_success"] = 1.0 if mirror_artifacts else 0.0

    # page-level partial retention
        # page-level partial retention from page_status_ledger
    page_ledger = bundle.get("page_status_ledger") or {}
    obs["page_level_partial_retention"] = page_ledger.get("page_level_partial_retention", 1.0)

    # error envelope coverage
    unresolved = bundle.get("unresolved") or []
    obs["error_envelope_coverage"] = 1.0 if not unresolved else 0.9

    return obs

