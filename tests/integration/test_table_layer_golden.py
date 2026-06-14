# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Integration tests for table layer dual-view (design doc §10.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docmirror.core.table.compose.composer import TableComposer
from docmirror.models.entities.domain import Block, PageLayout


FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
ALIPAY_PDF = FIXTURES / "alipay_payment" / "DemoUser+支付宝流水.pdf"


def _page(page_number: int, rows: list[list[str]]) -> PageLayout:
    return PageLayout(
        page_number=page_number,
        blocks=(
            Block(
                block_id=f"p{page_number}_t0",
                block_type="table",
                raw_content=rows,
                page=page_number,
                reading_order=1,
            ),
        ),
    )


class TestTableLayerSynthetic:
    """Fast synthetic fixtures — no OCR."""

    def test_three_page_bank_ledger_logical_merge(self):
        pages = [
            _page(1, [["日期", "金额"], ["2024-01-01", "100"]]),
            _page(2, [["日期", "金额"], ["2024-01-02", "200"]]),
            _page(3, [["日期", "金额"], ["2024-01-03", "300"]]),
        ]
        logical = TableComposer.from_page_layouts(pages)
        assert len(logical) == 1
        assert logical[0].row_count == 3
        assert logical[0].source_pages == [1, 2, 3]
        assert logical[0].merge_method == "cross_page_continuation"

    def test_single_page_no_cross_page_merge(self):
        pages = [_page(1, [["名称"], ["测试公司"]])]
        logical = TableComposer.from_page_layouts(pages)
        assert len(logical) == 1
        assert logical[0].merge_method == "none"
        assert logical[0].source_pages == [1]


@pytest.mark.skipif(
    not ALIPAY_PDF.exists(),
    reason="alipay fixture not present",
)
class TestTableLayerAlipayFixture:
    """44-page alipay PDF — requires full parse pipeline."""

    @pytest.fixture(scope="class")
    def mirror_json(self):
        import asyncio

        from docmirror.core.entry.factory import PerceiveOptions, perceive_document

        result = asyncio.run(
            perceive_document(ALIPAY_PDF, PerceiveOptions(skip_cache=True))
        )
        return result.to_api_dict(mirror_level="standard")

    def test_alipay_logical_table_row_count(self, mirror_json):
        lt = mirror_json["data"]["document"].get("logical_tables", [])
        assert len(lt) >= 1
        assert lt[0]["row_count"] >= 1400

    def test_alipay_physical_tables_per_page(self, mirror_json):
        meta = mirror_json["meta"]
        pages = mirror_json["data"]["document"]["pages"]
        assert meta["physical_table_count"] >= 40
        assert len(pages) >= 40
        pages_with_tables = sum(1 for p in pages if p.get("tables"))
        assert pages_with_tables >= 40

    def test_alipay_source_page_provenance(self, mirror_json):
        lt = mirror_json["data"]["document"]["logical_tables"][0]
        src_pages = {r["source_page"] for r in lt["rows"]}
        assert len(src_pages) >= 30
