# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Single-column signed amount bank ledger style (+ income / - expense)."""

from __future__ import annotations

import re
from typing import Any

from docmirror.plugins._base.standardizer import normalize_amount
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.styles import grid_standard

PARSER_ID = "signed_amount"
STYLE_ID = "signed_amount"

_SIGNED_PREFIX_RE = re.compile(r"^[+-]")
_AMOUNT_HEADER_NEEDLES = ("交易金额", "金额", "发生额")
_SPLIT_HEADER_NEEDLES = ("收入", "支出", "借方发生额", "贷方发生额")


def _cell_value(raw_txn: dict[str, str], *needles: str) -> str:
    for key, value in raw_txn.items():
        for needle in needles:
            if key == needle or needle in key:
                return str(value or "").strip()
    return ""


def parse_signed_amount(text: str) -> tuple[float | None, str]:
    """Return (abs_amount, direction) from a signed amount string."""
    raw = (text or "").strip().replace(",", "").replace("¥", "").replace("￥", "")
    if not raw:
        return None, "other"
    if raw.startswith("-"):
        amount = normalize_amount(raw)
        return (abs(float(amount)), "expense") if amount is not None else (None, "other")
    if raw.startswith("+"):
        amount = normalize_amount(raw.lstrip("+"))
        return (float(amount), "income") if amount is not None else (None, "other")
    amount = normalize_amount(raw)
    if amount is None:
        return None, "other"
    return abs(float(amount)), "income"


def table_has_signed_amount_cells(tables: list[list[list[str]]]) -> bool:
    """True when amount column cells use explicit +/- prefixes (not split debit/credit)."""
    for tbl in tables:
        if not tbl:
            continue
        header_idx = -1
        amount_col = -1
        for i, row in enumerate(tbl[:10]):
            for j, cell in enumerate(row):
                text = str(cell or "").strip()
                if any(n in text for n in _AMOUNT_HEADER_NEEDLES):
                    if any(s in text for s in _SPLIT_HEADER_NEEDLES):
                        return False
                    header_idx = i
                    amount_col = j
                    break
            if amount_col >= 0:
                break
        if amount_col < 0:
            continue

        signed_rows = 0
        checked_rows = 0
        for row in tbl[header_idx + 1 : header_idx + 12]:
            if amount_col >= len(row):
                continue
            cell = str(row[amount_col] or "").strip()
            if not cell or not re.search(r"\d", cell):
                continue
            checked_rows += 1
            if _SIGNED_PREFIX_RE.match(cell):
                signed_rows += 1
        if checked_rows >= 2 and signed_rows == checked_rows:
            return True
    return False


def extract_transactions(ctx: StyleContext, plugin: Any) -> list[dict[str, str]]:
    return grid_standard.extract_transactions(ctx, plugin)


def normalize_record(raw_txn: dict[str, str], plugin: Any) -> dict[str, Any]:
    amount_text = _cell_value(raw_txn, *_AMOUNT_HEADER_NEEDLES)
    parsed_amount, direction = parse_signed_amount(amount_text)
    normalized = plugin._normalize(raw_txn)
    if parsed_amount is not None:
        normalized["amount"] = parsed_amount
        normalized["amount_cny"] = parsed_amount
        normalized["direction"] = direction
    return normalized
