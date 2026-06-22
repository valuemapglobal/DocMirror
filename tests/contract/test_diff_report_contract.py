# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""W7-04: Diff Report contract tests.

GA 1.0 design SS6.4 / SS9 Wave 7: Validates that diff_graphs produces
a correct DiffReport with changed nodes, severity ratings, visual diff
overlay data, and a gate summary.
"""

import json as _json

import pytest

from docmirror.models.visual_evidence import VisualNode, VisualEdge, VisualEvidenceGraph
from docmirror.evidence.diff_canonicalizer import (
    canonicalize_visual_graph,
    canonicalize_source_span_ledger,
    canonicalize_quality_decision,
)
from docmirror.evidence.diff_engine import DiffChange, DiffReport, diff_graphs
from docmirror.evidence.source_span import (
    SourceSpanEntry, SourceSpanLedger, UnresolvedField,
)
from docmirror.evidence.quality_decision import QualityDecisionReport, ReviewItem


def _base_graph() -> dict:
    g = VisualEvidenceGraph(document_id="d1", task_id="t1")
    g.add_page(1, width=595, height=842, image_ref="page_001.png")
    g.add_node(VisualNode(id="block:p1:b0", kind="block", label="Header",
                           page=1, bbox=[20, 40, 520, 90], confidence=0.98))
    g.add_node(VisualNode(id="field:inv.total", kind="field", label="total",
                           page=1, bbox=[400, 700, 500, 720], confidence=0.95,
                           value_preview="100.00", field_path="inv.total",
                           source_refs=["cell:p1:c0"]))
    g.add_node(VisualNode(id="field:inv.unknown", kind="field", label="unknown",
                           page=0, bbox=None, confidence=0.0,
                           value_preview="???", field_path="inv.unknown",
                           review="needs_evidence"))
    g.add_edge(VisualEdge(id="e1", type="contains", from_node="block:p1:b0",
                           to_node="field:inv.total", confidence=1.0))
    return canonicalize_visual_graph(g)


def test_diff_report_schema_roundtrip():
    """DiffReport must round-trip through to_dict/from_dict."""
    report = DiffReport(
        base_run="run_a", candidate_run="run_b", status="warning",
        summary={"node_added": 2, "total_changes": 3},
        budgets={"allowed_high_severity_changes": 0},
    )
    report.changes.append(DiffChange(
        id="diff_001", kind="node_added", severity="medium",
        node_id="field:f1", field_path="inv.f1",
        after="100.00", source_refs=["cell:c1"],
        visual_nodes=["field:f1"], page=1,
        message="Node field:f1 added: 100.00",
    ))

    d = report.to_dict()
    assert d["version"] == 1
    assert d["base_run"] == "run_a"
    assert d["status"] == "warning"
    assert len(d["changes"]) == 1
    assert d["changes"][0]["id"] == "diff_001"
    assert d["changes"][0]["kind"] == "node_added"

    report2 = DiffReport.from_dict(d)
    assert report2.base_run == "run_a"
    assert report2.status == "warning"
    assert len(report2.changes) == 1
    assert report2.changes[0].kind == "node_added"


def test_diff_no_changes():
    """Identical graphs must produce status=pass with no changes."""
    base = _base_graph()
    cand = _base_graph()
    report = diff_graphs(base, cand, base_run="run_a", candidate_run="run_b")

    assert report.status == "pass"
    assert report.summary["total_changes"] == 0
    assert len(report.changes) == 0


def test_diff_node_added():
    """A node only in candidate must be flagged as node_added."""
    base = _base_graph()
    cand = _base_graph()
    cand["nodes"]["field:inv.new"] = {
        "id": "field:inv.new", "kind": "field", "label": "new_field",
        "page": 1, "bbox": [10, 20, 30, 40], "confidence": 0.9,
        "value_preview": "42", "field_path": "inv.new",
    }

    report = diff_graphs(base, cand)
    assert report.status == "warning"
    added = [c for c in report.changes if c.kind == "node_added"]
    assert len(added) == 1
    assert added[0].node_id == "field:inv.new"


def test_diff_node_removed():
    """A node only in base must be flagged as node_removed."""
    base = _base_graph()
    cand = _base_graph()
    del cand["nodes"]["field:inv.unknown"]

    report = diff_graphs(base, cand)
    removed = [c for c in report.changes if c.kind == "node_removed"]
    assert len(removed) == 1
    assert removed[0].node_id == "field:inv.unknown"
    # field nodes should have medium severity
    assert removed[0].severity == "medium"


def test_diff_field_value_changed():
    """Value change on a field must be flagged as field_value_changed with high severity."""
    base = _base_graph()
    cand = _base_graph()
    cand["nodes"]["field:inv.total"]["value_preview"] = "200.00"

    report = diff_graphs(base, cand)
    field_changes = [c for c in report.changes if c.kind == "field_value_changed"]
    assert len(field_changes) == 1
    assert field_changes[0].severity == "high"
    assert field_changes[0].node_id == "field:inv.total"


def test_diff_confidence_changed():
    """Confidence drop > 0.2 must be high severity."""
    base = _base_graph()
    cand = _base_graph()
    cand["nodes"]["field:inv.total"]["confidence"] = 0.5

    report = diff_graphs(base, cand)
    conf_changes = [c for c in report.changes if c.kind == "confidence_changed"]
    assert len(conf_changes) == 1
    assert conf_changes[0].severity == "high"  # delta 0.45 > 0.2


def test_diff_bbox_changed():
    """BBox change must be flagged with diff overlay data."""
    base = _base_graph()
    cand = _base_graph()
    cand["nodes"]["field:inv.total"]["bbox"] = [410, 710, 510, 730]

    report = diff_graphs(base, cand)
    bbox_changes = [c for c in report.changes if c.kind == "bbox_changed"]
    assert len(bbox_changes) == 1

    # Must produce diff overlay entry for bbox change
    assert len(report.diff_overlay) >= 1
    overlay = report.diff_overlay[0]
    assert overlay["node_id"] == "field:inv.total"
    assert overlay["kind"] == "bbox_changed"
    assert "style" in overlay


def test_diff_edge_changes():
    """Edge additions and removals must be tracked."""
    base = _base_graph()
    cand = _base_graph()

    # Add a new edge
    cand["edges"].append({
        "id": "e_new", "type": "derived_from",
        "from": "field:inv.total", "to": "field:inv.unknown",
        "confidence": 0.5,
    })

    report = diff_graphs(base, cand)
    edge_added = [c for c in report.changes if c.kind == "edge_added"]
    assert len(edge_added) == 1

    # Remove the original edge
    cand2 = _base_graph()
    cand2["edges"] = []
    report2 = diff_graphs(base, cand2)
    edge_removed = [c for c in report2.changes if c.kind == "edge_removed"]
    assert len(edge_removed) == 1


def test_diff_quality_decision_changed():
    """Quality decision change must be high severity."""
    base = _base_graph()
    cand = _base_graph()

    base["quality_decision"] = {"decision": "auto_ingest"}
    cand["quality_decision"] = {"decision": "needs_review"}

    report = diff_graphs(base, cand)
    qd_changes = [c for c in report.changes if c.kind == "quality_decision_changed"]
    assert len(qd_changes) == 1
    assert qd_changes[0].severity == "high"


def test_diff_status_high_severity_fail():
    """High severity changes exceeding budget must result in fail status."""
    base = _base_graph()
    cand = _base_graph()
    cand["nodes"]["field:inv.total"]["value_preview"] = "999.99"  # high severity

    report = diff_graphs(base, cand, budgets={"allowed_high_severity_changes": 0})
    assert report.status == "fail"


def test_canonicalize_sorts_and_rounds():
    """canonicalize_visual_graph must sort nodes, edges, pages and round bbox."""
    g = VisualEvidenceGraph(document_id="d1")
    g.add_page(2, width=595, height=842)
    g.add_page(1, width=595, height=842)
    g.add_node(VisualNode(id="z", kind="block", page=1, bbox=[10.123456, 20.654321, 30.0, 40.0]))
    g.add_node(VisualNode(id="a", kind="block", page=1, bbox=[1.0, 2.0, 3.0, 4.0]))

    c = canonicalize_visual_graph(g)
    # Nodes must be sorted by id
    node_ids = list(c["nodes"].keys())
    assert node_ids == ["a", "z"]
    # Pages must be sorted by page number
    assert c["pages"][0]["page"] == 1
    assert c["pages"][1]["page"] == 2
    # BBox must be rounded to 2 decimal places
    assert c["nodes"]["a"]["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert c["nodes"]["z"]["bbox"] == [10.12, 20.65, 30.0, 40.0]


def test_canonicalize_source_span_ledger():
    """canonicalize_source_span_ledger must sort spans and round floats."""
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="z.last", bbox=[10.123, 20.456, 30.789, 40.012],
        confidence=0.95678,
    ))
    ledger.add_span(SourceSpanEntry(
        field_path="a.first", bbox=[1.0, 2.0, 3.0, 4.0],
        confidence=0.12345,
    ))
    ledger.add_unresolved(UnresolvedField(
        field_path="b.missing", reason="no_source_ref",
    ))

    c = canonicalize_source_span_ledger(ledger)
    # Spans sorted by field_path
    assert c["field_spans"][0]["field_path"] == "a.first"
    assert c["field_spans"][1]["field_path"] == "z.last"
    # Unresolved sorted by field_path
    assert c["unresolved_fields"][0]["field_path"] == "b.missing"
    # BBox rounded
    assert c["field_spans"][1]["bbox"] == [10.12, 20.46, 30.79, 40.01]
    # Confidence rounded to 4 places
    assert c["field_spans"][1]["confidence"] == 0.9568
    assert c["field_spans"][0]["confidence"] == 0.1235


def test_canonicalize_quality_decision():
    """canonicalize_quality_decision must sort needs_review items."""
    qd = QualityDecisionReport(
        decision="needs_review",
        decision_reason="low_coverage",
        confidence_policy="ga_default_v1",
    )
    qd.needs_review.append(ReviewItem(
        field_path="z.field", node_id="z", reason="low_confidence",
    ))
    qd.needs_review.append(ReviewItem(
        field_path="a.field", node_id="a", reason="no_evidence",
    ))

    c = canonicalize_quality_decision(qd)
    assert c["decision"] == "needs_review"
    assert c["needs_review"][0]["field_path"] == "a.field"
    assert c["needs_review"][1]["field_path"] == "z.field"


def test_diff_report_has_source_refs():
    """Changed nodes must carry source_refs for traceability."""
    base = _base_graph()
    cand = _base_graph()
    cand["nodes"]["field:inv.total"]["value_preview"] = "999.99"

    report = diff_graphs(base, cand)
    field_changes = [c for c in report.changes if c.kind == "field_value_changed"]
    assert len(field_changes) == 1
    assert "cell:p1:c0" in field_changes[0].source_refs, \
        "Changed node must carry source_refs for explainability"
