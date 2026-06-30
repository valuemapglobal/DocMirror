# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.models.mirror.page_evidence_bundles import merge_micro_grid_structures_into_bundles
from docmirror.topology.page_projection.flow_filter import filter_flow_texts_not_in_regions
from docmirror.topology.page_projection.models import PageRegion
from docmirror.topology.page_projection.structure_coverage import (
    iter_structure_bboxes,
    text_covered_by_structure,
)


def test_merge_micro_grid_structures_into_bundles_by_page():
    ds: dict = {"_page_evidence_bundles": [{"page": 4, "micro_grid_evidence": {"page": 4}}]}
    merge_micro_grid_structures_into_bundles(
        ds,
        [{"grid_id": "mg_p4_0", "page": 4, "bbox": [0, 0, 10, 10]}],
    )
    bundle = ds["_page_evidence_bundles"][0]
    assert bundle["micro_grid_structures"][0]["grid_id"] == "mg_p4_0"


def test_filter_flow_texts_excludes_region_covered_lines():
    regions = [
        PageRegion(
            region_id="rg_p4_0",
            kind="micro_grid",
            morphology="S3",
            bbox=[0, 0, 100, 100],
            structure={},
        )
    ]
    texts = [
        {"content": "inside", "bbox": [10, 10, 90, 30]},
        {"content": "outside", "bbox": [10, 200, 90, 220]},
    ]
    kept = filter_flow_texts_not_in_regions(texts, regions)
    assert [t["content"] for t in kept] == ["outside"]


def test_filter_flow_texts_uses_structure_cells_not_envelope_bbox():
    """Left-gutter row labels must leave flow when registered in structure cells."""
    regions = [
        PageRegion(
            region_id="rg_p4_repayment_0",
            kind="micro_grid",
            morphology="S3",
            bbox=[130, 190, 730, 350],
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
    ]
    texts = [
        {"content": "2021", "bbox": [75, 262, 112, 280]},
        {"content": "prose", "bbox": [10, 80, 200, 100]},
    ]
    kept = filter_flow_texts_not_in_regions(texts, regions)
    assert [t["content"] for t in kept] == ["prose"]


def test_text_covered_by_structure_uses_cells_not_envelope():
    structure = {
        "cells": [
            [
                {
                    "role": "year",
                    "text": "2021",
                    "bbox": [75, 262, 112, 280],
                }
            ]
        ],
    }
    assert text_covered_by_structure(
        [75, 262, 112, 280],
        structure,
        region_bbox=[130, 190, 730, 350],
    )
    assert not text_covered_by_structure(
        [10, 80, 200, 100],
        structure,
        region_bbox=[130, 190, 730, 350],
    )


def test_iter_structure_bboxes_collects_nested_and_flat_cells():
    nested = iter_structure_bboxes(
        {
            "row_bands": [{"bbox": [0, 0, 10, 10]}],
            "cells": [[{"bbox": [1, 1, 2, 2]}]],
        }
    )
    assert nested == [[0, 0, 10, 10], [1, 1, 2, 2]]

    flat = iter_structure_bboxes({"cells": [{"bbox": [3, 3, 4, 4]}]})
    assert flat == [[3, 3, 4, 4]]
