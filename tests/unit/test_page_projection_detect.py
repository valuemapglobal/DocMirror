# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.topology.page_projection.detect import detect_page_region_candidates


def test_detect_page_region_candidates_merges_smg_and_slsr():
    lines = [
        {"content": "2020年09月-2021年02月的还款记录", "bbox": [100, 50, 400, 70]},
        {"content": "账户2", "bbox": [72, 380, 120, 396]},
        {"content": "管理机构", "bbox": [72, 400, 140, 416]},
        {"content": "重庆市蚂蚁商诚信息技术有限公司", "bbox": [200, 400, 500, 416]},
        {"content": "账户标识", "bbox": [72, 420, 140, 436]},
        {"content": "蚂蚁借呗", "bbox": [200, 420, 400, 436]},
    ]
    candidates = detect_page_region_candidates(lines, page=4, page_width=800, page_height=600)
    kinds = {c.kind for c in candidates}
    assert "micro_grid" in kinds
    assert "field_grid" in kinds
