# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""W7-04: Quality Decision Report contract tests.

GA 1.0 design SS6.3 / SS9 Wave 7: Validates that build_quality_decision
correctly decides auto_ingest / needs_review / reject based on schema pass,
evidence coverage, confidence thresholds, and outcome events.
"""

import pytest

from docmirror.evidence.quality_decision import (
    QualityDecisionReport,
    ReviewItem,
    build_quality_decision,
)
from docmirror.evidence.source_span import (
    SourceSpanEntry,
    SourceSpanLedger,
    UnresolvedField,
)
from docmirror.models.visual_evidence import VisualEdge, VisualEvidenceGraph, VisualNode


def _clean_editions():
    return {
        "community": {
            "data": {"fields": {"total": "100.00", "vendor": "ACME"}},
            "metadata": {
                "source_page": 1,
                "source_bbox": [400, 200, 500, 220],
                "source_fact_ids": ["e1", "e2"],
                "support_level": "L1",
            },
            "quality": {"confidence": 0.94},
        },
    }


def test_quality_decision_schema_roundtrip():
    """QualityDecisionReport must round-trip through to_dict/from_dict."""
    qd = QualityDecisionReport(
        document_id="d1", task_id="t1",
        decision="auto_ingest",
        decision_reason="all_checks_passed",
        confidence_policy="ga_default_v1",
        summary={
            "text_fidelity": "pass",
            "layout_fidelity": "pass",
            "business_fidelity": "pass",
            "audit_fidelity": "pass",
        },
    )
    qd.needs_review.append(ReviewItem(
        scope="field", field_path="inv.unknown",
        node_id="field:inv.unknown", reason="low_confidence",
        confidence=0.3, page=2, bbox=[10, 20, 30, 40],
    ))

    d = qd.to_dict()
    assert d["version"] == 2
    assert d["decision"] == "auto_ingest"
    assert len(d["needs_review"]) == 1
    assert d["needs_review"][0]["field_path"] == "inv.unknown"

    qd2 = QualityDecisionReport.from_dict(d)
    assert qd2.decision == "auto_ingest"
    assert len(qd2.needs_review) == 1
    assert qd2.needs_review[0].field_path == "inv.unknown"


def test_auto_ingest_clean():
    """Clean editions with evidence must produce auto_ingest."""
    editions = _clean_editions()
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="community.data.fields.total", source_refs=["e1"],
        page=1, bbox=[400, 200, 500, 220], confidence=0.94,
    ))
    ledger.add_span(SourceSpanEntry(
        field_path="community.data.fields.vendor", source_refs=["e2"],
        page=1, bbox=[100, 200, 300, 220], confidence=0.92,
    ))

    graph = VisualEvidenceGraph(document_id="d1")
    graph.add_node(VisualNode(
        id="field:total", kind="field", label="total",
        page=1, bbox=[400, 700, 500, 720], confidence=0.94,
        field_path="community.data.fields.total",
        source_refs=["e1"], review="auto_accepted",
    ))

    qd = build_quality_decision(
        visual_graph=graph,
        source_span_ledger=ledger,
        editions=editions,
        document_id="d1", task_id="t1",
    )

    assert qd.decision == "auto_ingest"
    assert "key_fields_have_evidence" in qd.decision_reason or \
           "evidence" in qd.decision_reason.lower()


def test_needs_review_missing_evidence():
    """Fields without evidence must produce needs_review."""
    editions = _clean_editions()
    ledger = SourceSpanLedger()
    ledger.add_unresolved(UnresolvedField(
        field_path="community.data.fields.unknown",
        reason="no_source_ref",
    ))
    # No field_spans at all
    graph = VisualEvidenceGraph(document_id="d1")

    qd = build_quality_decision(
        visual_graph=graph,
        source_span_ledger=ledger,
        editions=editions,
        document_id="d1", task_id="t1",
    )

    assert qd.decision == "needs_review", \
        f"Expected needs_review, got {qd.decision}: {qd.decision_reason}"


def test_needs_review_low_coverage():
    """Coverage below 80% must produce needs_review."""
    editions = _clean_editions()
    ledger = SourceSpanLedger()
    # Only 1 of 10 fields has evidence
    ledger.add_span(SourceSpanEntry(
        field_path="f0", page=1, bbox=[10, 20, 30, 40],
    ))
    for i in range(1, 10):
        ledger.add_unresolved(UnresolvedField(
            field_path=f"f{i}", reason="no_source_ref",
        ))

    graph = VisualEvidenceGraph()

    qd = build_quality_decision(
        visual_graph=graph,
        source_span_ledger=ledger,
        editions=editions,
        document_id="d1", task_id="t1",
    )

    assert qd.decision == "needs_review"
    assert qd.metrics.get("span_coverage", 1.0) < 0.8


def test_needs_review_low_confidence():
    """Editions with low confidence must produce needs_review."""
    editions = {
        "community": {
            "data": {"fields": {"total": "100.00"}},
            "metadata": {"source_page": 1, "source_bbox": [400, 200, 500, 220],
                         "source_fact_ids": ["e1"]},
            "quality": {"confidence": 0.3},  # very low
        },
    }
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="community.data.fields.total", source_refs=["e1"],
        page=1, bbox=[400, 200, 500, 220], confidence=0.3,
        review="needs_review",
    ))

    graph = VisualEvidenceGraph()
    graph.add_node(VisualNode(
        id="field:total", kind="field", label="total",
        page=1, bbox=[400, 200, 500, 220], confidence=0.3,
        field_path="community.data.fields.total",
        source_refs=["e1"], review="needs_review",
    ))

    qd = build_quality_decision(
        visual_graph=graph,
        source_span_ledger=ledger,
        editions=editions,
        document_id="d1", task_id="t1",
        threshold_needs_review=0.5,
    )

    assert qd.decision == "needs_review"


def test_reject_schema_fail():
    """Schema failure must produce reject."""
    editions = {
        "community": {
            "data": {"fields": {}},
            "metadata": {},
            "quality": {},
            "status": {"status": "schema_fail"},
        },
    }
    ledger = SourceSpanLedger()
    graph = VisualEvidenceGraph()

    qd = build_quality_decision(
        visual_graph=graph,
        source_span_ledger=ledger,
        editions=editions,
        document_id="d1", task_id="t1",
    )

    assert qd.decision == "reject"
    assert "schema" in str(qd.blocking_issues).lower() or \
           "schema" in str(qd.decision_reason).lower()


def test_quality_decision_has_links():
    """Quality decision must link to other explainability artifacts."""
    editions = _clean_editions()
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="community.data.fields.total", source_refs=["e1"],
        page=1, bbox=[400, 200, 500, 220], confidence=0.94,
    ))

    graph = VisualEvidenceGraph()
    graph.add_node(VisualNode(
        id="field:total", kind="field", label="total",
        page=1, bbox=[400, 700, 500, 720], confidence=0.94,
        field_path="community.data.fields.total",
        source_refs=["e1"],
    ))

    qd = build_quality_decision(
        visual_graph=graph, source_span_ledger=ledger,
        editions=editions, document_id="d1", task_id="t1",
    )

    assert "visual_debug" in qd.links
    assert "visual_graph" in qd.links
    assert "source_span_ledger" in qd.links
    assert "support_bundle" in qd.links


def test_fidelity_summary():
    """Fidelity summary must reflect observed state, not static claims."""
    editions = _clean_editions()
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="community.data.fields.total", source_refs=["e1"],
        page=1, bbox=[400, 200, 500, 220], confidence=0.94,
    ))

    graph = VisualEvidenceGraph()
    graph.add_node(VisualNode(
        id="field:total", kind="field", label="total",
        page=1, bbox=[400, 700, 500, 720], confidence=0.94,
        field_path="community.data.fields.total",
        source_refs=["e1"],
    ))

    qd = build_quality_decision(
        visual_graph=graph, source_span_ledger=ledger,
        editions=editions, document_id="d1", task_id="t1",
    )

    assert "text_fidelity" in qd.summary
    assert "layout_fidelity" in qd.summary
    assert "business_fidelity" in qd.summary
    assert "audit_fidelity" in qd.summary
    # Must not be the default "not_measured" for fidelity dimensions that are observed
    assert qd.summary["text_fidelity"] in ("pass", "warning", "fail")


def test_review_items_have_page_and_bbox():
    """Review items from low confidence must carry page and bbox for inspector."""
    editions = _clean_editions()
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="community.data.fields.total", source_refs=["e1"],
        page=3, bbox=[100, 210, 180, 230], confidence=0.45,
        review="needs_review",
    ))

    graph = VisualEvidenceGraph()
    graph.add_node(VisualNode(
        id="field:total", kind="field", label="total",
        page=3, bbox=[100, 210, 180, 230], confidence=0.45,
        field_path="community.data.fields.total",
        source_refs=["e1"], review="needs_review",
    ))

    qd = build_quality_decision(
        visual_graph=graph, source_span_ledger=ledger,
        editions=editions, document_id="d1", task_id="t1",
        threshold_needs_review=0.6,
    )

    nr = qd.needs_review
    assert len(nr) >= 1
    for item in nr:
        if item.field_path == "community.data.fields.total":
            assert item.page == 3
            assert item.bbox == [100, 210, 180, 230]
            break
    else:
        pytest.fail("Expected a needs_review item for community.data.fields.total")


def test_quality_decision_no_static_silent_failure():
    """Quality decision must not contain 'silent_failure=false' static claim."""
    editions = _clean_editions()
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="community.data.fields.total", source_refs=["e1"],
        page=1, bbox=[400, 200, 500, 220], confidence=0.94,
    ))

    graph = VisualEvidenceGraph()
    graph.add_node(VisualNode(
        id="field:total", kind="field", label="total",
        page=1, bbox=[400, 700, 500, 720], confidence=0.94,
        field_path="community.data.fields.total",
        source_refs=["e1"],
    ))

    qd = build_quality_decision(
        visual_graph=graph, source_span_ledger=ledger,
        editions=editions, document_id="d1", task_id="t1",
    )

    d = qd.to_dict()
    text = str(d)
    assert "silent_failure" not in text.lower() or \
        "silent_failure=false" not in text, \
        "Quality decision must not contain static 'silent_failure=false' claim"
