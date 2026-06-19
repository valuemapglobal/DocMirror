# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.core.ocr.page_canvas.build import reading_order_for_page
from docmirror.core.ocr.page_canvas.models import PageRegion
from docmirror.models.mirror.page_canvas_export import attach_region_refs_to_sections


def test_reading_order_interleaves_regions_and_flow_texts():
    regions = [
        PageRegion(
            region_id="rg_top",
            kind="micro_grid",
            morphology="S3",
            bbox=[0, 10, 100, 50],
            structure={},
        ),
        PageRegion(
            region_id="rg_bottom",
            kind="field_grid",
            morphology="S4",
            bbox=[0, 200, 100, 300],
            structure={},
        ),
    ]
    texts = [
        {"content": "between", "bbox": [0, 100, 50, 120]},
        {"content": "no bbox"},
    ]
    order = reading_order_for_page(regions, texts)
    assert order[0] == "rg_top"
    assert order[1] == "text:0"
    assert order[2] == "rg_bottom"
    assert order[3] == "text:1"


def test_attach_region_refs_adds_page_span_and_cross_page_refs():
    api_pages = [
        {
            "page_number": 4,
            "regions": [{"region_id": "rg_p4_a", "kind": "field_grid"}],
        },
        {
            "page_number": 5,
            "regions": [{"region_id": "rg_p5_b", "kind": "field_grid"}],
        },
    ]
    sections = [{"id": "sec_x", "title": "信贷", "page_start": 4, "page_end": 5}]
    out = attach_region_refs_to_sections(sections, api_pages)
    assert out[0]["page_span"] == [4, 5]
    assert set(out[0]["region_refs"]) == {"rg_p4_a", "rg_p5_b"}
