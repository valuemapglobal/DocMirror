# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Alipay Payment Domain Plugin (Community Edition)
=================================================

Community edition: extracts transactions from mirror ParseResult,
applies v2.0 universal community output schema.

Archetype: table_document (records + fields + raw + normalized)
Business domain: cashflow_payment

Per docs/design/01_community_edition_architecture_guide_v2.md
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from docmirror.plugins import DomainPlugin

_ALIPAY_KEYWORDS = ("支付宝（中国）网络技术有限公司", "交易流水证明", "Alipay")
_HEADER_MARKERS = ("收/支", "交易对方", "金额", "交易订单号", "交易时间")

_DIRECTION_MAP = {"支出": "expense", "收入": "income", "其他": "other"}

_DEFAULT_COLUMNS = ["收/支", "交易对方", "商品说明", "收/付款方式", "金额", "交易订单号", "商家订单号", "交易时间"]

plugin = None  # set at module bottom


class AlipayPaymentPlugin(DomainPlugin):
    """Community edition v2.0: Alipay payment transactions with raw+normalized fields."""

    # ── Plugin metadata ──

    @property
    def domain_name(self) -> str:
        return "alipay_payment"

    @property
    def display_name(self) -> str:
        return "Alipay Payment (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def scene_keywords(self) -> Sequence[str]:
        return _ALIPAY_KEYWORDS

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("account_holder", ("户名", "姓名", "Account holder")),
            ("account_number", ("账号", "卡号", "Account number")),
            ("query_period", ("查询时间段", "起始日期", "终止日期", "Query period")),
            ("currency", ("币种", "Currency")),
        )

    # ── Public API ──

    def extract_from_mirror(self, parse_result, text: str = "") -> dict[str, Any]:
        """Extract and return standardized v2.0 community output."""
        # Step 1: Extract identity fields from KV
        identity_fields = self._extract_identity(parse_result)

        # Step 2: Extract transactions
        transactions, headers = self._extract(parse_result)

        # Step 3: Build records (raw + normalized)
        records = self._build_records(transactions)

        # Step 4: Summary
        summary = self._build_summary(records)

        # Step 5: Period
        period = self._extract_period(text) or summary.get("period", {})

        # Step 6: Build v2.0 output
        return self._build_output(
            parse_result, identity_fields, records, headers, summary, period, text=text,
        )

    # ── Step 1: Identity fields ──

    @staticmethod
    def _extract_identity(parse_result) -> dict[str, dict]:
        """Extract identity fields from mirror KV pairs.

        Returns {field_key: {raw_name, raw_value, normalized_value, data_type}}.
        """
        fields: dict[str, dict] = {}
        if not parse_result or not hasattr(parse_result, "pages"):
            return fields

        for page in parse_result.pages:
            for kv in page.key_values:
                key = kv.key.strip()
                val = kv.value.strip()
                if "兹证明" in key:
                    name = re.sub(r"\(.*", "", val).strip()
                    if name:
                        fields["account_holder"] = {
                            "raw_name": key,
                            "raw_value": val,
                            "normalized_value": name,
                            "data_type": "string",
                        }
                elif "证件号码" in key:
                    m = re.search(r"(\d{6,})", val)
                    if m:
                        fields["account_number"] = {
                            "raw_name": key,
                            "raw_value": val,
                            "normalized_value": m.group(1),
                            "data_type": "string",
                        }
                elif key in ("币种", "Currency"):
                    fields["currency"] = {
                        "raw_name": key,
                        "raw_value": val,
                        "normalized_value": "CNY" if "人民" in val else val,
                        "data_type": "string",
                    }
        return fields

    # ── Step 2: Extract transactions ──

    @staticmethod
    def _extract(parse_result) -> tuple[list[dict[str, str]], list[str]]:
        """Extract raw transaction dicts from ParseResult tables.

        Uses table_access layer: reads logical_tables first (composed,
        cross-page), falls back to physical pages[].tables (legacy).
        """
        if not parse_result or not hasattr(parse_result, "pages"):
            return [], []

        all_rows: list[list[str]] = []
        from docmirror.core.table.table_access import get_logical_tables, table_flatten

        logical = get_logical_tables(parse_result)
        if logical:
            # Logical tables already composed — flatten directly
            for lt in logical:
                for row in lt.rows:
                    all_rows.append([c.text for c in row.cells])
        else:
            # Fallback to physical per-page tables (legacy)
            for page in parse_result.pages:
                for table in page.tables:
                    for row in table.rows:
                        all_rows.append([c.text for c in row.cells])

        if not all_rows:
            return [], []

        header_idx = -1
        actual_headers: list[str] = []
        for i, row in enumerate(all_rows[:12]):
            if sum(1 for m in _HEADER_MARKERS if any(m in (c or "") for c in row)) >= 3:
                header_idx = i
                actual_headers = [str(c or "").strip() for c in row]
                break

        if not actual_headers:
            col_count = max((len(r) for r in all_rows[:10] if r), default=8)
            actual_headers = _DEFAULT_COLUMNS[:col_count]
            header_idx = -1

        col_map = {h: i for i, h in enumerate(actual_headers) if h.strip()}
        start = header_idx + 1 if header_idx >= 0 else 0

        transactions: list[dict[str, str]] = []
        for row in all_rows[start:]:
            if not row or not any(str(c).strip() for c in row):
                continue
            first = str(row[0] or "").strip()
            if first in ("", "收/支"):
                continue
            if first not in ("支出", "收入", "其他"):
                continue

            txn: dict[str, str] = {}
            for h, idx in col_map.items():
                if idx < len(row):
                    txn[h] = str(row[idx] or "").strip().replace("\n", "")
            if any(txn.values()):
                transactions.append(txn)

        return transactions, actual_headers

    # ── Step 3: Build records (raw + normalized) ──

    def _build_records(self, transactions: list[dict[str, str]]) -> list[dict]:
        """Build records with raw + normalized per v2.0 spec."""
        records = []
        for i, raw_txn in enumerate(transactions, start=1):
            records.append({
                "row_index": i,
                "raw": dict(raw_txn),
                "normalized": self._normalize(raw_txn),
            })
        return records

    @staticmethod
    def _normalize_amount(raw: str) -> float | None:
        cleaned = re.sub(r"[¥￥,，\s]", "", raw.strip())
        if not cleaned:
            return None
        try:
            return round(float(cleaned), 2)
        except ValueError:
            return None

    @staticmethod
    def _normalize_timestamp(raw: str) -> str:
        raw = raw.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).isoformat()
            except ValueError:
                continue
        return raw

    def _normalize(self, raw_txn: dict[str, str]) -> dict[str, Any]:
        direction_raw = raw_txn.get("收/支", "")
        amount_raw = raw_txn.get("金额", "")
        ts_raw = raw_txn.get("交易时间", "")
        return {
            "direction": _DIRECTION_MAP.get(direction_raw, direction_raw),
            "counter_party": raw_txn.get("交易对方", ""),
            "description": raw_txn.get("商品说明", ""),
            "payment_method": raw_txn.get("收/付款方式", raw_txn.get("收/支方式", "")),
            "amount": self._normalize_amount(amount_raw),
            "trade_no": raw_txn.get("交易订单号", ""),
            "merchant_no": raw_txn.get("商家订单号", raw_txn.get("商户单号", "")),
            "timestamp": self._normalize_timestamp(ts_raw),
        }

    # ── Step 4: Summary ──

    @staticmethod
    def _build_summary(records: list[dict]) -> dict[str, Any]:
        income_recs = [r for r in records if r.get("normalized", {}).get("direction") == "income"]
        expense_recs = [r for r in records if r.get("normalized", {}).get("direction") == "expense"]
        other_recs = [r for r in records if r.get("normalized", {}).get("direction") == "other"]

        income_amounts = [r["normalized"]["amount"] for r in income_recs if r["normalized"].get("amount") is not None]
        expense_amounts = [r["normalized"]["amount"] for r in expense_recs if r["normalized"].get("amount") is not None]

        total_income = round(sum(income_amounts), 2) if income_amounts else 0.0
        total_expense = round(sum(expense_amounts), 2) if expense_amounts else 0.0

        all_ts = sorted(
            r["normalized"]["timestamp"] for r in records if r["normalized"].get("timestamp")
        )
        period = {}
        if len(all_ts) >= 2:
            period = {"start": all_ts[0][:10], "end": all_ts[-1][:10]}
        elif len(all_ts) == 1:
            period = {"start": all_ts[0][:10], "end": all_ts[0][:10]}

        return {
            "total_rows": len(records),
            "total_income": total_income,
            "total_expense": total_expense,
            "net_flow": round(total_income - total_expense, 2),
            "period": period,
            "statistics": {
                "income_count": len(income_recs),
                "expense_count": len(expense_recs),
                "other_count": len(other_recs),
                "avg_income": round(total_income / len(income_recs), 2) if income_recs else 0.0,
                "avg_expense": round(total_expense / len(expense_recs), 2) if expense_recs else 0.0,
                "max_income": round(max(income_amounts), 2) if income_amounts else 0.0,
                "max_expense": round(max(expense_amounts), 2) if expense_amounts else 0.0,
            },
        }

    # ── Helpers ──

    @staticmethod
    def _extract_period(text: str) -> str:
        m = re.search(
            r"(\d{4}[-./年]\d{1,2}[-./月]\d{1,2}日?\s*[~\-至]\s*\d{4}[-./年]\d{1,2}[-./月]\d{1,2}日?)", text
        )
        return m.group(1) if m else ""

    # ── Build v2.0 community output ──

    def _build_output(
        self,
        parse_result,
        identity_fields: dict[str, dict],
        records: list[dict],
        headers: list[str],
        summary: dict[str, Any],
        period: str | dict,
        *,
        text: str = "",
    ) -> dict[str, Any]:
        from docmirror.plugins._base.table_dec import serialize_table_plugin_output

        return serialize_table_plugin_output(
            self,
            parse_result,
            identity_fields=identity_fields,
            records=records,
            summary=summary,
            text=text,
            domain="cashflow_payment",
            match_method="keyword_driven",
        )


plugin = AlipayPaymentPlugin()
