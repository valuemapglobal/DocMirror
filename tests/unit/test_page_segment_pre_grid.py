# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.core.ocr.page_canvas.page_segment import detect_pre_grid_field_supplements
from docmirror.core.ocr.local_structure.utils import line_items


def _account1_prefix_lines():
    return [
        {"content": "截至2021年02月23日", "bbox": [351.0, 121.0, 466.0, 137.0]},
        {"content": "账户状态 账户关闭日期", "bbox": [182.0, 145.0, 618.0, 165.0]},
        {"content": "2021.02.23结消", "bbox": [223.0, 172.0, 614.0, 190.0]},
        {"content": "2020年09月-2021年02月的还款记录", "bbox": [100.0, 220.0, 400.0, 240.0]},
        {"content": "1 2 3 4 5 6 7 8 9 10 11 12", "bbox": [80.0, 260.0, 520.0, 280.0]},
        {"content": "N N N N N N N N N N N N", "bbox": [80.0, 290.0, 520.0, 310.0]},
        {"content": "N N N N N N N N N N N N", "bbox": [80.0, 320.0, 520.0, 340.0]},
    ]


def test_pre_grid_field_supplement_infers_account1_anchor():
    lines = _account1_prefix_lines()
    items = line_items(lines, page=4)
    from docmirror.core.ocr.local_structure.models import LocalStructureCandidate
    from docmirror.core.ocr.page_canvas.page_segment import lines_to_synthetic_tokens

    tokens = lines_to_synthetic_tokens(lines[3:], page=4)
    existing = [
        LocalStructureCandidate(
            candidate_id="existing_2",
            page=4,
            bbox=(72, 380, 730, 631),
            anchors=("账户2",),
            reason_codes=("block_heading_numbered",),
            score=0.9,
        )
    ]
    found = detect_pre_grid_field_supplements(items, tokens=tokens, page=4, existing=existing)
    assert found
    assert "账户1" in found[0].anchors
    assert "geometric" in found[0].reason_codes[0]
