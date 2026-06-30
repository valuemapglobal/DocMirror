# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bank statement semantic solver.

This first landing point targets native-text ledgers whose text stream preserves
row number + date + time but table geometry is weak. It reconstructs split
debit/credit rows using ledger invariants instead of treating every amount as a
single signed value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from docmirror.domains.base import DomainSolution

_HEADER_TOTAL_RE = re.compile(
    r"借方笔数[:：]\s*(?P<debit_count>\d+)\s*"
    r"借方发生总额[:：]\s*(?P<debit_total>[\d,]+\.\d{2})\s*"
    r"贷方笔数[:：]\s*(?P<credit_count>\d+)\s*"
    r"贷方发生总额[:：]\s*(?P<credit_total>[\d,]+\.\d{2})\s*"
    r"合计笔数[:：]\s*(?P<total_count>\d+)"
)
_DATE_TIME_ROW_RE = re.compile(r"^(?P<row_no>\d{1,5})\s+(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{1,2}:\d{2}:\d{2})\b")
_ROW_NO_RE = re.compile(r"^\d{1,5}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
_AMOUNT_RE = re.compile(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d)")
_ACCOUNT_HOLDER_RE = re.compile(r"账户名称[:：]\s*(?P<value>[^\n\r]+)")
_ACCOUNT_NUMBER_RE = re.compile(r"账号[:：]\s*(?P<value>[0-9*＊\s]{6,40})")
_PERIOD_RE = re.compile(r"起始日期[:：]\s*(?P<start>\d{4}-\d{2}-\d{2})\s*终止日期[:：]\s*(?P<end>\d{4}-\d{2}-\d{2})")
_BANK_RE = re.compile(r"(?P<bank>[\u4e00-\u9fa5]{2,20}银行)")
_NOISE_RE = re.compile(r"CPKYG[0-9A-Z]+|打印时间|回单专用章")
_VERTICAL_NOISE_TOKENS = {"第", "页"}


@dataclass(frozen=True)
class HeaderTotals:
    debit_count: int
    debit_total: float
    credit_count: int
    credit_total: float
    total_count: int


@dataclass
class RawLedgerRow:
    row_no: int
    date: str
    time: str
    text: str
    amount: float
    balance: float
    direction: str = ""
    summary: str = ""
    counter_account: str = ""
    counter_party: str = ""


class BankStatementSemanticSolver:
    """Solve bank ledger rows against debit/credit and balance invariants."""

    domain = "bank_statement"

    def solve(self, *, full_text: str, parse_result: Any = None) -> DomainSolution:
        header = extract_header_totals(full_text)
        if header is None:
            return DomainSolution(
                domain=self.domain,
                status="failed",
                diagnostics=({"reason": "missing_debit_credit_header_totals"},),
            )
        rows = extract_raw_rows(full_text)
        if not rows:
            return DomainSolution(
                domain=self.domain,
                status="failed",
                diagnostics=({"reason": "no_raw_ledger_rows"},),
            )
        solved = solve_directions(rows, header)
        invariants = evaluate_invariants(solved, header)
        hard_fail = any(item["status"] == "fail" and item.get("required") for item in invariants)
        status = "failed" if hard_fail else "success"
        confidence = 1.0 if status == "success" else 0.0
        canonical = {
            "identity": extract_identity(full_text),
            "header_totals": header.__dict__,
            "records": [canonical_record(row) for row in solved],
            "split_table": build_split_table(solved),
        }
        return DomainSolution(
            domain=self.domain,
            canonical_model=canonical,
            invariant_results=tuple(invariants),
            confidence=confidence,
            status=status,
            diagnostics=({"row_count": len(solved)},),
        )


def extract_header_totals(text: str) -> HeaderTotals | None:
    m = _HEADER_TOTAL_RE.search(text or "")
    if not m:
        return None
    return HeaderTotals(
        debit_count=int(m.group("debit_count")),
        debit_total=_money(m.group("debit_total")),
        credit_count=int(m.group("credit_count")),
        credit_total=_money(m.group("credit_total")),
        total_count=int(m.group("total_count")),
    )


def extract_identity(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if m := _ACCOUNT_HOLDER_RE.search(text or ""):
        out["account_holder"] = m.group("value").strip()
    if m := _ACCOUNT_NUMBER_RE.search(text or ""):
        out["account_number"] = re.sub(r"\s+", " ", m.group("value")).strip()
    if m := _PERIOD_RE.search(text or ""):
        out["query_period"] = f"{m.group('start')} ~ {m.group('end')}"
    if m := _BANK_RE.search(text or ""):
        out["bank_name"] = m.group("bank")
    if "人民币" in (text or ""):
        out["currency"] = "CNY"
    return out


def extract_raw_rows(text: str) -> list[RawLedgerRow]:
    vertical = _extract_vertical_rows(text)
    if vertical:
        return vertical

    groups: list[list[str]] = []
    current: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _DATE_TIME_ROW_RE.match(line):
            if current:
                groups.append(current)
            current = [line]
            continue
        if current:
            current.append(line)
    if current:
        groups.append(current)

    rows: list[RawLedgerRow] = []
    for group in groups:
        first = group[0]
        m = _DATE_TIME_ROW_RE.match(first)
        if not m:
            continue
        row_text = " ".join(group)
        amounts = [_money(value) for value in _AMOUNT_RE.findall(row_text)]
        if len(amounts) < 2:
            continue
        amount = amounts[-2]
        balance = amounts[-1]
        row = RawLedgerRow(
            row_no=int(m.group("row_no")),
            date=m.group("date"),
            time=m.group("time"),
            text=row_text,
            amount=amount,
            balance=balance,
        )
        row.summary = _extract_summary(row_text, amount, balance)
        row.counter_account, row.counter_party = _extract_counterparty(row_text)
        rows.append(row)
    return rows


def _extract_vertical_rows(text: str) -> list[RawLedgerRow]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    groups: list[list[str]] = []
    idx = 0
    while idx + 2 < len(lines):
        if not (_ROW_NO_RE.match(lines[idx]) and _DATE_RE.match(lines[idx + 1]) and _TIME_RE.match(lines[idx + 2])):
            idx += 1
            continue
        start = idx
        idx += 3
        while idx + 2 < len(lines):
            if _ROW_NO_RE.match(lines[idx]) and _DATE_RE.match(lines[idx + 1]) and _TIME_RE.match(lines[idx + 2]):
                break
            idx += 1
        groups.append(lines[start:idx])

    rows: list[RawLedgerRow] = []
    for group in groups:
        if len(group) < 6:
            continue
        amounts = [_money(value) for value in group if _AMOUNT_RE.fullmatch(value)]
        if len(amounts) < 2:
            continue
        row = RawLedgerRow(
            row_no=int(group[0]),
            date=group[1],
            time=group[2],
            text=" ".join(group),
            amount=amounts[0],
            balance=amounts[1],
        )
        amount_idx = next((i for i, value in enumerate(group) if _AMOUNT_RE.fullmatch(value)), -1)
        row.summary = _extract_vertical_summary(group, amount_idx)
        row.counter_account, row.counter_party = _extract_vertical_counterparty(group, amount_idx)
        rows.append(row)
    return rows


def solve_directions(rows: list[RawLedgerRow], header: HeaderTotals) -> list[RawLedgerRow]:
    if not rows:
        return rows
    # Infer all rows after the first from adjacent balances.
    for prev, row in zip(rows, rows[1:]):
        delta = round(row.balance - prev.balance, 2)
        if abs(delta - row.amount) <= 0.01:
            row.direction = "income"
        elif abs(delta + row.amount) <= 0.01:
            row.direction = "expense"

    # Pick the first-row direction by satisfying header counts/totals.
    for first_dir in ("expense", "income"):
        rows[0].direction = first_dir
        if _header_match(rows, header):
            return rows

    # Fallback: choose non-negative opening balance when possible.
    if rows[0].balance - rows[0].amount >= -0.01:
        rows[0].direction = "income"
    else:
        rows[0].direction = "expense"
    return rows


def evaluate_invariants(rows: list[RawLedgerRow], header: HeaderTotals) -> list[dict[str, Any]]:
    debit_rows = [row for row in rows if row.direction == "expense"]
    credit_rows = [row for row in rows if row.direction == "income"]
    debit_total = round(sum(row.amount for row in debit_rows), 2)
    credit_total = round(sum(row.amount for row in credit_rows), 2)
    chain_breaks = _balance_chain_breaks(rows)
    return [
        _gate(
            "bank.row_count_reconciliation",
            len(rows) == header.total_count,
            {"expected": header.total_count, "actual": len(rows)},
        ),
        _gate(
            "bank.debit_credit_count_reconciliation",
            len(debit_rows) == header.debit_count and len(credit_rows) == header.credit_count,
            {
                "expected_debit": header.debit_count,
                "actual_debit": len(debit_rows),
                "expected_credit": header.credit_count,
                "actual_credit": len(credit_rows),
            },
        ),
        _gate(
            "bank.debit_credit_total_reconciliation",
            abs(debit_total - header.debit_total) <= 0.01 and abs(credit_total - header.credit_total) <= 0.01,
            {
                "expected_debit_total": header.debit_total,
                "actual_debit_total": debit_total,
                "expected_credit_total": header.credit_total,
                "actual_credit_total": credit_total,
            },
        ),
        _gate(
            "bank.balance_chain_consistency",
            chain_breaks == 0,
            {"chain_breaks": chain_breaks, "checked": max(len(rows) - 1, 0)},
        ),
    ]


def build_split_table(rows: list[RawLedgerRow]) -> list[list[str]]:
    table = [["序号", "交易日期", "交易时间", "摘要", "借方发生额", "贷方发生额", "余额", "对方账户", "对方户名"]]
    for row in rows:
        debit = _format_money(row.amount) if row.direction == "expense" else ""
        credit = _format_money(row.amount) if row.direction == "income" else ""
        table.append(
            [
                str(row.row_no),
                row.date,
                f"{row.date} {row.time}",
                row.summary,
                debit,
                credit,
                _format_money(row.balance),
                row.counter_account,
                row.counter_party,
            ]
        )
    return table


def canonical_record(row: RawLedgerRow) -> dict[str, Any]:
    signed = row.amount if row.direction == "income" else -row.amount
    return {
        "row_no": row.row_no,
        "date": row.date,
        "time": row.time,
        "timestamp": f"{row.date}T{row.time}",
        "summary": row.summary,
        "debit_amount": row.amount if row.direction == "expense" else None,
        "credit_amount": row.amount if row.direction == "income" else None,
        "amount": signed,
        "direction": row.direction,
        "balance": row.balance,
        "counter_account": row.counter_account,
        "counter_party": row.counter_party,
    }


def _header_match(rows: list[RawLedgerRow], header: HeaderTotals) -> bool:
    debit = [row for row in rows if row.direction == "expense"]
    credit = [row for row in rows if row.direction == "income"]
    return (
        len(debit) == header.debit_count
        and len(credit) == header.credit_count
        and abs(round(sum(row.amount for row in debit), 2) - header.debit_total) <= 0.01
        and abs(round(sum(row.amount for row in credit), 2) - header.credit_total) <= 0.01
    )


def _balance_chain_breaks(rows: list[RawLedgerRow]) -> int:
    breaks = 0
    for prev, row in zip(rows, rows[1:]):
        expected = prev.balance + row.amount if row.direction == "income" else prev.balance - row.amount
        if abs(round(expected - row.balance, 2)) > 0.01:
            breaks += 1
    return breaks


def _gate(gate_id: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": gate_id,
        "status": "pass" if passed else "fail",
        "required": True,
        "details": details,
    }


def _extract_summary(text: str, amount: float, balance: float) -> str:
    stripped = _DATE_TIME_ROW_RE.sub("", text, count=1).strip()
    amount_s = _format_money(amount)
    before_amount = stripped.split(amount_s, 1)[0] if amount_s in stripped else stripped
    tokens = [tok for tok in before_amount.split() if not tok.isdigit() and not _NOISE_RE.search(tok)]
    text_tokens = [tok for tok in tokens if not re.fullmatch(r"[0-9]{6,}", tok)]
    if not text_tokens:
        return ""
    # Prefer the last short business phrase before the amount.
    for token in reversed(text_tokens):
        if any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in token):
            return token[:80]
    return text_tokens[-1][:80]


def _extract_vertical_summary(group: list[str], amount_idx: int) -> str:
    if amount_idx <= 3:
        return ""
    summary_parts = [
        item for item in group[3:amount_idx] if not _NOISE_RE.search(item) and item not in {"摘要", "凭证种类"}
    ]
    return " ".join(summary_parts).strip()[:80]


def _extract_vertical_counterparty(group: list[str], amount_idx: int) -> tuple[str, str]:
    tail = [
        item
        for item in group[amount_idx + 2 :]
        if item and item != "null" and item not in _VERTICAL_NOISE_TOKENS and not _NOISE_RE.search(item)
    ]
    account_parts: list[str] = []
    party_parts: list[str] = []
    for item in tail:
        if re.fullmatch(r"\d{3,30}", item):
            account_parts.append(item)
        elif any("\u4e00" <= ch <= "\u9fff" for ch in item):
            party_parts.append(item)
    account = "".join(account_parts[:2])
    party = "".join(party_parts).strip()[:80]
    return account, party


def _extract_counterparty(text: str) -> tuple[str, str]:
    cleaned = _NOISE_RE.sub("", text)
    account = ""
    for match in re.finditer(r"\b\d{10,30}\b", cleaned):
        value = match.group(0)
        if value.startswith(("2022", "2023")):
            continue
        account = value
        break
    party = ""
    chinese_runs = re.findall(r"[\u4e00-\u9fa5（）()]{4,40}", cleaned)
    skip = ("江苏银行对公账户对账单", "企业电子渠道跨", "待报解预算收入")
    for run in reversed(chinese_runs):
        value = run.strip()
        if any(item in value for item in skip):
            continue
        if value in {"借方发生额", "贷方发生额", "合计笔数"}:
            continue
        party = value
        break
    return account, party


def _money(value: str) -> float:
    return float(str(value or "0").replace(",", ""))


def _format_money(value: float) -> str:
    return f"{float(value):.2f}"


__all__ = [
    "BankStatementSemanticSolver",
    "HeaderTotals",
    "RawLedgerRow",
    "build_split_table",
    "evaluate_invariants",
    "extract_header_totals",
    "extract_raw_rows",
    "solve_directions",
]
