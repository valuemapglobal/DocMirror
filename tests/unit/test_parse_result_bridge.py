# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bridge single-point tests (design 09 Phase 1)."""

from __future__ import annotations

import pytest

from docmirror.input.bridge.parse_result_bridge import ParseResultBridge
from docmirror.models.entities.domain import BaseResult, Block, PageLayout


class TestParseResultBridge:
    def test_from_base_result_roundtrip_pages(self):
        block = Block(
            block_type="table",
            raw_content=[["日期", "金额"], ["2024-01-01", "100.00"]],
            page=1,
            reading_order=0,
        )
        page = PageLayout(page_number=1, blocks=(block,))
        base = BaseResult(pages=(page,), full_text="", metadata={})

        pr = ParseResultBridge.from_base_result(base)
        assert len(pr.pages) == 1
        assert len(pr.pages[0].tables) == 1
        assert pr.pages[0].tables[0].rows

    def test_bridge_lives_in_core_bridge(self):
        import docmirror.input.bridge.parse_result_bridge as bridge_mod

        assert hasattr(bridge_mod, "ParseResultBridge")

    def test_logical_table_metadata_rows_get_provenance_fallback(self):
        base = BaseResult(
            pages=(),
            full_text="",
            metadata={
                "_logical_tables": [
                    {
                        "logical_id": "lt_0",
                        "headers": ["A"],
                        "rows": [{"cells": [{"text": "1"}]}],
                        "source_pages": [3],
                        "source_physical_ids": ["pt_3_0"],
                        "page_span": [3, 3],
                        "row_count": 1,
                    }
                ]
            },
        )

        pr = ParseResultBridge.from_base_result(base)

        row = pr.logical_tables[0].rows[0]
        assert row.source_page == 3
        assert row.source_physical_id == "pt_3_0"
        assert row.source_row_index == 0

    def test_physical_table_layer_falls_back_to_extraction_audit(self):
        block = Block(
            block_type="table",
            raw_content=[["A"], ["1"]],
            page=1,
            reading_order=0,
        )
        page = PageLayout(page_number=1, blocks=(block,))
        base = BaseResult(
            pages=(page,),
            full_text="",
            metadata={
                "perf_breakdown": {
                    "extraction_audit": {
                        "pages": [
                            {
                                "page": 1,
                                "picked": "word_anchors",
                                "score": 0.9,
                            }
                        ]
                    }
                }
            },
        )

        pr = ParseResultBridge.from_base_result(base)
        table = pr.pages[0].tables[0]

        assert table.extraction_layer == "word_anchors"
        assert table.extraction_confidence == 0.9

    def test_scanned_meta_converts_to_page_evidence_bundles(self):
        base = BaseResult(
            pages=(),
            full_text="",
            metadata={
                "scanned_micro_grid_evidence": [{"page": 4, "lines": [{"content": "x"}], "tokens": []}],
                "scanned_local_structure_evidence": [{"page": 4, "structures": [{"structure_id": "ls_p4_0"}]}],
            },
        )

        pr = ParseResultBridge.from_base_result(base)
        ds = pr.entities.domain_specific

        assert "_scanned_micro_grid_evidence" not in ds
        assert "_scanned_local_structure_evidence" not in ds
        bundles = ds.get("_page_evidence_bundles") or []
        assert len(bundles) == 1
        assert bundles[0]["micro_grid_evidence"]["lines"]
        assert bundles[0]["local_structure_evidence"]["structures"]

    @pytest.mark.asyncio
    async def test_extract_parse_result_delegates_to_bridge(self, tmp_path):
        from unittest.mock import AsyncMock, patch

        from docmirror.input.extraction.extractor import CoreExtractor
        from docmirror.models.entities.parse_result import ParseResult

        pdf = tmp_path / "empty.pdf"
        pdf.write_bytes(b"%PDF-1.4 minimal")

        mock_base = BaseResult(pages=(), metadata={})
        mock_pr = ParseResult()

        extractor = CoreExtractor()
        with patch.object(extractor, "extract", AsyncMock(return_value=mock_base)):
            with patch.object(
                ParseResultBridge, "from_base_result", return_value=mock_pr
            ) as bridge_mock:
                result = await extractor.extract_parse_result(pdf)
                bridge_mock.assert_called_once_with(mock_base)
                assert result is mock_pr


def test_to_mirror_json_vnext_serializes_document_sections():
    import json

    from docmirror.models.entities.parse_result import DocumentSection, ParseResult

    pr = ParseResult(
        sections=[
            DocumentSection(id="1", title="Account summary", page_start=1, level=1, line_count=12),
        ],
    )
    pr.entities.document_type = "bank_statement"
    api = pr.to_mirror_json_vnext()
    json.dumps(api, ensure_ascii=False)
    assert "sections" not in api
    sections = api["source"]["provenance"]["sections"]
    assert sections[0]["title"] == "Account summary"
    assert sections[0]["level"] == 1
