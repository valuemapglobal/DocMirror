# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Overlay Manifest builder — produces overlay primitives for visualization.

GA 1.0 design §5.4 / §9 Wave 2: Builds the overlay_manifest.json artifact
from a VisualEvidenceGraph.  Each overlay primitive carries a node_id,
layer assignment, page, bbox, style, label, and tooltip so that the
visual_debug.html renderer can draw and interact with every explainable
element.

Usage::

    from docmirror.evidence.overlay_manifest import build_overlay_manifest
    manifest = build_overlay_manifest(graph)
    print(manifest)
"""

from __future__ import annotations

from typing import Any

from docmirror.models.visual_evidence import VisualEvidenceGraph, VisualNode


# ── Layer taxonomy ───────────────────────────────────────────────────

_DEFAULT_LAYERS = [
    {"id": "pages", "label": "Page bounds", "default_visible": True},
    {"id": "blocks", "label": "Text blocks", "default_visible": True},
    {"id": "tables", "label": "Tables", "default_visible": True},
    {"id": "cells", "label": "Table cells", "default_visible": False},
    {"id": "fields", "label": "Edition fields", "default_visible": True},
    {"id": "key_values", "label": "Key-value pairs", "default_visible": True},
    {"id": "quality", "label": "Quality issues", "default_visible": True},
    {"id": "needs_review", "label": "Needs review", "default_visible": True},
    {"id": "diff", "label": "Diff changes", "default_visible": False},
    {"id": "reading_order", "label": "Reading order", "default_visible": False},
    {"id": "suppressed", "label": "Suppressed noise", "default_visible": False},
]

# ── Kind → layer mapping ─────────────────────────────────────────────

_KIND_TO_LAYER = {
    "page": "pages",
    "block": "blocks",
    "span": "blocks",
    "token": "blocks",
    "table": "tables",
    "cell": "cells",
    "field": "fields",
    "record": "fields",
    "key_value": "key_values",
    "quality_issue": "quality",
    "needs_review": "needs_review",
    "diff_change": "diff",
    "fallback": "needs_review",
    "unresolved": "needs_review",
    "section": "blocks",
    "reading_order": "reading_order",
    "image": "blocks",
    "formula": "blocks",
}

# ── Kind → style mapping ────────────────────────────────────────────

_KIND_TO_STYLE = {
    "page": {"stroke": "#d0d7de", "strokeWidth": 1, "fill": "transparent", "dash": []},
    "block": {"stroke": "#54aeff", "strokeWidth": 1.5, "fill": "rgba(84,174,255,0.08)"},
    "span": {"stroke": "#54aeff", "strokeWidth": 0.5, "fill": "rgba(84,174,255,0.05)"},
    "token": {"stroke": "#a5d6ff", "strokeWidth": 0.5, "fill": "transparent"},
    "table": {"stroke": "#4ac26b", "strokeWidth": 2, "fill": "rgba(74,194,107,0.06)"},
    "cell": {"stroke": "#4ac26b", "strokeWidth": 0.5, "fill": "rgba(74,194,107,0.04)"},
    "field": {"stroke": "#cf222e", "strokeWidth": 1.5, "fill": "rgba(207,34,46,0.06)"},
    "record": {"stroke": "#cf222e", "strokeWidth": 1, "fill": "transparent"},
    "key_value": {"stroke": "#d4a72c", "strokeWidth": 1.5, "fill": "rgba(212,167,44,0.06)"},
    "quality_issue": {"stroke": "#cf222e", "strokeWidth": 2, "fill": "rgba(207,34,46,0.12)"},
    "needs_review": {"stroke": "#d4a72c", "strokeWidth": 1.5, "fill": "rgba(212,167,44,0.08)"},
    "diff_change": {"stroke": "#8250df", "strokeWidth": 2, "fill": "rgba(130,80,223,0.10)"},
    "fallback": {"stroke": "#d4a72c", "strokeWidth": 1, "fill": "rgba(212,167,44,0.06)"},
    "unresolved": {"stroke": "#d4a72c", "strokeWidth": 1, "fill": "rgba(212,167,44,0.08)"},
    "section": {"stroke": "#0969da", "strokeWidth": 1.5, "fill": "transparent"},
    "reading_order": {"stroke": "#8250df", "strokeWidth": 0.5, "fill": "transparent", "dash": [4, 4]},
    "image": {"stroke": "#bf3980", "strokeWidth": 1, "fill": "transparent"},
    "formula": {"stroke": "#0550ae", "strokeWidth": 1, "fill": "transparent"},
}


def build_overlay_manifest(graph: VisualEvidenceGraph) -> dict[str, Any]:
    """Build an overlay manifest from a VisualEvidenceGraph.

    Args:
        graph: A populated VisualEvidenceGraph.

    Returns:
        Overlay manifest dict with layers, overlays, and summary.
    """
    overlays: list[dict[str, Any]] = []
    page_dims: dict[int, tuple[float, float]] = {}
    for pg in graph.pages:
        pn = pg.get("page", 0)
        if pn:
            page_dims[pn] = (
                float(pg.get("width", 595.0) or 595.0),
                float(pg.get("height", 842.0) or 842.0),
            )

    for node_id, node in graph.nodes.items():
        if not node.bbox or not node.page:
            continue

        layer = _KIND_TO_LAYER.get(node.kind, "blocks")
        style = _KIND_TO_STYLE.get(node.kind, _KIND_TO_STYLE["block"])

        tooltip_parts = [f"kind={node.kind}", f"confidence={node.confidence:.2f}"]
        if node.review != "auto_accepted":
            tooltip_parts.append(f"review={node.review}")
        if node.field_path:
            tooltip_parts.append(f"field={node.field_path}")
        if node.source_refs:
            tooltip_parts.append(f"refs={len(node.source_refs)}")
        if node.edition:
            tooltip_parts.append(f"edition={node.edition}")

        overlays.append({
            "node_id": node_id,
            "layer": layer,
            "page": node.page,
            "bbox": node.bbox,
            "page_width": page_dims.get(node.page, (595.0, 842.0))[0],
            "page_height": page_dims.get(node.page, (595.0, 842.0))[1],
            "style": style,
            "label": node.label[:60] if node.label else "",
            "tooltip": " ".join(tooltip_parts),
            "confidence": node.confidence,
            "review": node.review,
            "kind": node.kind,
            "field_path": node.field_path,
        })

    # ── Group by page and layer for the summary ──
    by_layer: dict[str, int] = {}
    by_page: dict[int, int] = {}
    for ov in overlays:
        by_layer[ov["layer"]] = by_layer.get(ov["layer"], 0) + 1
        by_page[ov["page"]] = by_page.get(ov["page"], 0) + 1

    # ── Build layers with actual counts ──
    layers = []
    for dl in _DEFAULT_LAYERS:
        count = by_layer.get(dl["id"], 0)
        layers.append({**dl, "overlay_count": count})

    return {
        "version": 1,
        "coordinate_system": graph.coordinate_system,
        "document_id": graph.document_id,
        "task_id": graph.task_id,
        "layers": layers,
        "overlays": overlays,
        "summary": {
            "total_overlays": len(overlays),
            "by_layer": by_layer,
            "by_page": {str(k): v for k, v in sorted(by_page.items())},
            "pages_represented": len(by_page),
        },
    }


__all__ = ["build_overlay_manifest"]
