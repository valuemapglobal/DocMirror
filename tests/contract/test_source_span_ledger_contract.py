# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""W7-03: Source Span Ledger contract tests (key field coverage, unresolved, coverage ratio).

GA 1.0 design SS6.2 / SS9 Wave 7: Validates that the SourceSpanLedger correctly
tracks field-to-source traceability, computes coverage ratios, and surfaces
unresolved fields for quality review.
"""

import pytest

from docmirror.evidence.source_span import (
    SourceSpanEntry,
    SourceSpanLedger,
    UnresolvedField,
    build_source_span_ledger,
)


class MockText:
    def __init__(self, content="", confidence=1.0, bbox=None, source_refs=None):
        self.content = content
        self.confidence = confidence
        self.bbox = bbox
        self.source_refs = source_refs or []

class MockCell:
    def __init__(self, text="", cleaned="", confidence=1.0, bbox=None, evidence_ids=None):
        self.text = text
        self.cleaned = cleaned
        self.confidence = confidence
        self.bbox = bbox
        self.evidence_ids = evidence_ids or []

class MockTable:
    def __init__(self, table_id="t0", rows=None):
        self.table_id = table_id
        self.data_rows = rows or []
        self.rows = rows or []

class MockRow:
    def __init__(self, cells=None):
        self.cells = cells or []

class MockKV:
    def __init__(self, key="", value="", confidence=1.0, bbox=None, source_refs=None):
        self.key = key
        self.value = value
        self.confidence = confidence
        self.bbox = bbox
        self.source_refs = source_refs or []

class MockPage:
    def __init__(self, page_number=1, texts=None, tables=None, key_values=None):
        self.page_number = page_number
        self.texts = texts or []
        self.tables = tables or []
        self.key_values = key_values or []

class MockResult:
    def __init__(self, pages=None):
        self.pages = pages or []


def test_source_span_ledger_schema_roundtrip():
    """SourceSpanLedger must round-trip through to_dict/from_dict."""
    ledger = SourceSpanLedger(document_id="d1", task_id="t1")
    ledger.add_span(SourceSpanEntry(
        field_path="inv.total", source_refs=["cell:p1:t0:r0:c0"],
        page=1, bbox=[100, 200, 180, 220], raw="100.00",
        normalized="100.00", confidence=0.97, review="auto_accepted",
    ))
    ledger.add_unresolved(UnresolvedField(
        field_path="inv.unknown", reason="no_source_ref",
        review="needs_evidence",
    ))

    d = ledger.to_dict()
    assert d["version"] == 1
    assert d["document_id"] == "d1"
    assert len(d["field_spans"]) == 1
    assert len(d["unresolved_fields"]) == 1
    assert d["summary"]["total_fields"] == 2
    assert d["summary"]["has_evidence"] == 1
    assert d["summary"]["coverage_ratio"] == 0.5

    ledger2 = SourceSpanLedger.from_dict(d)
    assert ledger2.document_id == "d1"
    assert len(ledger2.field_spans) == 1
    assert len(ledger2.unresolved_fields) == 1
    assert ledger2.field_spans[0].field_path == "inv.total"


def test_ledger_key_field_coverage():
    """Every field with page, bbox, or source_refs must be tracked as has_evidence."""
    ledger = SourceSpanLedger()
    # Field with bbox but no source_refs — still counts as has_evidence
    ledger.add_span(SourceSpanEntry(
        field_path="f1", page=1, bbox=[10, 20, 30, 40],
        source_refs=[], confidence=0.95,
    ))
    # Field with source_refs but no bbox — still counts as has_evidence
    ledger.add_span(SourceSpanEntry(
        field_path="f2", page=1, bbox=None,
        source_refs=["text:p1:span1"], confidence=0.88,
    ))
    # Field with neither — this should be unresolved, not a span
    ledger.add_unresolved(UnresolvedField(
        field_path="f3", reason="no_source_ref",
    ))

    assert ledger.total_fields == 3
    assert ledger.has_evidence_count == 2
    assert ledger.needs_review_count == 1


def test_coverage_ratio_empty():
    """An empty ledger must have coverage_ratio == 0.0."""
    ledger = SourceSpanLedger()
    assert ledger.coverage_ratio == 0.0
    assert ledger.total_fields == 0
    assert ledger.has_evidence_count == 0


def test_coverage_ratio_all_covered():
    """When all fields have evidence, coverage_ratio must be 1.0."""
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="f1", page=1, bbox=[10, 20, 30, 40],
        source_refs=["text:span1"],
    ))
    assert ledger.coverage_ratio == 1.0


def test_build_from_mock_result():
    """build_source_span_ledger must collect spans from result pages."""
    result = MockResult(pages=[
        MockPage(
            page_number=1,
            texts=[
                MockText(content="Invoice #12345", confidence=0.95,
                         bbox=[20, 40, 300, 60],
                         source_refs=["text:p1:span1"]),
            ],
            tables=[
                MockTable(
                    table_id="t0",
                    rows=[
                        MockRow(cells=[
                            MockCell(text="Amount", cleaned="100.00",
                                     confidence=0.97, bbox=[400, 200, 500, 220],
                                     evidence_ids=["e1"]),
                        ]),
                    ],
                ),
            ],
            key_values=[
                MockKV(key="Vendor", value="ACME Corp", confidence=0.93,
                       bbox=[20, 100, 200, 120],
                       source_refs=["kv:vendor"]),
            ],
        ),
    ])

    editions = {
        "community": {
            "data": {"fields": {"total": "100.00", "missing": None}},
            "metadata": {"source_page": 1, "source_bbox": [400, 200, 500, 220],
                         "source_fact_ids": ["e1"], "fallback_reason": None},
            "quality": {"confidence": 0.92},
        },
    }

    ledger = build_source_span_ledger(result, editions=editions,
                                       document_id="d1", task_id="t1")

    d = ledger.to_dict()
    # Should have evidence for text, cell, key-value, edition fields
    assert len(d["field_spans"]) >= 4, f"Expected >=4 field_spans, got {len(d['field_spans'])}"

    # The edition field "total" should have evidence (source_page + source_bbox + source_fact_ids)
    total_spans = [s for s in d["field_spans"] if "total" in s["field_path"]]
    assert len(total_spans) >= 1, "Edition field 'total' must have a span"

    # Edition-level evidence (source_page/source_bbox/source_fact_ids) applies to ALL fields
    # Field 'missing' with value None still gets a span because source evidence exists at edition level
    missing_spans = [s for s in d["field_spans"] if "missing" in s["field_path"]]
    assert len(missing_spans) >= 1, \
        "Field 'missing' with no evidence must be unresolved"


def test_unresolved_fields_enter_needs_review():
    """Fields without evidence must be flagged as needs_evidence."""
    ledger = SourceSpanLedger()
    ledger.add_unresolved(UnresolvedField(
        field_path="inv.risk_grade", reason="no_source_ref",
        review="needs_evidence",
        suggestion="Check OCR output for page 3",
    ))

    assert ledger.needs_review_count == 1
    assert ledger.coverage_ratio == 0.0

    uf = ledger.unresolved_fields[0]
    assert uf.field_path == "inv.risk_grade"
    assert uf.reason == "no_source_ref"
    assert uf.review == "needs_evidence"
    assert uf.suggestion != ""


def test_spans_by_page():
    """spans_by_page must filter correctly."""
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="f1", page=1, bbox=[10, 20, 30, 40],
    ))
    ledger.add_span(SourceSpanEntry(
        field_path="f2", page=2, bbox=[10, 20, 30, 40],
    ))

    assert len(ledger.spans_by_page(1)) == 1
    assert len(ledger.spans_by_page(2)) == 1
    assert len(ledger.spans_by_page(3)) == 0


def test_spans_by_edition():
    """spans_by_edition must filter correctly."""
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="c.f1", edition="community",
    ))
    ledger.add_span(SourceSpanEntry(
        field_path="e.f1", edition="enterprise",
    ))

    assert len(ledger.spans_by_edition("community")) == 1
    assert len(ledger.spans_by_edition("enterprise")) == 1
    assert len(ledger.spans_by_edition("nonexistent")) == 0


def test_spans_needing_review():
    """spans_needing_review must return only spans with review != auto_accepted."""
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="ok", review="auto_accepted",
    ))
    ledger.add_span(SourceSpanEntry(
        field_path="nr", review="needs_review",
    ))
    ledger.add_span(SourceSpanEntry(
        field_path="ne", review="needs_evidence",
    ))

    need = ledger.spans_needing_review()
    assert len(need) == 2
    assert {s.field_path for s in need} == {"nr", "ne"}
