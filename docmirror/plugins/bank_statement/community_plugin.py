# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Bank statement community plugin — style-aware ledger extract.

Premium community plugin for ``bank_statement`` documents. Extends ``BaseTableParser``
with a style detection pipeline (``BankStyleDetector`` → ``BankStyleParserRegistry``)
that selects among grid, compact merged, signed amount, borderless OCR, and KV
identity parsers before building canonical transaction records and DEC output.

Pipeline role: registered as ``plugin`` for ``registry`` discovery; ``runner`` invokes
``recognize`` on canonical tables and OCR evidence fallback.

Key exports: ``BankStatementCommunityPlugin``, ``plugin``, column/identity config constants.

Dependencies: ``_base.base_table_parser``, ``bank_statement.extract_pipeline``, ``table_dec``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from docmirror.models.edition_serializer import EditionContext, edition_serializer
from docmirror.plugin_api import FactPatch
from docmirror.plugins._base.base_table_parser import BaseTableParser
from docmirror.plugins._base.column_registry import ColumnMapping
from docmirror.plugins._base.table_dec import build_table_dec
from docmirror.plugins.bank_statement.extract_pipeline import run_bank_statement_extract

BANK_COLUMN_REGISTRY: dict[str, ColumnMapping] = {
    "序号": ColumnMapping(field="sequence_no", aliases=["No.", "序列号"]),
    "交易日期": ColumnMapping(field="date", format_hint="date", aliases=["日期", "记账日期", "记账日", "Date"]),
    "交易时间": ColumnMapping(field="timestamp", format_hint="datetime", aliases=["时间", "Time"]),
    "收/支": ColumnMapping(
        field="direction",
        enum_map={
            "收入": "income",
            "收人": "income",
            "支出": "expense",
            "支山": "expense",
            "支鼎": "expense",
            "攴出": "expense",
        },
        aliases=["收支", "方向", "交易方向", "月收/支", "月收支"],
    ),
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
    "对方行号": ColumnMapping(field="counter_bank_code", aliases=["对方银行行号"]),
    "对方行名": ColumnMapping(field="counter_bank_name", aliases=["对方开户行", "对方银行名称"]),
    "交易渠道": ColumnMapping(field="channel", aliases=["渠道", "交易方式"]),
    "用途": ColumnMapping(field="purpose", aliases=["交易用途"]),
}

BANK_STANDARD_FIELDS = [
    "date",
    "timestamp",
    "summary",
    "direction",
    "amount",
    "balance",
    "counter_party",
    "counter_account",
    "sequence_no",
    "counter_bank_code",
    "counter_bank_name",
    "channel",
    "purpose",
    "counterparty_status",
]

BANK_IDENTITY_FIELDS: Sequence[tuple[str, Sequence[str]]] = (
    ("account_holder", ("Account holder", "Account name", "Card holder", "Customer name", "户名", "账户名")),
    ("account_number", ("Account number", "Card number", "Customer account number", "账号", "账户号", "卡号")),
    ("bank_name", ("Bank name", "Bank branch", "银行名称")),
    ("query_period", ("Query period", "From/to date", "Period", "查询时间段", "交易时段")),
    ("print_date", ("打印日期",)),
    ("total_transactions", ("总笔数", "总条数")),
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

    def _recover_identity_from_evidence(self, parse_result) -> dict[str, dict[str, object]]:
        atoms_by_page = self._evidence_text_atoms_by_page(parse_result)
        if not atoms_by_page:
            return {}
        page_id = sorted(atoms_by_page)[0]
        atoms = sorted(
            atoms_by_page[page_id],
            key=lambda atom: (float(atom["bbox"][1]), float(atom["bbox"][0])),
        )
        text = " ".join(str(atom.get("text") or "").strip() for atom in atoms)
        patterns = {
            "print_date": ("打印日期", r"打印日期\s*[:：]\s*(20\d{2}-\d{2}-\d{2})"),
            "query_period": (
                "交易时段",
                r"交易时段\s*[:：]\s*(20\d{2}-\d{2}-\d{2})\s*至\s*(20\d{2}-\d{2}-\d{2})",
            ),
            "total_transactions": ("总条数", r"(?:总笔数|总条数)\s*[:：]\s*(\d+)"),
            "account_holder": ("户名", r"户名\s*[:：]\s*(.+?)(?=\s+账号\s*[:：])"),
            "account_number": ("账号", r"账号\s*[:：]\s*([0-9*]+)"),
            "currency": ("币种", r"币种\s*[:：]\s*([^\s]+)"),
        }
        recovered: dict[str, dict[str, object]] = {}
        for field_name, (label, pattern) in patterns.items():
            match = re.search(pattern, text)
            if not match:
                continue
            value = " 至 ".join(match.groups()) if field_name == "query_period" else match.group(1).strip()
            if value:
                recovered[field_name] = self._evidence_identity_detail(field_name, label, value, page_id=page_id)
        title_atom = next(
            (atom for atom in atoms if "账户交易明细表" in str(atom.get("text") or "")),
            None,
        )
        if title_atom is not None:
            title = str(title_atom.get("text") or "").strip()
            recovered["statement_title"] = self._evidence_identity_detail(
                "statement_title",
                "document_title",
                title,
                page_id=page_id,
                evidence_ids=[str(title_atom.get("id") or "")],
            )
        return recovered

    def build_domain_data(self, _metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv

        return build_dec_kv(
            "bank_statement",
            {
                "account_holder": str(entities.get("account_holder", _metadata.get("Account holder", ""))),
                "account_number": str(entities.get("account_number", _metadata.get("Account number", ""))),
                "bank_name": str(entities.get("bank_name", "")),
                "query_period": str(entities.get("query_period", _metadata.get("Query period", ""))),
                "currency": str(entities.get("currency", "CNY")),
            },
        )

    def recognize(self, parse_result, text: str = ""):
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

    def recognize_facts(self, parse_result, text: str = "") -> FactPatch:
        """Run the style-aware extractor and return canonical facts directly."""
        result = run_bank_statement_extract(parse_result, text, self)
        summary = self._build_summary(result.records)
        patch = self._fact_patch_from_components(
            identity_fields=result.identity_fields,
            records=result.records,
            raw_headers=[],
            summary=summary,
            period=summary.get("period", {}),
            extra_domain_facts=result.style_meta.to_properties(),
            warnings=result.warnings,
            confidence=1.0 if result.style_meta.extract_status != "degraded" else 0.5,
        )
        identity_values: dict[str, str] = {}
        for field_name, detail in result.identity_fields.items():
            value = detail
            if isinstance(detail, dict):
                value = next(
                    (
                        detail.get(candidate)
                        for candidate in ("normalized_value", "value", "raw_value")
                        if detail.get(candidate) not in (None, "")
                    ),
                    None,
                )
            if value not in (None, ""):
                identity_values[field_name] = str(value)
        entity_fields = {
            target: identity_values[source]
            for source, target in (
                ("account_holder", "subject_name"),
                ("account_number", "subject_id"),
                ("bank_name", "organization"),
            )
            if identity_values.get(source)
        }
        return patch.model_copy(update={"entity_fields": entity_fields})


plugin = BankStatementCommunityPlugin()
