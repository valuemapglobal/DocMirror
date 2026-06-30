# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Quality summary helpers for evidence bundles."""

from __future__ import annotations

from typing import Any

from docmirror.models.mirror.completeness import build_mirror_completeness


def build_quality_summary_v2(
    result: Any,
    editions: dict[str, Any] | None = None,
    *,
    document_structure: dict[str, Any] | None = None,
    observed_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build quality summary v2 with observed fidelity metrics (QTC §6.2, W2-05).

    In v2 mode, fidelity layers are scored from 0.0–1.0 with measurable
    pass/fail statuses, rather than the v1 completeness levels
    (full/partial/missing). When observed_metrics are provided from a TQG
    or benchmark run, they are used directly; otherwise, completeness-derived
    scores are used as fallback.

    Args:
        result: ParseResult or compatible object.
        editions: Edition payloads dict.
        document_structure: Optional DFG document structure.
        observed_metrics: Optional dict with pre-computed fidelity metrics.

    Returns:
        Quality summary dict with v2 observed fidelity layers.
    """
    from docmirror.models.mirror.completeness import build_mirror_completeness

    completeness = build_mirror_completeness(result)
    obs = observed_metrics or {}

    # ── Text fidelity v2 ──────────────────────────────────────────────────
    text_metrics = obs.get("text", {})
    text_score = text_metrics.get("score", 1.0 if completeness.get("text") == "full" else 0.5)
    text_status = text_metrics.get("status", "pass" if text_score >= 0.95 else "not_measured")

    # ── Layout fidelity v2 ─────────────────────────────────────────────────
    layout_metrics = obs.get("layout", {})
    layout_score = layout_metrics.get("score", (1.0 if completeness.get("bbox") in ("block", "token") else 0.5))
    layout_status = layout_metrics.get("status", "pass" if layout_score >= 0.90 else "not_measured")

    # ── Business fidelity v2 ───────────────────────────────────────────────
    business_metrics = obs.get("business", {})
    validation_issues = []
    for payload in (editions or {}).values():
        if isinstance(payload, dict):
            validation_issues.extend(payload.get("validation", {}).get("issues") or [])
            validation_issues.extend(payload.get("status", {}).get("warnings") or [])
    business_score = business_metrics.get("score", 1.0 if not validation_issues else 0.8)
    business_status = business_metrics.get("status", "pass" if business_score >= 0.99 else "not_measured")

    # ── Audit fidelity v2 ──────────────────────────────────────────────────
    audit_metrics = obs.get("audit", {})
    has_source_refs = completeness.get("source_refs", "missing") != "missing"
    audit_score = audit_metrics.get("score", 1.0 if has_source_refs else 0.0)
    audit_status = audit_metrics.get("status", "pass" if audit_score >= 0.95 else "not_measured")

    # ── Structure readiness (from v1, still useful) ────────────────────────
    structure_readiness: dict[str, Any] = {}
    if document_structure:
        nodes = document_structure.get("nodes") or []
        edges = document_structure.get("edges") or []
        reading_flow = document_structure.get("reading_flow") or []
        relations = document_structure.get("relations") or []
        outline = document_structure.get("outline") or []
        cross_page_flows = document_structure.get("cross_page_flows") or []
        suppressed_noise = document_structure.get("suppressed_noise") or []

        node_types = {}
        for n in nodes:
            nt = n.get("type", "unknown")
            node_types[nt] = node_types.get(nt, 0) + 1

        structure_readiness = {
            "version": document_structure.get("version", 1),
            "profile": document_structure.get("profile", "raw"),
            "node_count": len(nodes),
            "node_types": node_types,
            "edge_count": len(edges),
            "reading_flow_count": len(reading_flow),
            "main_flow_node_count": len(reading_flow[0].get("node_ids", [])) if reading_flow else 0,
            "outline_section_count": len(outline),
            "cross_page_flow_count": len(cross_page_flows),
            "relation_count": len(relations),
            "suppressed_noise_count": len(suppressed_noise),
        }

    return {
        "version": 2,
        "structure_readiness": structure_readiness,
        "text_fidelity": {
            "score": round(float(text_score), 4),
            "status": text_status,
            "metrics": text_metrics.get("metrics", {}),
            "denominator": text_metrics.get("denominator", 0),
            "failed_items": text_metrics.get("failed_items", []),
            "evidence_refs": text_metrics.get("evidence_refs", []),
        },
        "layout_fidelity": {
            "score": round(float(layout_score), 4),
            "status": layout_status,
            "metrics": layout_metrics.get("metrics", {}),
            "denominator": layout_metrics.get("denominator", 0),
            "failed_items": layout_metrics.get("failed_items", []),
            "evidence_refs": layout_metrics.get("evidence_refs", []),
        },
        "business_fidelity": {
            "score": round(float(business_score), 4),
            "status": business_status,
            "metrics": business_metrics.get("metrics", {}),
            "denominator": business_metrics.get("denominator", 0),
            "failed_items": business_metrics.get("failed_items", []),
            "evidence_refs": business_metrics.get("evidence_refs", []),
            "edition_issue_count": len(validation_issues),
        },
        "audit_fidelity": {
            "score": round(float(audit_score), 4),
            "status": audit_status,
            "metrics": audit_metrics.get("metrics", {}),
            "denominator": audit_metrics.get("denominator", 0),
            "failed_items": audit_metrics.get("failed_items", []),
            "evidence_refs": audit_metrics.get("evidence_refs", []),
        },
        "completeness": completeness,
    }


def build_quality_summary(
    result: Any,
    editions: dict[str, Any] | None = None,
    *,
    document_structure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    completeness = build_mirror_completeness(result)
    validation_issues = []
    for payload in (editions or {}).values():
        if isinstance(payload, dict):
            validation_issues.extend(payload.get("validation", {}).get("issues") or [])
            validation_issues.extend(payload.get("status", {}).get("warnings") or [])
    # DFG structure readiness (STR-5-5)
    structure_readiness: dict[str, Any] = {}
    if document_structure:
        nodes = document_structure.get("nodes") or []
        edges = document_structure.get("edges") or []
        reading_flow = document_structure.get("reading_flow") or []
        relations = document_structure.get("relations") or []
        outline = document_structure.get("outline") or []
        cross_page_flows = document_structure.get("cross_page_flows") or []
        suppressed_noise = document_structure.get("suppressed_noise") or []

        node_types = {}
        for n in nodes:
            nt = n.get("type", "unknown")
            node_types[nt] = node_types.get(nt, 0) + 1

        structure_readiness = {
            "version": document_structure.get("version", 1),
            "profile": document_structure.get("profile", "raw"),
            "node_count": len(nodes),
            "node_types": node_types,
            "edge_count": len(edges),
            "reading_flow_count": len(reading_flow),
            "main_flow_node_count": len(reading_flow[0].get("node_ids", [])) if reading_flow else 0,
            "outline_section_count": len(outline),
            "cross_page_flow_count": len(cross_page_flows),
            "relation_count": len(relations),
            "suppressed_noise_count": len(suppressed_noise),
        }

    return {
        "structure_readiness": structure_readiness,
        "text_fidelity": {
            "level": completeness.get("text"),
            "confidence": float(getattr(result, "confidence", 0.0) or 0.0),
        },
        "layout_fidelity": {
            "bbox": completeness.get("bbox"),
            "tables": completeness.get("tables"),
            "forensic_ready": completeness.get("forensic_ready"),
        },
        "business_fidelity": {
            "document_type": getattr(getattr(result, "entities", None), "document_type", ""),
            "edition_issue_count": len(validation_issues),
        },
        "audit_fidelity": {
            "source_refs": completeness.get("source_refs"),
            "limitations": completeness.get("limitations") or [],
        },
    }
