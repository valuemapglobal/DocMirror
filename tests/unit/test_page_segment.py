# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.core.ocr.page_canvas.page_segment import (
    lines_to_synthetic_tokens,
    segment_page_blocks,
)


def _field_block_lines(start_y: float) -> list[dict]:
    return [
        {"content": "管理机构", "bbox": [72, start_y, 140, start_y + 16]},
        {"content": "示例银行股份有限公司", "bbox": [200, start_y, 500, start_y + 16]},
        {"content": "账户标识", "bbox": [72, start_y + 20, 140, start_y + 36]},
        {"content": "LOAN-001", "bbox": [200, start_y + 20, 400, start_y + 36]},
        {"content": "开立日期", "bbox": [72, start_y + 40, 140, start_y + 56]},
        {"content": "2019-01-01", "bbox": [200, start_y + 40, 320, start_y + 56]},
    ]


def test_segment_detects_field_block_without_numbered_heading():
    lines = [
        {"content": "page header prose", "bbox": [50, 30, 300, 50]},
        *_field_block_lines(120.0),
        {"content": "footer prose", "bbox": [50, 500, 300, 520]},
    ]
    blocks = segment_page_blocks(lines, page=1)
    field_blocks = [block for block in blocks if block.predicted_kind == "field_grid"]
    assert len(field_blocks) == 1
    assert field_blocks[0].field_score >= 0.45
    assert "two_column_rows" in field_blocks[0].reason_codes


def test_segment_detects_grid_block_from_token_lattice():
    lines = [
        {"content": "period matrix", "bbox": [80, 50, 260, 70]},
        {"content": "1 2 3 4 5 6 7 8 9 10 11 12", "bbox": [80, 90, 520, 110]},
        {"content": "N N N N N N N N N N N N", "bbox": [80, 120, 520, 140]},
        {"content": "N N N N N N N N N N N N", "bbox": [80, 150, 520, 170]},
        {"content": "N N N N N N N N N N N N", "bbox": [80, 180, 520, 200]},
    ]
    tokens = lines_to_synthetic_tokens(lines[1:], page=1)
    blocks = segment_page_blocks(lines, tokens=tokens, page=1, gap_threshold=28.0)
    grid_blocks = [block for block in blocks if block.predicted_kind == "micro_grid"]
    assert len(grid_blocks) == 1
    assert grid_blocks[0].grid_score >= 0.45


def test_segment_skips_prose_only_blocks():
    lines = [
        {"content": "paragraph one", "bbox": [50, 40, 400, 60]},
        {"content": "paragraph two continues here", "bbox": [50, 66, 420, 86]},
        {"content": "paragraph three", "bbox": [50, 92, 380, 112]},
    ]
    blocks = segment_page_blocks(lines, page=1)
    assert blocks == []
