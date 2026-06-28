# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.structure.ocr.grid_materialize import (
    coalesce_tokens_prefer_native,
    exclusive_assign_tokens_to_grid,
    materialize_grid_cell,
)
from docmirror.structure.ocr.micro_grid.models import OCRToken


def _token(token_id: str, text: str, bbox: tuple[float, float, float, float], *, source: str = "native") -> OCRToken:
    return OCRToken(
        token_id=token_id,
        text=text,
        bbox=bbox,
        confidence=0.95,
        page=1,
        source=source,
    )


def test_exclusive_assign_token_to_single_cell():
    rows = [
        {"index": 0, "bbox": [0, 0, 100, 20]},
        {"index": 1, "bbox": [0, 24, 100, 44]},
    ]
    cols = [
        {"index": 0, "bbox": [0, 0, 40, 44]},
        {"index": 1, "bbox": [40, 0, 100, 44]},
    ]
    token = _token("t1", "N", (35, 2, 45, 18))
    assigned = exclusive_assign_tokens_to_grid([token], rows, cols)
    occupied = [key for key, bucket in assigned.items() if bucket]
    assert len(occupied) == 1
    assert assigned[occupied[0]][0].token_id == "t1"


def test_exclusive_assign_prevents_duplicate_token_across_rows():
    rows = [
        {"index": 0, "bbox": [0, 0, 100, 22]},
        {"index": 1, "bbox": [0, 20, 100, 42]},
    ]
    cols = [{"index": 0, "bbox": [0, 0, 100, 42]}]
    shared = _token("shared", "X", (10, 10, 20, 30))
    assigned = exclusive_assign_tokens_to_grid([shared], rows, cols)
    token_hits = sum(1 for bucket in assigned.values() for token in bucket if token.token_id == "shared")
    assert token_hits == 1


def test_coalesce_tokens_prefer_native_over_char_split():
    native = _token("native", "蚂蚁商诚", (200, 400, 280, 416), source="ocr")
    split = OCRToken(
        token_id="native_c0",
        text="蚂",
        bbox=(200, 400, 210, 416),
        confidence=0.9,
        page=1,
        source="ocr_char_split",
        source_token_id="native",
    )
    coalesced = coalesce_tokens_prefer_native([native, split])
    assert [token.token_id for token in coalesced] == ["native"]


def test_materialize_grid_cell_assembles_sorted_text():
    row = {"index": 0, "bbox": [0, 0, 100, 20]}
    col = {"index": 1, "bbox": [40, 0, 100, 20], "header": "管理机构"}
    tokens = [
        _token("t1", "蚂蚁", (45, 2, 65, 18)),
        _token("t2", "商诚", (66, 2, 90, 18)),
    ]
    cell = materialize_grid_cell(row_band=row, col_band=col, tokens=tokens, label_text="管理机构")
    assert cell is not None
    assert cell.text == "蚂蚁商诚"
    assert cell.label_text == "管理机构"
