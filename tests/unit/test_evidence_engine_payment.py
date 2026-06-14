# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""EvidenceEngine payment ledger disambiguation."""

from __future__ import annotations

from docmirror.core.scene.evidence_engine import EvidenceEngine
from docmirror.models.entities.parse_result import (
    CellValue,
    PageContent,
    ParseResult,
    TableBlock,
    TableRow,
)


def _alipay_header_table() -> TableBlock:
    headers = [
        "收/支",
        "交易对方",
        "商品说明",
        "收/付款方式",
        "金额",
        "交易订单号",
        "商家订单号",
        "交易时间",
    ]
    row = TableRow(cells=[CellValue(text="支出") for _ in headers])
    return TableBlock(table_id="t1", headers=headers, rows=[row])


def test_alipay_headers_prefer_alipay_over_wechat():
    engine = EvidenceEngine()
    result = ParseResult(
        pages=[PageContent(page_number=1, tables=[_alipay_header_table()])],
    )
    result.entities.domain_specific = {
        "extractor_scene_hint": "alipay_payment",
        "extractor_scene_confidence": 0.99,
    }
    classified = engine.process(result)
    assert classified.entities.document_type == "alipay_payment"
