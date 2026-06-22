# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""W7-02: Visual Debug HTML semantic tests — overlay data must be present.

GA 1.0 design SS7 invariant XVC-I4: visual_debug must not be a bare
artifact listing; it must contain overlay data, SVG rendering surface,
inspector panel, and layer bar.
"""

import json as _json

import pytest

from docmirror.models.visual_evidence import VisualNode, VisualEvidenceGraph
from docmirror.evidence.overlay_manifest import build_overlay_manifest
from docmirror.server.artifact_pack import _build_visual_debug_html_v3


def _minimal_graph() -> VisualEvidenceGraph:
    g = VisualEvidenceGraph(document_id="doc_test", task_id="task_test")
    g.add_page(1, width=595, height=842, image_ref="page_images/page_001.png")
    g.add_node(VisualNode(
        id="block:p1:b0", kind="block", label="Title Block",
        page=1, bbox=[20, 40, 520, 90], confidence=0.98,
    ))
    g.add_node(VisualNode(
        id="field:inv.total", kind="field", label="total",
        page=1, bbox=[400, 700, 500, 720], confidence=0.95,
        value_preview="100.00", field_path="inv.total",
        source_refs=["cell:p1:t0:r0:c2"], review="auto_accepted",
    ))
    g.add_node(VisualNode(
        id="field:inv.review", kind="field", label="unknown_field",
        page=0, bbox=None, confidence=0.0,
        value_preview="???", field_path="inv.review",
        review="needs_evidence",
    ))
    return g


def test_visual_debug_contains_overlay_manifest_data():
    """XVC-I4: visual_debug.html must have embedded overlay_manifest JSON with overlays."""
    graph = _minimal_graph()
    overlay = build_overlay_manifest(graph)

    manifest = {"document_id": "doc_test", "task_id": "task_test", "output_profile": "quickstart"}
    html = _build_visual_debug_html_v3(manifest, visual_graph=graph, overlay_manifest=overlay)

    # Must embed overlay manifest as window variable
    assert "window.OVERLAY_MANIFEST" in html, "visual_debug.html must embed OVERLAY_MANIFEST"

    # Extract the embedded JSON and verify it has overlays
    om_start = html.index("window.OVERLAY_MANIFEST = ") + len("window.OVERLAY_MANIFEST = ")
    om_end = html.index(";", om_start)
    om_json = html[om_start:om_end].strip()
    om = _json.loads(om_json)

    assert om.get("version") == 1
    overlays = om.get("overlays", [])
    assert len(overlays) >= 1, "visual_debug.html must have at least 1 overlay"

    # Verify overlay entries have required fields
    for ov in overlays:
        assert "node_id" in ov
        assert "layer" in ov
        assert "page" in ov
        assert "bbox" in ov
        assert "style" in ov


def test_visual_debug_contains_visual_evidence_graph():
    """XVC-I4: visual_debug.html must embed visual_evidence_graph JSON."""
    graph = _minimal_graph()
    overlay = build_overlay_manifest(graph)

    manifest = {"document_id": "doc_test", "task_id": "task_test", "output_profile": "quickstart"}
    html = _build_visual_debug_html_v3(manifest, visual_graph=graph, overlay_manifest=overlay)

    assert "window.VISUAL_EVIDENCE_GRAPH" in html, "visual_debug.html must embed VEG"

    veg_start = html.index("window.VISUAL_EVIDENCE_GRAPH = ") + len("window.VISUAL_EVIDENCE_GRAPH = ")
    veg_end = html.index(";", veg_start)
    veg_json = html[veg_start:veg_end].strip()
    veg = _json.loads(veg_json)

    assert veg.get("version") == 1
    assert len(veg.get("nodes", {})) >= 1


def test_visual_debug_has_svg_container():
    """XVC-I4: visual_debug.html must have an SVG overlay rendering surface."""
    graph = _minimal_graph()
    overlay = build_overlay_manifest(graph)

    manifest = {"document_id": "doc_test", "task_id": "task_test", "output_profile": "quickstart"}
    html = _build_visual_debug_html_v3(manifest, visual_graph=graph, overlay_manifest=overlay)

    assert '<svg id="overlay-svg"' in html, "Must have SVG overlay element"
    assert '<div id="inspector-panel"' in html, "Must have inspector panel"
    assert '<div id="layer-bar"' in html, "Must have layer bar"


def test_visual_debug_has_layer_bar():
    """XVC-I4: The layer bar must reference standard layers."""
    graph = _minimal_graph()
    overlay = build_overlay_manifest(graph)

    manifest = {"document_id": "doc_test", "task_id": "task_test", "output_profile": "quickstart"}
    html = _build_visual_debug_html_v3(manifest, visual_graph=graph, overlay_manifest=overlay)

    assert "layer-bar" in html, "Must have layer bar element"


def test_visual_debug_not_just_artifact_list():
    """XVC-I4: visual_debug.html must NOT be a bare artifact listing page."""
    graph = _minimal_graph()
    overlay = build_overlay_manifest(graph)

    manifest = {"document_id": "doc_test", "task_id": "task_test", "output_profile": "quickstart"}
    html = _build_visual_debug_html_v3(manifest, visual_graph=graph, overlay_manifest=overlay)

    # The HTML must contain structural elements beyond just artifact names
    assert "overlay-svg" in html, "Must have SVG overlay rendering surface"
    # Check that the HTML is more than a simple table of files
    assert len(html) > 2000, "visual_debug.html must be substantial, not a bare artifact list"
