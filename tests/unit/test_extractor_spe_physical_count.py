# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SPE physical_table_count must reflect PageLayout table blocks."""

from __future__ import annotations

from docmirror.core.extraction.extractor import CoreExtractor
from docmirror.models.entities.domain import Block, PageLayout


def test_build_structure_metadata_physical_table_count_from_blocks():
    pages = [
        PageLayout(
            page_number=1,
            blocks=(
                Block(block_id="t0", block_type="table", raw_content=[["a"], ["1"]], page=1, reading_order=0),
                Block(block_id="t1", block_type="table", raw_content=[["b"], ["2"]], page=1, reading_order=1),
            ),
        ),
        PageLayout(
            page_number=2,
            blocks=(
                Block(block_id="t0", block_type="table", raw_content=[["c"], ["3"]], page=2, reading_order=0),
            ),
        ),
    ]
    table_count = sum(1 for p in pages for b in p.blocks if b.block_type == "table")
    assert table_count == 3

    spe = CoreExtractor._build_structure_metadata(
        pre_analysis=type("PA", (), {"structure_spe": None, "content_type": "unknown"})(),
        fitz_doc=None,
        table_count=table_count,
        extraction_layer="pdfplumber_default",
        layout_profile_id="borderless_ledger_bank",
        physical_table_count=table_count,
    )
    assert spe["physical_table_count"] == 3
