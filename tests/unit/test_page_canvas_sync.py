# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.core.ocr.page_canvas.evidence_bundles import (
    domain_specific_with_page_bundles,
    merge_micro_grid_structures_into_bundles,
    page_evidence_bundle,
)
from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, TextBlock, TextLevel


def test_sync_page_canvases_materializes_regions_on_page():
    grid = {
        "grid_id": "mg_p4_repayment_0",
        "page": 4,
        "bbox": [1, 2, 100, 80],
        "anchor_text": "anchor",
        "confidence": 0.8,
        "cells": [],
    }
    ds = domain_specific_with_page_bundles(
        page_evidence_bundle(
            4,
            micro_grid_evidence={"page": 4, "lines": [{"content": "inside", "bbox": [5, 5, 90, 20]}]},
        ),
    )
    merge_micro_grid_structures_into_bundles(ds, [grid])
    pr = ParseResult(
        pages=[
            PageContent(
                page_number=4,
                width=100,
                height=200,
                texts=[TextBlock(content="inside", bbox=[5, 5, 90, 20], level=TextLevel.BODY)],
            )
        ],
        entities=DocumentEntities(document_type="credit_report", domain_specific=ds),
    )
    pr.sync_page_canvases()
    canvas = pr.pages[0].page_canvas
    assert canvas is not None
    assert canvas.page_number == 4
    assert len(canvas.regions) == 1
    assert canvas.regions[0].kind == "micro_grid"
    assert canvas.flow.texts == []
    assert "text:" not in "".join(canvas.reading_order_v1 or canvas.reading_order)
    assert len(canvas.blocks) >= 1


def test_sync_page_canvas_includes_tables_and_mixed_reading_order():
    from docmirror.models.entities.parse_result import TableBlock, TableRow, CellValue

    grid = {
        "grid_id": "mg_p4_0",
        "page": 4,
        "bbox": [0, 10, 100, 50],
        "anchor_text": "anchor",
        "confidence": 0.8,
        "cells": [],
    }
    ds: dict = {}
    merge_micro_grid_structures_into_bundles(ds, [grid])
    table = TableBlock(
        table_id="tbl_p4_0",
        headers=["A"],
        rows=[TableRow(cells=[CellValue(text="1")])],
        page=4,
    )
    pr = ParseResult(
        pages=[
            PageContent(
                page_number=4,
                width=100,
                height=300,
                texts=[TextBlock(content="below", bbox=[0, 200, 50, 220], level=TextLevel.BODY)],
                tables=[table],
            )
        ],
        entities=DocumentEntities(document_type="credit_report", domain_specific=ds),
    )
    pr.sync_page_canvases()
    canvas = pr.pages[0].page_canvas
    assert canvas is not None
    assert len(canvas.tables) == 1
    assert canvas.tables[0]["table_id"] == "tbl_p4_0"
    assert canvas.blocks
    assert canvas.blocks[0].block_id.startswith("blk_p4_")
    assert "rg_" in (canvas.reading_order_v1[0] if canvas.reading_order_v1 else "")
    assert any(item.startswith("text:") for item in (canvas.reading_order_v1 or []))
    assert len(canvas.reading_order) == len(canvas.blocks)


def test_to_api_dict_uses_synced_page_canvas():
    grid = {
        "grid_id": "mg_p4_repayment_0",
        "page": 4,
        "bbox": [1, 2, 3, 4],
        "anchor_text": "anchor",
        "confidence": 0.8,
        "cells": [],
    }
    ds: dict = {}
    merge_micro_grid_structures_into_bundles(ds, [grid])
    pr = ParseResult(
        pages=[PageContent(page_number=4, width=100, height=200)],
        entities=DocumentEntities(document_type="credit_report", domain_specific=ds),
    )
    api = pr.to_api_dict(mirror_level="standard")
    assert pr.pages[0].page_canvas is not None
    page = api["data"]["document"]["pages"][0]
    assert page["regions"][0]["kind"] == "micro_grid"
