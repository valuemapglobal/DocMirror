# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.core.ocr.field_grid.assign import assign_tokens_to_col_bands, cell_bbox
from docmirror.core.ocr.field_grid.models import FieldCell
from docmirror.core.ocr.field_grid.type_gate import apply_type_gate, infer_types, quarantine_reason_for_types
from docmirror.core.ocr.micro_grid.models import OCRToken
from docmirror.core.ocr.micro_grid.reconstruct import dedupe_visual_tokens


def test_field_grid_type_gate_quarantines_page_footer():
    inferred = infer_types("第4页，共56页")
    assert "page_footer" in inferred
    assert quarantine_reason_for_types(tuple(inferred)) == "page_footer_leak"

    cell = FieldCell(
        cell_id="c1",
        row_index=0,
        col_index=0,
        label_text="开立日期",
        text="第4页，共56页",
        raw_text="第4页，共56页",
        bbox=(0, 0, 10, 10),
    )
    gated = apply_type_gate(cell)
    assert gated.geometry_status == "quarantined"
    assert gated.quarantine_reason == "page_footer_leak"


def test_field_grid_assign_tokens_exclusive():
    row = {"index": 0, "bbox": [0, 0, 100, 20]}
    cols = [
        {"index": 0, "bbox": [0, 0, 30, 20]},
        {"index": 1, "bbox": [30, 0, 60, 20]},
    ]
    token = OCRToken(
        token_id="t1",
        text="N",
        bbox=(25, 2, 35, 18),
        confidence=0.9,
        page=1,
        source="native_test",
    )
    assigned = assign_tokens_to_col_bands([token], row, cols)
    non_empty = [idx for idx, bucket in assigned.items() if bucket]
    assert len(non_empty) == 1


def test_field_grid_reconstruct_exports_from_micro_grid():
    from docmirror.core.ocr import field_grid

    assert hasattr(field_grid, "assign_tokens_to_col_bands")
    assert dedupe_visual_tokens is not None


def test_field_grid_semantic_spans_split_mixed_ocr_line():
    from docmirror.core.ocr.field_grid.assemble import _extract_semantic_spans, line_has_mixed_semantics

    text = "2018.08.31（原：重庆市蚂蚁 人民币元20180831J10101172,000"
    assert line_has_mixed_semantics(text)
    spans = _extract_semantic_spans(text)
    by_kind = {kind: value for *_rest, value, kind in spans}
    assert by_kind["date"] == "2018.08.31"
    assert by_kind["currency"] == "人民币"
    assert by_kind["amount"] == "72,000"


def test_field_grid_parse_as_of_date():
    from docmirror.core.ocr.field_grid.assemble import parse_as_of_date

    assert parse_as_of_date("截至2019年06月21日") == "2019.06.21"

