# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Bank statement community plugin — style-aware ledger extract.

Premium community plugin for ``bank_statement`` documents. Extends ``BaseTableParser``
with a style detection pipeline (``BankStyleDetector`` → ``BankStyleParserRegistry``)
that selects among grid, compact merged, signed amount, borderless OCR, and KV
identity parsers before building canonical transaction records and DEC output.

Pipeline role: registered as ``plugin`` for ``registry`` discovery; ``runner`` invokes
``extract_from_mirror`` on matched Mirror tables and OCR text fallback.

Key exports: ``BankStatementCommunityPlugin``, ``plugin``, column/identity config constants.

Dependencies: ``_base.base_table_parser``, ``bank_statement.extract_pipeline``, ``table_dec``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from docmirror.models.edition_serializer import EditionContext, edition_serializer
from docmirror.plugins._base.base_table_parser import BaseTableParser
from docmirror.plugins._base.column_registry import ColumnMapping
from docmirror.plugins._base.table_dec import build_table_dec
from docmirror.plugins.bank_statement.extract_pipeline import run_bank_statement_extract

BANK_COLUMN_REGISTRY: dict[str, ColumnMapping] = {
    "交易日期": ColumnMapping(field="date", format_hint="date", aliases=["日期", "记账日期", "记账日", "Date"]),
    "交易时间": ColumnMapping(field="timestamp", format_hint="datetime", aliases=["时间", "Time"]),
    "摘要": ColumnMapping(field="summary", aliases=["交易摘要", "Description", "Memo"]),
    "交易金额": ColumnMapping(
        field="amount",
        unit="CNY",
        aliases=["金额", "发生额", "Amount", "借方发生额", "贷方发生额", "收入金额", "支出金额"],
    ),
    "余额": ColumnMapping(field="balance", unit="CNY", aliases=["账户余额", "Balance"]),
    "对方户名": ColumnMapping(
        field="counter_party",
        aliases=[
            "对方名称",
            "交易对方",
            "Counter party",
            "备注",
            "Remarks",
            "对方账号与户名",
        ],
    ),
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
    ("account_holder", ("Account holder", "Account name", "Card holder", "Customer name", "户名", "账户名")),
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

    def extract_from_mirror(self, parse_result, text: str = ""):
        """StyleDetector → Registry → v2.0 community output with style metadata."""
        result = run_bank_statement_extract(parse_result, text, self)
        summary = self._build_summary(result.records)
        style_props = result.style_meta.to_properties()

        dec = build_table_dec(
            document_type=self.domain_name,
            identity_fields=result.identity_fields,
            records=result.records,
            summary=summary,
            properties=style_props,
            metadata=dict(style_props),
        )
        if result.warnings:
            dec.quality.issues.extend(f"warning:{w}" for w in result.warnings)
        if result.style_meta.extract_status == "degraded":
            dec.quality.validation_passed = False
            dec.quality.issues.append("error:cqf_degraded")

        file_path = getattr(parse_result, "file_path", "") or ""
        doc_name = Path(file_path).name if file_path else self.display_name
        page_count = len(getattr(parse_result, "pages", []) or [])

        edition_ctx = EditionContext(
            edition=self.edition,
            detected_type=self.domain_name,
            full_text=text,
            document_name=doc_name,
            page_count=page_count,
            archetype="table_document",
            domain="cashflow_payment",
            match_method="style_family",
            scene_keywords=getattr(self, "scene_keywords", ()) or (),
            plugin_name=self.domain_name,
            plugin_display_name=self.display_name,
            plugin_version="community-2.0",
            support_level="L2",
            parser_label="docmirror-community",
        )
        return edition_serializer(dec, context=edition_ctx)


plugin = BankStatementCommunityPlugin()
