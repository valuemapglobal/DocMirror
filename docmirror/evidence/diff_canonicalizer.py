# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Artifact canonicalizer for diff comparison (W4-01).

Produces a stable, sorted representation of a VisualEvidenceGraph or task
directory so that two parse runs can be compared deterministically.
"""

from __future__ import annotations

from typing import Any


def canonicalize_visual_graph(graph: Any) -> dict[str, Any]:
    """Produce a canonicalized dict from a VisualEvidenceGraph.

    Nodes are sorted by id; edges sorted by (from_node, to_node); pages
    sorted by page number. BBox floats are rounded to 2 decimal places to
    avoid floating-point noise.
    """
    if graph is None:
        return {"version": 1, "nodes": {}, "edges": [], "pages": []}

    if hasattr(graph, "to_dict"):
        data = graph.to_dict()
    elif isinstance(graph, dict):
        data = dict(graph)
    else:
        return {"version": 1, "nodes": {}, "edges": [], "pages": []}

    # Sort pages by page number
    pages = sorted(data.get("pages", []), key=lambda p: p.get("page", 0) or 0)
    for pg in pages:
        pg["nodes"] = sorted(pg.get("nodes", []))

    # Sort nodes alphabetically by id and round bbox
    nodes = data.get("nodes", {})
    sorted_nodes: dict[str, Any] = {}
    for nid in sorted(nodes.keys()):
        node = dict(nodes[nid])
        if node.get("bbox"):
            node["bbox"] = [round(float(v), 2) for v in node["bbox"]]
        if node.get("confidence") is not None:
            node["confidence"] = round(float(node["confidence"]), 4)
        sorted_nodes[nid] = node

    # Sort edges by (from_node, to_node)
    edges = sorted(
        data.get("edges", []), key=lambda e: (e.get("from", e.get("from_node", "")), e.get("to", e.get("to_node", "")))
    )

    return {
        "version": data.get("version", 1),
        "document_id": data.get("document_id", ""),
        "task_id": data.get("task_id", ""),
        "coordinate_system": data.get("coordinate_system", "pdf_points_top_left"),
        "pages": pages,
        "nodes": sorted_nodes,
        "edges": edges,
        "node_count": len(sorted_nodes),
        "edge_count": len(edges),
        "page_count": len(pages),
    }


def canonicalize_overlay_manifest(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Produce a canonicalized dict from an overlay manifest."""
    if manifest is None:
        return {"version": 1, "layers": [], "overlays": [], "summary": {}}
    data = dict(manifest)
    overlays = sorted(
        data.get("overlays", []),
        key=lambda o: (o.get("page", 0) or 0, o.get("node_id", "")),
    )
    for ov in overlays:
        if ov.get("bbox"):
            ov["bbox"] = [round(float(v), 2) for v in ov["bbox"]]
        if ov.get("confidence") is not None:
            ov["confidence"] = round(float(ov["confidence"]), 4)
    return {
        "version": data.get("version", 1),
        "coordinate_system": data.get("coordinate_system", "pdf_points_top_left"),
        "document_id": data.get("document_id", ""),
        "task_id": data.get("task_id", ""),
        "layers": data.get("layers", []),
        "overlays": overlays,
        "summary": data.get("summary", {}),
    }


def canonicalize_source_span_ledger(ledger: Any) -> dict[str, Any]:
    """Produce a canonicalized dict from a SourceSpanLedger."""
    if ledger is None:
        return {"version": 1, "field_spans": [], "unresolved_fields": [], "summary": {}}
    if hasattr(ledger, "to_dict"):
        data = ledger.to_dict()
    elif isinstance(ledger, dict):
        data = dict(ledger)
    else:
        return {"version": 1, "field_spans": [], "unresolved_fields": [], "summary": {}}

    field_spans = sorted(
        data.get("field_spans", []),
        key=lambda s: s.get("field_path", ""),
    )
    for fs in field_spans:
        if fs.get("bbox"):
            fs["bbox"] = [round(float(v), 2) for v in fs["bbox"]]
        if fs.get("confidence") is not None:
            fs["confidence"] = round(float(fs["confidence"]), 4)

    unresolved = sorted(
        data.get("unresolved_fields", []),
        key=lambda u: u.get("field_path", ""),
    )

    return {
        "version": data.get("version", 1),
        "document_id": data.get("document_id", ""),
        "task_id": data.get("task_id", ""),
        "field_spans": field_spans,
        "unresolved_fields": unresolved,
        "summary": data.get("summary", {}),
    }


def canonicalize_quality_decision(qd: Any) -> dict[str, Any]:
    """Produce a canonicalized dict from a QualityDecisionReport."""
    if qd is None:
        return {"version": 2, "decision": "not_computed", "needs_review": []}
    if hasattr(qd, "to_dict"):
        data = qd.to_dict()
    elif isinstance(qd, dict):
        data = dict(qd)
    else:
        return {"version": 2, "decision": "not_computed", "needs_review": []}

    nr = sorted(
        data.get("needs_review", []),
        key=lambda r: r.get("field_path", "") or r.get("node_id", ""),
    )
    return {
        "version": data.get("version", 2),
        "decision": data.get("decision", "not_computed"),
        "decision_reason": data.get("decision_reason", ""),
        "confidence_policy": data.get("confidence_policy", ""),
        "summary": data.get("summary", {}),
        "blocking_issues": data.get("blocking_issues", []),
        "needs_review": nr,
        "metrics": data.get("metrics", {}),
    }


__all__ = [
    "canonicalize_visual_graph",
    "canonicalize_overlay_manifest",
    "canonicalize_source_span_ledger",
    "canonicalize_quality_decision",
]
