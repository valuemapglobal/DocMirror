# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bank statement UMMA blocks oracle (Design 20 residual)."""

from __future__ import annotations

from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, TextBlock, TextLevel
from docmirror.models.entities.parse_result import TableBlock, TableRow, CellValue


def test_bank_statement_page_has_s2_block_no_regions():
    table = TableBlock(
        table_id="pt_1_0",
        headers=["交易时间", "收入金额", "支出金额", "账户余额"],
        rows=[TableRow(cells=[CellValue(text="2024-01-01")])],
        page=1,
        bbox=(48, 90, 560, 780),
    )
    pr = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                texts=[TextBlock(content="账户交易明细", bbox=(72, 48, 400, 72), level=TextLevel.BODY)],
                tables=[table],
            )
        ],
        entities=DocumentEntities(document_type="bank_statement", content_type="table_dominant"),
    )
    pr.sync_page_canvases()
    canvas = pr.pages[0].page_canvas
    assert canvas is not None
    assert len(canvas.regions) == 0
    assert len(canvas.blocks) >= 1
    s2_blocks = [b for b in canvas.blocks if b.morphology == "S2"]
    assert s2_blocks
    assert s2_blocks[0].ref == "table:pt_1_0"

    api = pr.to_api_dict(mirror_level="standard")
    page = api["data"]["document"]["pages"][0]
    assert page.get("regions") == []
    assert any(b.get("morphology") == "S2" for b in page.get("blocks") or [])
