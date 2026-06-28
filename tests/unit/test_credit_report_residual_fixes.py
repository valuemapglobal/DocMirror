# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.structure.ocr.local_structure.build import extract_local_structure_evidence
from docmirror.plugins.credit_report.account_structure import _collapse_ocr_stutter
from docmirror.plugins.credit_report.repayment_grid import dedupe_repayment_records, extract_credit_repayment_records
from tests.unit.test_scanned_micro_grid_repayment import _credit_page4_lines, _credit_page4_tokens


def _credit_page4_with_account1_lines():
    return [
        {"content": "个人商用房（含商组合 (不含保证)", "bbox": [76.0, 82.0, 281.0, 106.0], "confidence": 1.0},
        {"content": "无住两用）贷款 月120", "bbox": [87.0, 88.0, 703.0, 113.0], "confidence": 1.0},
        {"content": "截至2021年02月23日", "bbox": [351.0, 121.0, 466.0, 137.0], "confidence": 1.0},
        {"content": "账户状态 账户关闭日期", "bbox": [182.0, 145.0, 618.0, 165.0], "confidence": 1.0},
        {"content": "2021.02.23结消", "bbox": [223.0, 172.0, 614.0, 190.0], "confidence": 1.0},
        *_credit_page4_lines(),
    ]


def test_repayment_structure_materializes_anchor_and_header():
    out = extract_credit_repayment_records(_credit_page4_lines(), page=4)
    grid = out["micro_grid"]
    roles = {cell.get("role") for row in grid["cells"] for cell in row}
    assert "anchor" in roles
    assert "month_header" in roles
    anchor_cells = [cell for row in grid["cells"] for cell in row if cell.get("role") == "anchor"]
    assert "还款记录" in anchor_cells[0]["text"]


def test_credit_closed_account_block_detected_on_page4():
    evidence = extract_local_structure_evidence(
        _credit_page4_with_account1_lines(),
        tokens=_credit_page4_tokens(),
        page=4,
    )
    structures = evidence.get("structures") or []
    assert any(
        "账户1" in str((structure.get("anchors") or [""])[0])
        for structure in structures
        if structure.get("anchors")
    )


def test_collapse_ocr_stutter_removes_repeated_prefix():
    raw = "重庆市蚂蚁商诚信重庆市蚂蚁商诚信息技术有限公司"
    collapsed = _collapse_ocr_stutter(raw)
    assert collapsed.count("重庆市蚂蚁商诚") == 1


def test_dedupe_repayment_records_by_grid_month():
    records = [
        {"year": 2025, "month": 4, "status": "N", "confidence": 0.5, "source_cell_refs": [{"grid_id": "mg_p5_0"}]},
        {"year": 2025, "month": 4, "status": "N", "confidence": 0.9, "source_cell_refs": [{"grid_id": "mg_p5_0"}]},
        {"year": 2025, "month": 5, "status": "C", "confidence": 0.8, "source_cell_refs": [{"grid_id": "mg_p5_0"}]},
    ]
    out = dedupe_repayment_records(records)
    assert len(out) == 2
    assert out[0]["confidence"] == 0.9
