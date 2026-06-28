# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.structure.ocr.page_canvas.flow_filter import filter_flow_texts_not_in_regions
from docmirror.structure.ocr.page_canvas.models import PageRegion
from docmirror.structure.ocr.page_canvas.page_token_ownership import (
    assert_no_flow_structure_dual_assign,
    assign_line_ownership,
    flow_texts_complement,
    iter_structure_elements,
)


def _micro_region(
    region_id: str,
    bbox: list[float],
    *,
    structure: dict | None = None,
) -> PageRegion:
    return PageRegion(
        region_id=region_id,
        kind="micro_grid",
        morphology="S3",
        bbox=bbox,
        structure=structure or {},
    )


def test_assign_line_ownership_exclusive_cell_over_envelope():
    region = _micro_region(
        "rg_p1_0",
        [0, 0, 200, 200],
        structure={
            "cells": [
                [
                    {
                        "row_index": 0,
                        "col_index": 0,
                        "text": "2021",
                        "bbox": [10, 10, 50, 30],
                    }
                ]
            ],
        },
    )
    texts = [
        {"content": "2021", "bbox": [10, 10, 50, 30]},
        {"content": "outside", "bbox": [10, 180, 50, 195]},
    ]
    ownership = assign_line_ownership(texts, [region])
    assert ownership[0].owner == "rg_p1_0"
    assert ownership[0].element_ref == "cell:0:0"
    assert ownership[1].owner == "prose_flow"


def test_smallest_cell_wins_when_overlapping_cells():
    region = _micro_region(
        "rg_p1_0",
        [0, 0, 200, 200],
        structure={
            "cells": [
                [
                    {"row_index": 0, "col_index": 0, "bbox": [0, 0, 200, 200]},
                    {"row_index": 0, "col_index": 1, "bbox": [10, 10, 60, 30]},
                ]
            ],
        },
    )
    texts = [{"content": "N", "bbox": [12, 12, 58, 28]}]
    ownership = assign_line_ownership(texts, [region])
    assert ownership[0].element_ref == "cell:0:1"


def test_multi_region_single_owner_per_line():
    grid = _micro_region(
        "rg_grid",
        [100, 100, 400, 300],
        structure={
            "cells": [[{"row_index": 0, "col_index": 0, "bbox": [120, 120, 160, 140]}]],
        },
    )
    field = PageRegion(
        region_id="rg_field",
        kind="field_grid",
        morphology="S4",
        bbox=[100, 350, 400, 500],
        structure={
            "cells": [{"row_index": 0, "col_index": 0, "bbox": [120, 360, 300, 380]}],
        },
    )
    texts = [
        {"content": "2021", "bbox": [120, 120, 160, 140]},
        {"content": "管理机构", "bbox": [120, 360, 300, 380]},
        {"content": "prose", "bbox": [10, 10, 80, 30]},
    ]
    ownership = assign_line_ownership(texts, [grid, field])
    assert ownership[0].owner == "rg_grid"
    assert ownership[1].owner == "rg_field"
    assert ownership[2].owner == "prose_flow"
    assert_no_flow_structure_dual_assign(texts, [grid, field])


def test_flow_complement_never_includes_owned_lines():
    region = _micro_region(
        "rg_p4_repayment_0",
        [130, 190, 730, 350],
        structure={
            "cells": [
                [
                    {
                        "row_index": 0,
                        "col_index": 0,
                        "role": "year",
                        "text": "2021",
                        "bbox": [75, 262, 112, 280],
                    },
                    {
                        "row_index": 0,
                        "col_index": 1,
                        "role": "status",
                        "text": "N",
                        "bbox": [130, 262, 160, 280],
                    },
                ]
            ],
        },
    )
    texts = [
        {"content": "2021", "bbox": [75, 262, 112, 280]},
        {"content": "prose", "bbox": [10, 80, 200, 100]},
    ]
    ownership = assign_line_ownership(texts, [region])
    flow = flow_texts_complement(texts, ownership)
    assert [t["content"] for t in flow] == ["prose"]
    kept = filter_flow_texts_not_in_regions(texts, [region])
    assert [t["content"] for t in kept] == ["prose"]


def test_empty_structure_falls_back_to_region_envelope():
    region = _micro_region("rg_p4_0", [0, 0, 100, 100])
    elements = iter_structure_elements(region)
    assert len(elements) == 1
    assert elements[0].element_type == "region_envelope"

    texts = [
        {"content": "inside", "bbox": [10, 10, 90, 30]},
        {"content": "outside", "bbox": [10, 200, 90, 220]},
    ]
    kept = filter_flow_texts_not_in_regions(texts, [region])
    assert [t["content"] for t in kept] == ["outside"]


def test_synthetic_prose_plus_grid_adjacency():
    """Prose above grid: only grid interior lines leave flow."""
    region = _micro_region(
        "rg_grid",
        [50, 120, 350, 320],
        structure={
            "cells": [
                [
                    {"row_index": 0, "col_index": 0, "bbox": [60, 130, 100, 150]},
                    {"row_index": 0, "col_index": 1, "bbox": [110, 130, 150, 150]},
                ],
                [
                    {"row_index": 1, "col_index": 0, "bbox": [60, 160, 100, 180]},
                    {"row_index": 1, "col_index": 1, "bbox": [110, 160, 150, 180]},
                ],
            ],
        },
    )
    texts = [
        {"content": "header prose", "bbox": [50, 40, 200, 60]},
        {"content": "A", "bbox": [65, 135, 95, 145]},
        {"content": "B", "bbox": [115, 135, 145, 145]},
        {"content": "footer", "bbox": [50, 400, 200, 420]},
    ]
    ownership = assign_line_ownership(texts, [region])
    flow = flow_texts_complement(texts, ownership)
    assert [t["content"] for t in flow] == ["header prose", "footer"]
    assert_no_flow_structure_dual_assign(texts, [region])
