# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Alipay payment community domain plugin (v2.0).

Premium community plugin for Alipay transaction proof PDFs. Extends ``BaseTableParser``
with Alipay column registry, header marker heuristics, default column ordering for
headerless tables, and normalized field alignment with finance edition plugins.

Pipeline role: discovered as ``alipay_payment`` premium plugin; ``runner`` calls
``extract_from_mirror`` after Mirror classification.

Archetype: ``table_document``; domain: ``cashflow_payment``; support level: L2.

Key exports: ``AlipayPaymentPlugin``, ``plugin``, ``ALIPAY_COLUMN_REGISTRY``,
``ALIPAY_STANDARD_FIELDS``, ``ALIPAY_IDENTITY_FIELDS``.

Dependencies: ``_base.base_table_parser``, ``ColumnMatcher``, ``standardizer``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from docmirror.plugins._base.base_table_parser import BaseTableParser
from docmirror.plugins._base.column_registry import ColumnMapping, ColumnMatcher
from docmirror.plugins._base.standardizer import normalize_amount

logger = logging.getLogger(__name__)

_ALIPAY_KEYWORDS = ("支付宝（中国）网络技术有限公司", "交易流水证明", "Alipay")
_HEADER_MARKERS = ("收/支", "交易对方", "金额", "交易订单号", "交易时间")
_DIRECTION_VALUES = frozenset({"支出", "收入", "其他"})
_DEFAULT_COLUMNS = [
    "收/支",
    "交易对方",
    "商品说明",
    "收/付款方式",
    "金额",
    "交易订单号",
    "商家订单号",
    "交易时间",
]

ALIPAY_COLUMN_REGISTRY: dict[str, ColumnMapping] = {
    "收/支": ColumnMapping(
        field="direction",
        enum_map={"支出": "expense", "收入": "income", "其他": "other"},
        aliases=["收支"],
    ),
    "金额": ColumnMapping(field="amount", unit="CNY", aliases=["交易金额"]),
    "交易订单号": ColumnMapping(field="trade_no", aliases=["订单号"]),
    "交易时间": ColumnMapping(
        field="timestamp",
        format_hint="datetime",
        aliases=["交易日期", "时间", "日期"],
    ),
    "交易对方": ColumnMapping(field="counter_party", aliases=["对方", "交易对手"]),
    "商品说明": ColumnMapping(field="description", aliases=["说明", "备注"]),
    "收/付款方式": ColumnMapping(
        field="payment_method",
        aliases=["收/支方式", "付款方式", "支付方式"],
    ),
    "商家订单号": ColumnMapping(
        field="merchant_no",
        aliases=["商户单号", "商家单号"],
    ),
}

ALIPAY_STANDARD_FIELDS = [
    "direction",
    "counter_party",
    "description",
    "payment_method",
    "amount",
    "trade_no",
    "merchant_no",
    "timestamp",
]

ALIPAY_IDENTITY_FIELDS: Sequence[tuple[str, Sequence[str]]] = (
    ("account_holder", ("户名", "姓名", "Account holder")),
    ("account_number", ("账号", "卡号", "Account number")),
    ("query_period", ("查询时间段", "起始日期", "终止日期", "Query period")),
    ("currency", ("币种", "Currency")),
)


class AlipayPaymentPlugin(BaseTableParser):
    """社区版 v2.0：支付宝流水插件（BaseTableParser + 收/支首列行过滤）。"""

    @property
    def domain_name(self) -> str:
        return "alipay_payment"

    @property
    def display_name(self) -> str:
        return "Alipay Payment (Community)"

    @property
    def scene_keywords(self) -> Sequence[str]:
        return _ALIPAY_KEYWORDS

    @property
    def column_registry(self) -> dict[str, ColumnMapping]:
        return ALIPAY_COLUMN_REGISTRY

    @property
    def standard_fields(self) -> list[str]:
        return ALIPAY_STANDARD_FIELDS

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return ALIPAY_IDENTITY_FIELDS

    def _detect_headers(
        self,
        tables: list[list[list[str]]],
    ) -> tuple[int, list[str], dict[str, int]]:
        """表头检测：ColumnMatcher 优先，否则按支付宝 marker 行 + 默认列 fallback。"""
        header_row_idx, raw_headers, col_map = super()._detect_headers(tables)
        if len(col_map) >= 3:
            return header_row_idx, raw_headers, col_map

        matcher = ColumnMatcher(self.column_registry)
        for tbl in tables:
            if not tbl:
                continue
            for row_idx, row in enumerate(tbl[:12]):
                if sum(1 for marker in _HEADER_MARKERS if any(marker in (c or "") for c in row)) >= 3:
                    raw_headers = [str(c or "").strip() for c in row]
                    col_map = matcher.match(raw_headers)
                    if len(col_map) < 3:
                        col_map = {h: i for i, h in enumerate(raw_headers) if h.strip()}
                    return row_idx, raw_headers, col_map

        for tbl in tables:
            if not tbl:
                continue
            col_count = max((len(r) for r in tbl[:10] if r), default=8)
            raw_headers = _DEFAULT_COLUMNS[:col_count]
            return 0, raw_headers, matcher.match(raw_headers)

        return 0, [], {}

    def _extract_records(
        self,
        tables: list[list[list[str]]],
        header_row_idx: int,
        raw_headers: list[str],
        col_map: dict[str, int],
    ) -> list[dict[str, str]]:
        """支付宝流水首列为收/支，需按方向枚举过滤数据行（非日期首列）。"""
        transactions: list[dict[str, str]] = []
        has_col_map = bool(col_map)

        for tbl in tables:
            if not tbl:
                continue
            start = header_row_idx + 1 if 0 <= header_row_idx < len(tbl) else 0

            for row in tbl[start:]:
                if not row or not any(str(c).strip() for c in row):
                    continue

                first_cell = str(row[0] or "").strip()
                if first_cell in ("", "收/支"):
                    continue
                if first_cell not in _DIRECTION_VALUES:
                    continue

                if has_col_map:
                    txn: dict[str, str] = {}
                    for field_name, col_idx in col_map.items():
                        if col_idx < len(row):
                            header_key = raw_headers[col_idx] if col_idx < len(raw_headers) else f"col_{col_idx}"
                            txn[header_key] = str(row[col_idx] or "").strip().replace("\n", "")
                    if any(txn.values()):
                        transactions.append(txn)
                else:
                    txn = {}
                    for i, cell in enumerate(row):
                        header_key = raw_headers[i] if i < len(raw_headers) else f"col_{i}"
                        txn[header_key] = str(cell or "").strip().replace("\n", "")
                    if any(txn.values()):
                        transactions.append(txn)

        return transactions

    def build_domain_data(self, _metadata, entities):
        """Legacy KV fallback — prefer ``extract_from_mirror()`` for full v2.0 output."""
        from docmirror.plugins._base.dec_builder import build_dec_kv

        transactions = entities.get("transactions", metadata.get("transactions", []))
        total_income = 0.0
        total_expense = 0.0
        total_transactions = len(transactions) if isinstance(transactions, list) else 0

        if isinstance(transactions, list):
            for txn in transactions:
                direction = txn.get("收/支", "")
                amount_str = txn.get("金额", "0")
                amt = normalize_amount(amount_str) or 0.0
                if direction == "收入":
                    total_income += amt
                elif direction == "支出":
                    total_expense += amt

        return build_dec_kv(
            "alipay_payment",
            {
                "account_holder": str(entities.get("account_holder", metadata.get("Account holder", ""))),
                "account_number": str(entities.get("account_number", metadata.get("Account number", ""))),
                "total_transactions": total_transactions,
                "total_income": total_income,
                "total_expense": total_expense,
            },
        )


plugin = AlipayPaymentPlugin()
