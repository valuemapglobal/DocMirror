# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from docmirror.input.extraction.scanned_evidence import build_scanned_page_evidence_bundle
from docmirror.models.entities.domain import Block, TextSpan


def _block(index: int, text: str, bbox: tuple[float, float, float, float]) -> Block:
    block_id = f"ocr:sp0002:lp0003:{index:04d}"
    return Block(
        block_id=block_id,
        block_type="text",
        spans=(TextSpan(text=text, bbox=bbox),),
        bbox=bbox,
        reading_order=index,
        page=3,
        raw_content=text,
        attrs={"confidence": 0.98, "ocr_source": "rapidocr_pdf_logical_page"},
        evidence_ids=(block_id,),
    )


def test_vnext_bundle_preserves_lines_tokens_and_account_structures() -> None:
    lines = [
        ("账户1", (20.0, 10.0, 70.0, 24.0)),
        ("管理机构 账户标识 开立日期", (20.0, 40.0, 320.0, 54.0)),
        ("某银行 ABC123 2020.01.02", (20.0, 60.0, 420.0, 74.0)),
        ("账户币种 到期日期 借款金额", (20.0, 90.0, 320.0, 104.0)),
        ("人民币 2021.01.02 10000", (20.0, 110.0, 320.0, 124.0)),
    ]
    bundle = build_scanned_page_evidence_bundle(
        [_block(index, text, bbox) for index, (text, bbox) in enumerate(lines)],
        page=3,
        source_page=2,
        page_width=596.0,
        page_height=419.0,
    )

    assert bundle["page"] == 3
    assert bundle["source_page_number"] == 2
    local = bundle["local_structure_evidence"]
    assert len(local["lines"]) == len(lines)
    assert local["tokens"]
    assert local["structures"]
    assert bundle["micro_grid_evidence"]["lines"] == local["lines"]
