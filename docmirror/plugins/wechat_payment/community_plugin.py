# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
WeChat payment community domain plugin (v2.0).

Premium community plugin for WeChat transaction export PDFs. Extends ``BaseTableParser``
with WeChat-specific column registry, scene keywords, identity field specs, and custom
row normalization (trade number cleanup, direction mapping).

Pipeline role: one of six premium plugins discovered by ``community`` and executed
via ``runner._run_community_extract`` → ``extract_from_mirror``.

Archetype: ``table_document``; domain: ``cashflow_payment``; support level: L2.

Key exports: ``WeChatPaymentPlugin``, ``plugin``, ``WECHAT_COLUMN_REGISTRY``,
``WECHAT_STANDARD_FIELDS``, ``WECHAT_IDENTITY_FIELDS``, ``WECHAT_SCENE_KEYWORDS``.

Dependencies: ``_base.base_table_parser``, ``_base.column_registry``, ``standardizer``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from docmirror.plugins._base.base_table_parser import BaseTableParser
from docmirror.plugins._base.column_registry import ColumnMapping
from docmirror.plugins._base.standardizer import normalize_amount

logger = logging.getLogger(__name__)

WECHAT_COLUMN_REGISTRY: dict[str, ColumnMapping] = {
    "收/支/其他": ColumnMapping(
        field="direction",
        enum_map={"收入": "income", "支出": "expense", "/": "other"},
        aliases=["收/支", "收支其他"],
    ),
    "金额(元)": ColumnMapping(
        field="amount",
        unit="CNY",
        aliases=["金额", "交易金额（元）", "交易金额(元)", "金额（元）"],
    ),
    "交易单号": ColumnMapping(
        field="trade_no",
        aliases=["交易单号/交易编号", "商户订单号", "微信单号"],
    ),
    "交易时间": ColumnMapping(
        field="timestamp",
        format_hint="datetime",
        aliases=["交易日期", "时间", "日期"],
    ),
    "交易对方": ColumnMapping(
        field="counter_party",
        aliases=["对方", "交易对手", "对方名称"],
    ),
    "交易类型": ColumnMapping(
        field="transaction_type",
        aliases=["类型", "交易方式", "支付方式"],
    ),
    "交易对象": ColumnMapping(
        field="counter_object",
        aliases=["对象", "对方账户", "对方账号"],
    ),
}

WECHAT_STANDARD_FIELDS = [
    "direction",
    "counter_party",
    "transaction_type",
    "counter_object",
    "amount",
    "trade_no",
    "timestamp",
]

WECHAT_SCENE_KEYWORDS = (
    "微信支付交易明细证明",
    "财付通",
    "微信流水",
    "WeChat Pay",
    "微信支付",
)

WECHAT_DEFAULT_COLUMNS = list(WECHAT_COLUMN_REGISTRY.keys())

WECHAT_IDENTITY_FIELDS: Sequence[tuple[str, Sequence[str]]] = (
    ("account_holder", ("户名", "姓名", "Account holder")),
    ("account_number", ("账号", "卡号", "Account number")),
    ("query_period", ("查询时间段", "起始日期", "终止日期", "Query period")),
    ("currency", ("币种", "Currency")),
)


class WeChatPaymentPlugin(BaseTableParser):
    """Community v2.0: WeChat Pay statement plugin."""

    @property
    def domain_name(self) -> str:
        return "wechat_payment"

    @property
    def display_name(self) -> str:
        return "WeChat Payment (Community)"

    @property
    def column_registry(self) -> dict[str, ColumnMapping]:
        return WECHAT_COLUMN_REGISTRY

    @property
    def standard_fields(self) -> list[str]:
        return WECHAT_STANDARD_FIELDS

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return WECHAT_IDENTITY_FIELDS

    def build_domain_data(self, _metadata, entities):
        """Legacy KV fallback — prefer ``extract_from_mirror()`` for full v2.0 output."""
        from docmirror.plugins._base.dec_builder import build_dec_kv

        account_holder = str(entities.get("account_holder", metadata.get("Account holder", "")))
        account_number = str(entities.get("account_number", metadata.get("Account number", "")))
        transactions = entities.get("transactions", metadata.get("transactions", []))
        total_income = 0.0
        total_expense = 0.0
        total_transactions = len(transactions) if isinstance(transactions, list) else 0

        if isinstance(transactions, list):
            for txn in transactions:
                try:
                    amount_str = txn.get("金额(元)", txn.get("金额", "0"))
                    amt = normalize_amount(amount_str) or 0.0
                except (ValueError, AttributeError):
                    continue
                direction = txn.get("收/支", txn.get("收/支/其他", ""))
                if "收入" in direction or "存入" in direction:
                    total_income += amt
                elif "支出" in direction or "取出" in direction:
                    total_expense += amt

        return build_dec_kv(
            "wechat_payment",
            {
                "account_holder": account_holder,
                "account_number": account_number,
                "total_transactions": total_transactions,
                "total_income": total_income,
                "total_expense": total_expense,
            },
        )


plugin = WeChatPaymentPlugin()
