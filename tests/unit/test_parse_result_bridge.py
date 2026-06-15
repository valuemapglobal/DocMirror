# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bridge single-point tests (design 09 Phase 1)."""

from __future__ import annotations

import pytest

from docmirror.core.bridge.parse_result_bridge import ParseResultBridge
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
        import docmirror.core.bridge.parse_result_bridge as bridge_mod

        assert hasattr(bridge_mod, "ParseResultBridge")

    @pytest.mark.asyncio
    async def test_extract_parse_result_delegates_to_bridge(self, tmp_path):
        from unittest.mock import AsyncMock, patch

        from docmirror.core.extraction.extractor import CoreExtractor
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


def test_to_api_dict_serializes_document_sections():
    import json

    from docmirror.models.entities.parse_result import DocumentSection, ParseResult

    pr = ParseResult(
        sections=[
            DocumentSection(id="1", title="Account summary", page_start=1, level=1, line_count=12),
        ],
    )
    pr.entities.document_type = "bank_statement"
    api = pr.to_api_dict()
    json.dumps(api, ensure_ascii=False)
    sections = api["data"]["document"]["sections"]
    assert sections[0]["title"] == "Account summary"
    assert sections[0]["level"] == 1
