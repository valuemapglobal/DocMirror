# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.ocr.local_structure.utils import line_items
from docmirror.plugins.credit_report.account_structure import (
    _account_from_field_grid,
    _find_cell_for_field,
    _index_cells_by_label,
)
from docmirror.plugins.credit_report.local_structure_supplement import detect_credit_closed_account_blocks


def _page4_account1_prefix_items():
    lines = [
        {"content": "截至2021年02月23日", "bbox": [351.0, 121.0, 466.0, 137.0]},
        {"content": "账户状态 账户关闭日期", "bbox": [182.0, 145.0, 618.0, 165.0]},
        {"content": "2021.02.23结消", "bbox": [223.0, 172.0, 614.0, 190.0]},
        {"content": "2020年09月-2021年02月的还款记录", "bbox": [280.46, 194.67, 510.65, 217.78]},
        {"content": "1 122689 113.45710", "bbox": [130.84, 222.65, 733.57, 241.51]},
    ]
    return line_items(lines, page=4)


def test_pre_grid_candidate_does_not_include_repayment_lines():
    items = _page4_account1_prefix_items()
    found = detect_credit_closed_account_blocks(items, page=4, existing=[])
    assert len(found) == 1
    assert found[0].bbox[3] < 194.67
    assert "还款记录" not in " ".join(found[0].anchors)


def test_institution_merge_combines_fragment_cells():
    structure = {
        "structure_kind": "field_grid",
        "structure_id": "ls_test",
        "page": 4,
        "confidence": 0.8,
        "anchors": ("账户3",),
        "nodes": [{"node_id": "n0", "role": "anchor", "text": "账户3"}],
        "cells": [
            {
                "label_text": "管理机构",
                "text": "重庆市蚂蚁商诚信",
                "raw_text": "重庆市蚂蚁商诚信",
                "bbox": [200, 400, 500, 416],
                "geometry_status": "exact",
                "inferred_types": ["text"],
            },
            {
                "label_text": "管理机构",
                "text": "信息技术有限公司",
                "raw_text": "信息技术有限公司",
                "bbox": [200, 418, 500, 434],
                "geometry_status": "exact",
                "inferred_types": ["text"],
            },
        ],
    }
    cells_by_label = _index_cells_by_label(structure["cells"])
    cell = _find_cell_for_field(
        structure,
        cells_by_label,
        ("管理机构", "发放机构"),
        field_key="management_institution",
    )
    assert cell is not None
    assert "蚂蚁商诚" in cell["text"]
    account = _account_from_field_grid(structure, page=4)
    assert account is not None
    assert account["management_institution"]["value"] == "重庆市蚂蚁商诚信息技术有限公司"
