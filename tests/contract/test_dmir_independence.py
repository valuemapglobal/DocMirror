# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Contract test: DMIR serialization does NOT mutate ParseResult.

This test verifies the fundamental invariant of ODL-06:
  serialize_dmir() is READ-ONLY on ParseResult.
  All existing outputs (mirror, community, enterprise, finance)
  remain identical whether or not DMIR is serialized.
"""

from __future__ import annotations

import copy
import json

import pytest

pytestmark = [pytest.mark.tier_contract]

from docmirror.models.entities.parse_result import (
    CellValue,
    DataType,
    DocumentEntities,
    ExtractionMethod,
    PageContent,
    ParseResult,
    ParserInfo,
    ResultStatus,
    RowType,
    TableBlock,
    TableRow,
    TextBlock,
    TextLevel,
    TrustResult,
)
from docmirror.output.dmir import serialize_dmir, serialize_dmir_json


def _full_parse_result() -> ParseResult:
    """Create a realistic ParseResult with pages, tables, and metadata."""
    pr = ParseResult(
        status=ResultStatus.SUCCESS,
        confidence=0.95,
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                texts=[
                    TextBlock(
                        content="Account Statement",
                        level=TextLevel.TITLE,
                        bbox=[50.0, 30.0, 545.0, 60.0],
                        evidence_ids=["evt_001"],
                    ),
                    TextBlock(
                        content="Period: Jan-Jun 2026",
                        level=TextLevel.BODY,
                        bbox=[50.0, 70.0, 300.0, 85.0],
                        evidence_ids=["evt_002"],
                    ),
                ],
                tables=[
                    TableBlock(
                        table_id="tbl_001",
                        headers=["Date", "Description", "Amount"],
                        rows=[
                            TableRow(
                                cells=[
                                    CellValue(text="2026-01-15", cleaned="2026-01-15",
                                              bbox=[50, 100, 150, 115], confidence=0.98),
                                    CellValue(text="Wire transfer", cleaned="Wire transfer",
                                              bbox=[160, 100, 300, 115], confidence=0.97),
                                    CellValue(text="2,970.00", cleaned="2970.00",
                                              numeric=2970.0, bbox=[310, 100, 400, 115], confidence=0.99),
                                ]
                            ),
                            TableRow(
                                cells=[
                                    CellValue(text="2026-01-14", cleaned="2026-01-14",
                                              bbox=[50, 120, 150, 135], confidence=0.98),
                                    CellValue(text="Check deposit", cleaned="Check deposit",
                                              bbox=[160, 120, 300, 135], confidence=0.96),
                                    CellValue(text="500.00", cleaned="500.00",
                                              numeric=500.0, bbox=[310, 120, 400, 135], confidence=0.99),
                                ]
                            ),
                        ],
                        bbox=[30.0, 95.0, 565.0, 200.0],
                        extraction_layer="vector_table",
                        extraction_confidence=0.95,
                        evidence_ids=["evt_003"],
                    )
                ],
            )
        ],
        total_tables=1,
        total_rows=2,
        parser_info=ParserInfo(
            parser_name="DocMirror",
            parser_version="1.0.0",
            elapsed_ms=42.5,
            page_count=1,
            extraction_method=ExtractionMethod.DIGITAL,
            table_engine="pymupdf",
            overall_confidence=0.95,
            warnings=[],
        ),
        entities=DocumentEntities(
            document_type="bank_statement",
            organization="Test Bank",
            subject_name="Acme Corp",
            subject_id="ACME-001",
            document_date="2026-01-15",
            period_start="2026-01-01",
            period_end="2026-06-01",
        ),
        raw_text="Account Statement\nPeriod: Jan-Jun 2026\nDate Description Amount\n2026-01-15 Wire transfer 2,970.00",
    )
    pr.trust = TrustResult(
        trust_score=0.92,
        validation_passed=True,
        is_forged=False,
        forgery_reasons=[],
    )
    return pr


class TestDMIRDoesNotMutateParseResult:
    """Verify serialize_dmir() is read-only on ParseResult."""

    def test_dmir_preserves_page_count(self):
        result = _full_parse_result()
        orig = len(result.pages)
        serialize_dmir(result)
        assert len(result.pages) == orig

    def test_dmir_preserves_entity_fields(self):
        result = _full_parse_result()
        orig = (result.entities.document_type, result.entities.organization)
        serialize_dmir(result)
        assert result.entities.document_type == orig[0]
        assert result.entities.organization == orig[1]

    def test_dmir_preserves_table_structure(self):
        result = _full_parse_result()
        orig_h = list(result.pages[0].tables[0].headers)
        orig_r = len(result.pages[0].tables[0].rows)
        serialize_dmir(result)
        assert result.pages[0].tables[0].headers == orig_h
        assert len(result.pages[0].tables[0].rows) == orig_r

    def test_dmir_preserves_cell_values(self):
        result = _full_parse_result()
        cell = result.pages[0].tables[0].rows[0].cells[0]
        orig = (cell.text, cell.cleaned, cell.confidence)
        serialize_dmir(result)
        assert cell.text == orig[0]
        assert cell.cleaned == orig[1]
        assert cell.confidence == orig[2]

    def test_dmir_preserves_confidence(self):
        result = _full_parse_result()
        orig = result.confidence
        serialize_dmir(result)
        assert result.confidence == orig

    def test_dmir_preserves_trust_fields(self):
        result = _full_parse_result()
        orig = (result.trust.trust_score, result.trust.validation_passed)
        serialize_dmir(result)
        assert result.trust.trust_score == orig[0]
        assert result.trust.validation_passed == orig[1]

    def test_dmir_preserves_parser_info(self):
        result = _full_parse_result()
        orig = (result.parser_info.parser_name, result.parser_info.parser_version)
        serialize_dmir(result)
        assert result.parser_info.parser_name == orig[0]
        assert result.parser_info.parser_version == orig[1]

    def test_dmir_preserves_pages_reference(self):
        result = _full_parse_result()
        pid = id(result.pages)
        serialize_dmir(result)
        assert id(result.pages) == pid


class TestDMIRDeterminism:
    """DMIR output is deterministic and idempotent."""

    def test_same_parse_result_same_dmir(self):
        r1 = _full_parse_result()
        r2 = _full_parse_result()
        assert serialize_dmir_json(r1, indent=2) == serialize_dmir_json(r2, indent=2)

    def test_multiple_calls_idempotent(self):
        result = _full_parse_result()
        dmir1 = serialize_dmir(result)
        serialize_dmir(result)
        serialize_dmir(result)
        dmir_final = serialize_dmir(result)
        assert json.dumps(dmir1, sort_keys=True) == json.dumps(dmir_final, sort_keys=True)

    def test_build_projections_unchanged_after_dmir(self):
        from docmirror.models.sealed import seal_parse_result
        from docmirror.server.output_builder import build_all_projections
        r1 = _full_parse_result()
        r2 = _full_parse_result()
        p1 = build_all_projections(seal_parse_result(r1), file_path="test.pdf")
        serialize_dmir(r2)
        p2 = build_all_projections(seal_parse_result(r2), file_path="test.pdf")
        assert "dmir" not in p1
        assert "dmir" not in p2
        # Strip non-deterministic fields (timestamp) before comparison
        for d in [p1["mirror"], p2["mirror"]]:
            d.pop("timestamp", None)
        assert p1["mirror"] == p2["mirror"]

    def test_dmir_schema_version_stable(self):
        result = _full_parse_result()
        dmir = serialize_dmir(result)
        assert dmir["dmir_version"] == "1.0"
        assert dmir["meta"]["dmir_version"] == "1.0"

    def test_no_dmir_reference_in_server_code(self):
        """Normal delivery must never import the on-demand DMIR serializer."""
        import docmirror.server.edition_outputs as eo
        import docmirror.server.output_builder as ob
        src1 = open(ob.__file__).read()
        src2 = open(eo.__file__).read()
        assert "serialize_dmir" not in src1
        assert "serialize_dmir" not in src2
