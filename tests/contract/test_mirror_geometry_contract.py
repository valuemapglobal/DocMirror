# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror geometry conservation contract tests."""

from __future__ import annotations

from docmirror.core.bridge.parse_result_bridge import ParseResultBridge
from docmirror.eval.tqg.geometry_oracles import run_mirror_geometry_oracle
from docmirror.models.entities.domain import BaseResult, Block, PageLayout


def test_bridge_projects_table_geometry_attrs_to_forensic_cells():
    geometry = {
        "coordinate_system": "pdf_points_top_left",
        "cell_bboxes": [
            [[0, 0, 50, 20], [50, 0, 100, 20]],
            [[0, 20, 50, 40], [50, 20, 100, 40]],
        ],
        "cell_geometry_status": [["exact", "exact"], ["exact", "estimated"]],
        "cell_geometry_loss_reason": [[None, None], [None, "estimated_from_row_col_bands"]],
        "cell_evidence_ids": [[["h0"], ["h1"]], [["c0"], ["c1"]]],
        "cell_token_ids": [[["th0"], ["th1"]], [["tc0"], ["tc1"]]],
        "cell_confidences": [[0.95, 0.94], [0.93, 0.61]],
        "row_bands": [
            {"index": 0, "bbox": [0, 0, 100, 20], "role": "header"},
            {"index": 1, "bbox": [0, 20, 100, 40], "role": "data"},
        ],
        "col_bands": [
            {"index": 0, "bbox": [0, 0, 50, 40]},
            {"index": 1, "bbox": [50, 0, 100, 40]},
        ],
        "geometry_source": "unit",
        "geometry_confidence": 0.9,
    }
    block = Block(
        block_type="table",
        raw_content=[["A", "B"], ["1", ""]],
        bbox=(0, 0, 100, 40),
        page=1,
        attrs={"geometry": geometry, "extraction_layer": "unit", "extraction_confidence": 0.9},
    )
    base = BaseResult(pages=(PageLayout(page_number=1, width=100, height=40, blocks=(block,)),))

    result = ParseResultBridge.from_base_result(base)
    api = result.to_api_dict(mirror_level="forensic")
    table = api["data"]["document"]["pages"][0]["tables"][0]
    cell = table["rows"][0]["cells"][0]

    assert cell["bbox"] == [0, 20, 50, 40]
    assert cell["row_index"] == 0
    assert cell["col_index"] == 0
    assert cell["geometry_status"] == "exact"
    assert "geometry_loss_reason" not in cell
    assert cell["evidence_ids"] == ["c0"]
    assert cell["token_ids"] == ["tc0"]
    assert cell["geometry_confidence"] == 0.93
    estimated = table["rows"][0]["cells"][1]
    assert estimated["geometry_status"] == "estimated"
    assert estimated["geometry_loss_reason"] == "estimated_from_row_col_bands"
    assert estimated["token_ids"] == ["tc1"]
    assert estimated["geometry_confidence"] == 0.61
    assert table["metadata"]["geometry"]["row_bands"][0]["role"] == "header"


def test_mirror_geometry_oracle_accepts_synthetic_geometry():
    from docmirror.eval.tqg.manifest import TQGCase
    from docmirror.eval.tqg.runner import run_tqg_case

    report = run_tqg_case(
        TQGCase(
            id="unit_geometry",
            track="mirror_geometry",
            pipeline="mirror_geometry_contract",
            oracle={
                "mirror_geometry": {
                    "min_cell_bbox_coverage": 0.9,
                    "require_monotonic_rows": True,
                    "require_monotonic_cols": True,
                    "require_table_bbox_contains_cells": True,
                    "require_row_col_bands": True,
                    "require_logical_source_cell_refs": True,
                }
            },
        )
    )

    assert report.passed, report.failures


def test_mirror_geometry_oracle_rejects_missing_cell_bboxes():
    api = {
        "data": {
            "document": {
                "pages": [
                    {
                        "page_number": 1,
                        "tables": [
                            {
                                "table_id": "pt_1_0",
                                "bbox": [0, 0, 100, 40],
                                "rows": [{"cells": [{"text": "1"}]}],
                            }
                        ],
                    }
                ]
            }
        }
    }

    report = run_mirror_geometry_oracle(
        api,
        {"min_cell_bbox_coverage": 0.9, "max_missing_geometry_cells": 0},
        case_id="missing",
    )

    assert not report.passed
    assert any("cell bbox coverage" in failure for failure in report.failures)
