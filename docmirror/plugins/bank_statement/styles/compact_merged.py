# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Compact merged-column bank ledger style parser.

Parses layouts where date, expense, income, and balance share one or few merged
header/cells (common in certain regional bank exports). Uses ``row_pair_merge`` for
multiline continuation rows.

Pipeline role: registered as ``compact_merged`` in ``style_registry``; also re-exported
via deprecated ``_base.bank_compact_parser`` shim.

Key exports: ``PARSER_ID``, ``STYLE_ID``, ``is_compact_ledger_header``,
``parse_compact_ledger_cell``, ``table_has_compact_ledger``, ``extract_transactions``.

Dependencies: ``row_pair_merge.pair_ledger_rows``.
"""

from __future__ import annotations

import re
from typing import Any

_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
from docmirror.plugins.bank_statement.styles.row_pair_merge import pair_ledger_rows
_AMOUNT_RE = re.compile(r"\d+\.\d{2}")
_INCOME_KEYWORDS = ("结息", "利息", "入息", "转入", "收入")

PARSER_ID = "compact_merged"
STYLE_ID = "compact_merged_ledger"


def is_compact_ledger_header(headers: list[str]) -> bool:
    """True when a single header cell merges 日期+支出+收入+余额 (银座等 compact layout)."""
    for header in headers:
        text = str(header or "").replace(" ", "").replace("\n", "")
        if not text:
            continue
        if all(token in text for token in ("日期", "支出", "收入", "余额")):
            return True
    return False


def parse_compact_ledger_cell(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    match = _DATE_PREFIX_RE.match(text)
    if not match:
        return {}

    date = match.group(1)
    rest = text[len(date):]
    amounts = [float(a) for a in _AMOUNT_RE.findall(rest)]
    parsed: dict[str, Any] = {
        "date": date,
        "expense": 0.0,
        "income": 0.0,
        "balance": None,
    }

    if len(amounts) >= 3:
        parsed["expense"] = amounts[-3]
        parsed["income"] = amounts[-2]
        parsed["balance"] = amounts[-1]
    elif len(amounts) == 2:
        parsed["_ambiguous_amount"] = amounts[0]
        parsed["balance"] = amounts[1]
    elif len(amounts) == 1:
        parsed["balance"] = amounts[0]

    return parsed


def resolve_amount_fields(parsed: dict[str, Any], summary: str = "") -> dict[str, Any]:
    if parsed.get("expense", 0) > 0:
        parsed["amount"] = parsed["expense"]
        parsed["direction"] = "expense"
    elif parsed.get("income", 0) > 0:
        parsed["amount"] = parsed["income"]
        parsed["direction"] = "income"
    elif parsed.get("_ambiguous_amount") is not None:
        amt = float(parsed["_ambiguous_amount"])
        if any(kw in summary for kw in _INCOME_KEYWORDS):
            parsed["amount"] = amt
            parsed["income"] = amt
            parsed["direction"] = "income"
        else:
            parsed["amount"] = amt
            parsed["expense"] = amt
            parsed["direction"] = "expense"
        del parsed["_ambiguous_amount"]
    else:
        parsed["amount"] = 0.0
        parsed["direction"] = "other"
    return parsed


def parse_counterparty_cell(text: str) -> tuple[str, str]:
    text = (text or "").strip()
    match = re.match(r"^(\d{10,})(.*)$", text)
    if match:
        return match.group(1), match.group(2).strip()
    return "", text


def normalize_compact_transaction(raw: dict[str, str]) -> dict[str, Any]:
    ledger = parse_compact_ledger_cell(raw.get("ledger_cell", ""))
    if not ledger:
        return {}

    summary = str(raw.get("summary", "")).strip()
    ledger = resolve_amount_fields(ledger, summary)
    account, name = parse_counterparty_cell(raw.get("counterparty_cell", ""))

    timestamp = raw.get("time_cell", "").strip()
    if timestamp and ledger.get("date"):
        timestamp = f"{ledger['date']} {timestamp}"

    return {
        "date": ledger.get("date", ""),
        "timestamp": timestamp,
        "summary": summary,
        "amount": ledger.get("amount", 0.0),
        "amount_cny": ledger.get("amount", 0.0),
        "balance": ledger.get("balance"),
        "counter_party": name,
        "counter_account": account,
        "direction": ledger.get("direction", "other"),
    }


def extract_compact_ledger_transactions(table: list[list[str]]) -> list[dict[str, str]]:
    if not table:
        return []

    header_idx = -1
    headers: list[str] = []
    for i, row in enumerate(table[:12]):
        row_headers = [str(c or "") for c in row]
        if is_compact_ledger_header(row_headers):
            header_idx = i
            headers = row_headers
            break
    if header_idx < 0:
        return []

    col_ledger, col_cp, col_summary = 0, 1, 2
    for i, header in enumerate(headers):
        if "日期" in header or "余额" in header:
            col_ledger = i
        elif "对方" in header or "户名" in header:
            col_cp = i
        elif "摘要" in header or "附言" in header:
            col_summary = i

    return pair_ledger_rows(
        table,
        header_idx=header_idx,
        col_ledger=col_ledger,
        col_cp=col_cp,
        col_summary=col_summary,
    )


def table_has_compact_ledger(tables: list[list[list[str]]]) -> bool:
    for tbl in tables:
        for row in tbl[:12]:
            if is_compact_ledger_header([str(c or "") for c in row]):
                return True
    return False


def extract_transactions(tables: list[list[list[str]]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for tbl in tables:
        for raw in extract_compact_ledger_transactions(tbl):
            out.append({
                "日期支出收入余额": raw.get("ledger_cell", ""),
                "对方账户对方户名": raw.get("counterparty_cell", ""),
                "摘要/附言": raw.get("summary", ""),
                "_compact": "1",
                "_time_cell": raw.get("time_cell", ""),
            })
    return out


def normalize_record(raw_txn: dict[str, str]) -> dict[str, Any]:
    return normalize_compact_transaction({
        "ledger_cell": raw_txn.get("日期支出收入余额", ""),
        "counterparty_cell": raw_txn.get("对方账户对方户名", ""),
        "summary": raw_txn.get("摘要/附言", ""),
        "time_cell": raw_txn.get("_time_cell", ""),
    })


def refine_directions_from_balance_chain(records: list[dict[str, Any]]) -> None:
    """Re-infer income/expense when merged cells only expose amount + balance."""
    prev_balance: float | None = None
    for rec in records:
        norm = rec.get("normalized") or {}
        bal = norm.get("balance")
        amt = norm.get("amount")
        if bal is None or amt is None or amt <= 0:
            if bal is not None:
                prev_balance = float(bal)
            continue
        if prev_balance is not None:
            if abs(prev_balance + float(amt) - float(bal)) <= 0.01:
                norm["direction"] = "income"
            elif abs(prev_balance - float(amt) - float(bal)) <= 0.01:
                norm["direction"] = "expense"
        prev_balance = float(bal)
