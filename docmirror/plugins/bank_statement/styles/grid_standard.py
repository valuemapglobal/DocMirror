# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Standard multi-column grid bank ledger style parser.

Default parser for clearly tabulated ledgers: strict header detection, split
debit/credit column merging, and per-row normalization through plugin column registry.

Pipeline role: primary and fallback parser in ``style_registry``; also used by
``signed_amount`` for shared row harvest paths.

Key exports: ``PARSER_ID``, ``STYLE_ID``, ``normalize_split_debit_credit``,
``extract_transactions``.

Dependencies: ``header_resolve``, ``row_extract``, ``institution``, ``standardizer``.
"""

from __future__ import annotations

from typing import Any

from docmirror.plugins._base.standardizer import normalize_amount
from docmirror.plugins.bank_statement.header_resolve import (
    detect_headers,
    has_split_debit_credit_headers,
    normalize_header_cell,
)
from docmirror.plugins.bank_statement.institution import match_institution, normalize_table_headers
from docmirror.plugins.bank_statement.row_extract import extract_all_tables, extract_rows_from_header

PARSER_ID = "grid_standard"
STYLE_ID = "grid_standard"

_SPLIT_DEBIT_KEYS = ("支出", "支出金额", "借方发生额", "借方")
_SPLIT_CREDIT_KEYS = ("收入", "收入金额", "贷方发生额", "贷方")


def _cell_value(raw_txn: dict[str, str], *needles: str) -> str:
    for key, value in raw_txn.items():
        norm_key = normalize_header_cell(key)
        for needle in needles:
            if key == needle or needle in key or norm_key == normalize_header_cell(needle):
                return str(value or "").strip()
    return ""


def normalize_split_debit_credit(raw_txn: dict[str, str], plugin: Any) -> dict[str, Any] | None:
    """Parse separate debit/credit columns into amount + direction."""
    income = normalize_amount(_cell_value(raw_txn, *_SPLIT_CREDIT_KEYS))
    expense = normalize_amount(_cell_value(raw_txn, *_SPLIT_DEBIT_KEYS))
    if income is None and expense is None:
        return None
    income = float(income or 0)
    expense = float(expense or 0)
    if income <= 0 and expense <= 0:
        return None

    normalized = plugin._normalize(raw_txn)
    balance = normalize_amount(_cell_value(raw_txn, "余额", "账户余额", "本次余额", "账面余额"))
    if balance is not None:
        normalized["balance"] = float(balance)

    if not str(normalized.get("counter_party", "") or "").strip():
        cp = _cell_value(
            raw_txn,
            "备注",
            "对方户名",
            "对方账号与户名",
            "交易对方",
            "Remarks",
        )
        if cp:
            normalized["counter_party"] = cp

    if income > 0:
        normalized["amount"] = income
        normalized["amount_cny"] = income
        normalized["direction"] = "income"
    else:
        normalized["amount"] = expense
        normalized["amount_cny"] = expense
        normalized["direction"] = "expense"
    return normalized


def _extract_split_grid_records(
    tables: list[list[list[str]]],
    header_row_idx: int,
    raw_headers: list[str],
) -> list[dict[str, str]]:
    transactions: list[dict[str, str]] = []
    for tbl in tables:
        if not tbl or header_row_idx >= len(tbl):
            continue
        for row in tbl[header_row_idx + 1 :]:
            if not row or not any(str(c).strip() for c in row):
                continue
            first_cell = str(row[0] or "").strip()
            if any(kw in first_cell for kw in ("合计", "小计", "本页", "总计")):
                continue
            txn: dict[str, str] = {}
            for idx, cell in enumerate(row):
                header = raw_headers[idx] if idx < len(raw_headers) else f"col_{idx}"
                txn[header] = str(cell or "").strip()
            if any(txn.values()):
                transactions.append(txn)
    return transactions


def extract_transactions(ctx: StyleContext, plugin: Any) -> list[dict[str, str]]:
    variant = match_institution(ctx.full_text, ctx.institution)
    tables = normalize_table_headers(ctx.tables, variant=variant)

    split_txns: list[dict[str, str]] = []
    for tbl in tables:
        if not tbl:
            continue
        for row_idx, row in enumerate(tbl[:15]):
            raw_headers = [str(c or "").strip() for c in row]
            if has_split_debit_credit_headers([[raw_headers]]):
                split_txns.extend(_extract_split_grid_records([tbl], row_idx, raw_headers))
                break
    if split_txns:
        return split_txns

    batch = extract_all_tables(
        tables,
        plugin.column_registry,
        prefer_strict=True,
        strict_first_col=True,
    )
    if batch:
        return batch

    header = detect_headers(tables, plugin.column_registry, prefer_strict=True)
    if header is None:
        header_row_idx, raw_headers, col_map = plugin._detect_headers(tables)
        return plugin._extract_records(tables, header_row_idx, raw_headers, col_map)

    raw_headers = header.raw_headers
    if has_split_debit_credit_headers([[raw_headers]]):
        return _extract_split_grid_records(tables, header.row_index, raw_headers)

    rows = extract_rows_from_header(
        tables,
        header,
        plugin.column_registry,
        strict_first_col=True,
    )
    if rows:
        return rows

    header_row_idx, raw_headers, col_map = plugin._detect_headers(tables)
    return plugin._extract_records(tables, header_row_idx, raw_headers, col_map)


def normalize_record(raw_txn: dict[str, str], plugin: Any) -> dict[str, Any]:
    if raw_txn.get("_compact") == "1":
        from docmirror.plugins.bank_statement.styles.compact_merged import normalize_record as compact_norm

        return compact_norm(raw_txn)

    split = normalize_split_debit_credit(raw_txn, plugin)
    if split is not None:
        from docmirror.plugins._base.standardizer import normalize_timestamp

        if not split.get("date"):
            date_keys = ("交易日期", "记账日", "记账日期", "日期", "交易时间")
            for key in date_keys:
                norm_key = normalize_header_cell(key)
                for raw_key, raw_val in raw_txn.items():
                    if not str(raw_val or "").strip():
                        continue
                    if normalize_header_cell(raw_key) == norm_key or key in raw_key:
                        split["date"] = normalize_timestamp(str(raw_val))[:10]
                        break
                if split.get("date"):
                    break
        return split

    from docmirror.plugins.bank_statement.styles.signed_amount import parse_signed_amount

    for key, value in raw_txn.items():
        if any(n in key for n in ("金额", "发生", "Amount")) and str(value).strip().startswith(("+", "-")):
            amount, direction = parse_signed_amount(str(value))
            if amount is not None:
                normalized = plugin._normalize(raw_txn)
                normalized["amount"] = amount
                normalized["amount_cny"] = amount
                normalized["direction"] = direction
                return normalized

    return plugin._normalize(raw_txn)
