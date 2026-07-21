# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Coordinate-aware community payment recovery tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from docmirror.plugins.alipay_payment.community_plugin import AlipayPaymentPlugin
from docmirror.plugins.wechat_payment.community_plugin import WeChatPaymentPlugin

pytestmark = pytest.mark.unit


def _atom(atom_id: str, text: str, x: float, y: float, x1: float | None = None) -> dict:
    return {
        "id": atom_id,
        "page_id": "page:0001",
        "text": text,
        "bbox": [x, y, x1 if x1 is not None else x + max(len(text), 1) * 4.0, y + 8.0],
    }


def _parse_result(atoms: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        pages=[],
        file_path="sample.pdf",
        evidence_plane=SimpleNamespace(evidence={"text_atoms": atoms}),
    )


def test_alipay_recovers_only_complete_issuer_rows_from_evidence_atoms():
    headers = [
        ("收/支", 51.0),
        ("交易对方", 79.0),
        ("商品说明", 134.0),
        ("收/付款方式", 203.0),
        ("金额", 258.0),
        ("交易订单号", 300.0),
        ("商家订单号", 396.0),
        ("交易时间", 493.0),
    ]
    atoms = [_atom(f"h{i}", text, x, 158.0) for i, (text, x) in enumerate(headers)]
    atoms.extend(
        [
            _atom("d1", "收入", 51.0, 180.0),
            _atom("party1", "测试对方", 79.0, 180.0),
            _atom("description1", "测试商品", 134.0, 180.0),
            _atom("method1", "余额", 203.0, 180.0),
            _atom("a1", "12.34", 258.0, 180.0),
            _atom("n1a", "12345678901234567890123", 300.0, 180.0),
            _atom("n1b", "12345", 300.0, 188.0),
            _atom("date1", "2026-01-02", 493.0, 180.0),
            _atom("time1", "03:04:05", 493.0, 188.0),
            _atom("merchant1", "M123", 396.0, 180.0),
            _atom("d2a", "不计", 51.0, 210.0),
            _atom("d2b", "收支", 51.0, 218.0),
            _atom("a2", "6.78", 258.0, 210.0),
            _atom("n2", "12345678901234567890", 300.0, 210.0),
            _atom("date2", "2026-01-03", 493.0, 210.0),
            _atom("time2", "04:05:06", 493.0, 218.0),
        ]
    )

    plugin = AlipayPaymentPlugin()
    recovered = plugin._recover_records_from_evidence(_parse_result(atoms))

    assert len(recovered) == 2
    assert recovered[0]["交易订单号"] == "1234567890123456789012312345"
    assert recovered[0]["交易时间"] == "2026-01-02 03:04:05"
    assert recovered[0]["交易对方"] == "测试对方"
    assert recovered[0]["商品说明"] == "测试商品"
    assert recovered[0]["收/付款方式"] == "余额"
    assert recovered[0]["商家订单号"] == "M123"
    assert recovered[1]["收/支"] == "不计收支"
    assert recovered[1]["交易订单号"] == "12345678901234567890"

    built = plugin._build_records(recovered)
    assert built[0]["normalized"]["amount"] == 12.34
    assert built[0]["normalized"]["direction"] == "income"
    assert built[1]["normalized"]["direction"] == "other"
    assert "_source" not in built[0]["raw"]
    assert built[0]["source"]["source"] == "canonical_evidence_atoms"


def test_wechat_recovers_rows_and_ignores_statement_metadata_date():
    atoms = [
        _atom("h1", "交易单号", 78.0, 160.0),
        _atom("h2", "交易时间交易类型收/支/其他交易方式金额(元)", 163.0, 160.0, 415.0),
        _atom("h3", "交易对方", 423.0, 160.0),
        _atom("h4", "商户单号", 491.0, 160.0),
        _atom("meta-date", "2025-12-01", 160.0, 130.0),
        _atom("meta-time", "00:00:00", 160.0, 138.0),
        _atom("n1a", "1234567890123456789012", 40.0, 180.0),
        _atom("n1b", "123456", 40.0, 188.0),
        _atom("date1", "2026-01-02", 160.0, 180.0),
        _atom("time1", "03:04:05", 160.0, 188.0),
        _atom("d1", "支出", 281.0, 180.0),
        _atom("type1", "商户消费", 220.0, 180.0),
        _atom("method1", "零钱", 332.0, 180.0),
        _atom("a1", "12.34", 383.0, 180.0),
        _atom("party1", "测试商户", 423.0, 180.0),
        _atom("merchant1", "M123", 491.0, 180.0),
        _atom("n2a", "1234567890123456789012", 40.0, 210.0),
        _atom("n2b", "123456789", 40.0, 218.0),
        _atom("date2", "2026-01-03", 160.0, 210.0),
        _atom("time2", "04:05:06", 160.0, 218.0),
        _atom("d2", "收入", 281.0, 210.0),
        _atom("a2", "6.78", 383.0, 210.0),
        _atom("footer", "99", 500.0, 800.0),
    ]

    plugin = WeChatPaymentPlugin()
    recovered = plugin._recover_records_from_evidence(_parse_result(atoms))

    assert len(recovered) == 2
    assert recovered[0]["交易单号"] == "1234567890123456789012123456"
    assert recovered[0]["交易时间"] == "2026-01-02 03:04:05"
    assert recovered[0]["交易类型"] == "商户消费"
    assert recovered[0]["交易方式"] == "零钱"
    assert recovered[0]["交易对方"] == "测试商户"
    assert recovered[0]["商户单号"] == "M123"
    assert recovered[1]["交易单号"] == "1234567890123456789012123456789"

    built = plugin._build_records(recovered)
    assert built[0]["normalized"]["direction"] == "expense"
    assert built[1]["normalized"]["direction"] == "income"
    assert built[1]["normalized"]["amount"] == 6.78
    assert "_source" not in built[0]["raw"]


def test_alipay_recovers_complete_narrative_identity_without_sentence_suffixes():
    atoms = [
        _atom("number", "编号：202601020001", 400.0, 20.0),
        _atom(
            "identity",
            "兹证明：测试用户（证件号码：11010519491231002X）在其支付宝账号demo@example.com中明细如下：",
            50.0,
            60.0,
        ),
        _atom("currency", "币种：人民币/单位：元", 200.0, 100.0),
        _atom("period", "交易时间段：2026-01-01 00:00:00 至 2026-01-31 23:59:59", 50.0, 120.0),
        _atom("scope", "交易类型：全部", 50.0, 140.0),
    ]

    recovered = AlipayPaymentPlugin()._recover_identity_from_evidence(_parse_result(atoms))

    assert recovered["account_holder"]["normalized_value"] == "测试用户"
    assert recovered["account_number"]["normalized_value"] == "demo@example.com"
    assert recovered["id_number"]["normalized_value"] == "11010519491231002X"
    assert recovered["query_period"]["normalized_value"] == "2026-01-01 00:00:00 至 2026-01-31 23:59:59"
    assert recovered["transaction_scope"]["normalized_value"] == "全部"


def test_wechat_recovers_complete_narrative_identity_without_sentence_suffixes():
    atoms = [
        _atom("number", "编号：202601020001", 400.0, 20.0),
        _atom(
            "identity",
            "兹证明：测试用户（身份证：11010519491231002X），在其微信号：demo_wechat中的交易明细信息如下：",
            50.0,
            60.0,
        ),
        _atom("currency", "币种：人民币/单位：元", 200.0, 100.0),
        _atom("period", "交易明细对应时间段 2026-01-01 00:00:00至2026-01-31 23:59:59", 50.0, 120.0),
    ]

    recovered = WeChatPaymentPlugin()._recover_identity_from_evidence(_parse_result(atoms))

    assert recovered["account_holder"]["normalized_value"] == "测试用户"
    assert recovered["account_number"]["normalized_value"] == "demo_wechat"
    assert recovered["id_number"]["normalized_value"] == "11010519491231002X"
    assert recovered["query_period"]["normalized_value"] == "2026-01-01 00:00:00 至 2026-01-31 23:59:59"
