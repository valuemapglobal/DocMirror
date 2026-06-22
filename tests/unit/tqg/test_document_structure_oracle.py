# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for DocumentStructure TQG oracle."""

from __future__ import annotations

from docmirror.eval.tqg.document_structure_oracles import run_document_structure_oracle
from docmirror.models.entities.parse_result import DocumentSection, LogicalTable, ParseResult


def test_document_structure_oracle_requires_outline_and_flow():
    result = ParseResult(
        sections=[DocumentSection(id="s1", title="Transactions", page_start=1, page_end=2)],
        logical_tables=[LogicalTable(table_id="lt1", source_pages=[1, 2], merge_confidence=0.9)],
    )

    report = run_document_structure_oracle(
        result,
        {"min_outline_nodes": 1, "min_flows": 1, "require_flow_types": ["cross_page_table"]},
    )

    assert report.passed, report.failures
