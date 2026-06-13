# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""transaction_row_count metric tests."""

from __future__ import annotations

from docmirror.core.evaluation.metrics import compute_metrics, transaction_row_count
from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, TableBlock, TableRow


def test_transaction_row_count_from_structured_data():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="bank_statement",
            domain_specific={"structured_data": {"transactions": [{"id": 1}, {"id": 2}, {"id": 3}]}},
        ),
        total_rows=0,
    )
    assert transaction_row_count(pr) == 3.0


def test_transaction_row_count_from_transaction_count_field():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="bank_statement",
            domain_specific={"structured_data": {"transaction_count": 5}},
        ),
        total_rows=1,
    )
    assert transaction_row_count(pr) == 5.0


def test_transaction_row_count_falls_back_to_total_rows():
    rows = [TableRow() for _ in range(12)]
    pr = ParseResult(
        entities=DocumentEntities(document_type="generic"),
        pages=[PageContent(page_number=1, tables=[TableBlock(rows=rows)])],
    )
    assert transaction_row_count(pr) == 12.0


def test_compute_metrics_includes_transaction_row_count():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="bank_statement",
            domain_specific={"structured_data": {"transactions": [{"a": 1}]}},
        ),
    )
    metrics = compute_metrics(pr)
    assert metrics["transaction_row_count"] == 1.0
