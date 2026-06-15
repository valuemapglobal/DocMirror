# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Synthetic ledger table builder from OCR full text.

When Mirror reports zero tables but OCR text looks like a bank ledger, regex parsers
extract transaction lines into pseudo-table rows for downstream style parsers.

Pipeline role: fallback path inside ``bank_statement.community_plugin`` when
``StyleContext.tables`` is empty; feeds reconstructed grids into style detection.

Key exports: ``looks_like_bank_ocr_text``, ``build_tables_from_spaced_ocr_text``,
``build_tables_from_ocr_text`` (alias).

Dependencies: stdlib ``re`` only; consumed by ``context`` / ``community_plugin``.
"""

from __future__ import annotations

import re

_HEADER_MARKERS = ("交易日期", "交易金额", "账户余额", "摘要", "收入", "支出")
_BANK_MARKERS = (
    "交易明细",
    "银行流水",
    "客户账号",
    "账户余额",
    "借方发生额",
    "贷方发生额",
    "活期账户",
    "电子汇入",
    "电子汇出",
)

_INCOME_HINTS = ("收入", "汇入", "入账", "结息", "付息")
_EXPENSE_HINTS = ("支出", "汇出", "消费", "扣款", "转账")

# 20220402支出 3.00 1070.13 POS消费
_TXN_SPACED_RE = re.compile(
    r"(?<!\d)(\d{8})(收入|支出)\s*([+-]?\d+\.\d{2})\s*(\d+\.\d{2})"
)
# 20220325收入-50.0084.13 (amount glued to balance)
_TXN_GLUED_RE = re.compile(
    r"(?<!\d)(\d{8})(收入|支出)([+-]?\d+\.\d{2})(\d+\.\d{2})"
)
# ISO date variants
_TXN_ISO_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})\s*(收入|支出)?\s*([+-]?\d+\.\d{2})\s*(\d+\.\d{2})"
)


def looks_like_bank_ocr_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return False
    hits = sum(1 for m in _BANK_MARKERS if m in compact)
    return hits >= 2


def _infer_direction(line: str, amount: str) -> str:
    if amount.startswith("-"):
        return "expense"
    if amount.startswith("+"):
        return "income"
    compact = line.replace(" ", "")
    if any(h in compact for h in _EXPENSE_HINTS):
        return "expense"
    if any(h in compact for h in _INCOME_HINTS):
        return "income"
    return "income"


def _signed_amount(amount: str, direction: str) -> str:
    val = amount.replace(",", "").lstrip("+-")
    if not val:
        return amount
    if direction == "expense":
        return f"-{val}"
    return f"+{val}"


def _valid_yyyymmdd_dates(line: str) -> list[str]:
    found: list[str] = []
    for m in re.finditer(r"(?<!\d)(\d{8})", line):
        raw = m.group(1)
        try:
            y, mo, da = int(raw[:4]), int(raw[4:6]), int(raw[6:8])
            if 2010 <= y <= 2035 and 1 <= mo <= 12 and 1 <= da <= 31:
                found.append(raw)
        except ValueError:
            continue
    return found


def _parse_txn_line_fallback(line: str) -> dict[str, str] | None:
    """Generic: last valid YYYYMMDD + last two decimal amounts on the line."""
    dates = _valid_yyyymmdd_dates(line)
    amounts = re.findall(r"-?\d{1,3}(?:,\d{3})*\.\d{2}", line)
    if not dates or len(amounts) < 2:
        return None
    date_raw = dates[-1]
    amount_raw, balance_raw = amounts[-2], amounts[-1]
    date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
    direction = _infer_direction(line, amount_raw)
    return {
        "交易日期": date,
        "摘要": line[:80],
        "交易金额": _signed_amount(amount_raw, direction),
        "余额": balance_raw.replace(",", ""),
    }


def _parse_txn_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    if not line or len(line) < 12:
        return None
    for pattern in (_TXN_SPACED_RE, _TXN_GLUED_RE):
        m = pattern.search(line)
        if m:
            date_raw, direction, amount, balance = m.groups()
            date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
            summary = line[m.end() :].strip() or direction
            summary = re.sub(r"^网络(收款|付款)", "", summary).strip() or direction
            signed = f"{'+' if direction == '收入' else '-'}{amount.lstrip('+-')}"
            return {
                "交易日期": date,
                "摘要": summary[:80],
                "交易金额": signed,
                "余额": balance,
            }
    m = _TXN_ISO_RE.search(line)
    if m:
        date, direction, amount, balance = m.groups()
        signed = amount
        if direction:
            signed = f"{'+' if direction == '收入' else '-'}{amount.lstrip('+-')}"
        return {
            "交易日期": date,
            "摘要": (direction or "交易")[:80],
            "交易金额": signed,
            "余额": balance,
        }
    return _parse_txn_line_fallback(line)


def build_tables_from_spaced_ocr_text(text: str) -> list[list[list[str]]]:
    """Parse spaced OCR plain text into a single synthetic signed-amount grid table."""
    if not looks_like_bank_ocr_text(text):
        return []

    headers = ["交易日期", "摘要", "交易金额", "余额"]
    rows: list[list[str]] = [headers]
    seen: set[tuple[str, str, str]] = set()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(m in line for m in _HEADER_MARKERS) and not re.search(r"\d{8}", line):
            continue
        if line.startswith("客户账号") or line.startswith("起始日期"):
            continue

        txn = _parse_txn_line(line)
        if txn is None:
            continue
        key = (txn["交易日期"], txn["交易金额"], txn["余额"])
        if key in seen:
            continue
        seen.add(key)
        rows.append([txn["交易日期"], txn["摘要"], txn["交易金额"], txn["余额"]])

    if len(rows) < 2:
        return []
    return [rows]


def build_tables_from_ocr_text(text: str) -> list[list[list[str]]]:
    """Backward-compatible alias for ``build_tables_from_spaced_ocr_text``."""
    return build_tables_from_spaced_ocr_text(text)
