# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Bank Statement Domain Plugin (Community Edition)
=================================================

Community edition: scene detection, identity fields, and table records
via BaseTableParser + logical_tables consumption.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from docmirror.plugins._base.base_table_parser import BaseTableParser
from docmirror.plugins._base.column_registry import ColumnMapping

logger = logging.getLogger(__name__)

BANK_COLUMN_REGISTRY: dict[str, ColumnMapping] = {
    "交易日期": ColumnMapping(field="date", format_hint="date", aliases=["日期", "记账日期", "Date"]),
    "交易时间": ColumnMapping(field="timestamp", format_hint="datetime", aliases=["时间", "Time"]),
    "摘要": ColumnMapping(field="summary", aliases=["交易摘要", "Description", "Memo"]),
    "交易金额": ColumnMapping(
        field="amount",
        unit="CNY",
        aliases=["金额", "发生额", "Amount", "借方发生额", "贷方发生额"],
    ),
    "余额": ColumnMapping(field="balance", unit="CNY", aliases=["账户余额", "Balance"]),
    "对方户名": ColumnMapping(field="counter_party", aliases=["对方名称", "交易对方", "Counter party"]),
    "对方账号": ColumnMapping(field="counter_account", aliases=["对方账户", "Counter account"]),
}

BANK_STANDARD_FIELDS = [
    "date",
    "timestamp",
    "summary",
    "amount",
    "balance",
    "counter_party",
    "counter_account",
]

BANK_IDENTITY_FIELDS: Sequence[tuple[str, Sequence[str]]] = (
    ("account_holder", ("Account holder", "Account name", "Card holder", "Customer name", "户名")),
    ("account_number", ("Account number", "Card number", "Customer account number", "账号", "卡号")),
    ("bank_name", ("Bank name", "Bank branch", "银行名称")),
    ("query_period", ("Query period", "From/to date", "Period", "查询时间段")),
    ("currency", ("Currency", "币种")),
)


class BankStatementCommunityPlugin(BaseTableParser):
    """Community edition plugin for bank statement document processing."""

    @property
    def domain_name(self) -> str:
        return "bank_statement"

    @property
    def display_name(self) -> str:
        return "Bank Statement (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def column_registry(self) -> dict[str, ColumnMapping]:
        return BANK_COLUMN_REGISTRY

    @property
    def standard_fields(self) -> list[str]:
        return BANK_STANDARD_FIELDS

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return BANK_IDENTITY_FIELDS

    def build_domain_data(self, metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv
        return build_dec_kv("bank_statement", {
            "account_holder": str(entities.get("account_holder", metadata.get("Account holder", ""))),
            "account_number": str(entities.get("account_number", metadata.get("Account number", ""))),
            "bank_name": str(entities.get("bank_name", "")),
            "query_period": str(entities.get("query_period", metadata.get("Query period", ""))),
            "currency": str(entities.get("currency", "CNY")),
        })



plugin = BankStatementCommunityPlugin()
