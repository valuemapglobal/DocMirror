# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Recover native-PDF wide debit/credit bank ledger tables.

This is a guarded candidate source for bank statements where the primary
Mirror/LTRO table candidate is sparse or malformed, but the source PDF still
contains a reliable native table. It is intentionally schema-driven rather than
bank-name-driven: a candidate must expose row number/date/debit/credit/balance
semantics before it is returned.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from docmirror.evidence.repair import RepairRequest
from docmirror.plugins.bank_statement.header_resolve import normalize_header_cell

logger = logging.getLogger(__name__)

_DEBIT_CREDIT_REQUIRED = ("借方发生额", "贷方发生额", "余额")
_INCOME_EXPENSE_REQUIRED = ("支出金额", "收入金额", "余额")
_ROW_ANCHOR_HEADERS = ("序号", "交易日期", "会计日期", "日期")
_FOOTER_MARKERS = (
    "当前账单借方发生数",
    "当前账单贷方发生数",
    "本月累计借方发生数",
    "本月累计贷方发生数",
    "本月累计借方发生额",
    "本月累计贷方发生额",
    "出单截至日期",
    "以下此页无正文",
    "合计",
    "小计",
    "总计",
)
_COUNT_PATTERNS = (re.compile(r"合计笔数[:：]\s*(?P<count>\d+)"),)
_SPLIT_COUNT_PATTERNS = (
    re.compile(r"借方笔数[:：]\s*(?P<debit>\d+).*?贷方笔数[:：]\s*(?P<credit>\d+)", re.S),
    re.compile(r"当前账单借方发生数[:：]\s*(?P<debit>\d+).*?当前账单贷方发生数[:：]\s*(?P<credit>\d+)", re.S),
    re.compile(r"本月累计借方发生数[:：]\s*(?P<debit>\d+).*?本月累计贷方发生数[:：]\s*(?P<credit>\d+)", re.S),
    re.compile(r"支出总笔数[:：]\s*(?P<debit>\d+).*?收入总笔数[:：]\s*(?P<credit>\d+)", re.S),
    re.compile(r"收入总笔数[:：]\s*(?P<credit>\d+).*?支出总笔数[:：]\s*(?P<debit>\d+)", re.S),
)
_DEBIT_TOTAL_PATTERNS = (
    re.compile(r"借方发生总额[:：]\s*(?P<value>[\d,]+\.\d{2})"),
    re.compile(r"本月累计借方发生额[:：]\s*(?P<value>[\d,]+\.\d{2})"),
    re.compile(r"支出总金额[:：]\s*(?P<value>[\d,]+\.\d{2})"),
)
_CREDIT_TOTAL_PATTERNS = (
    re.compile(r"贷方发生总额[:：]\s*(?P<value>[\d,]+\.\d{2})"),
    re.compile(r"本月累计贷方发生额[:：]\s*(?P<value>[\d,]+\.\d{2})"),
    re.compile(r"收入总金额[:：]\s*(?P<value>[\d,]+\.\d{2})"),
)


def recover_wide_bank_tables(parse_result: Any, full_text: str = "") -> list[list[list[str]]]:
    """Return high-confidence wide debit/credit table candidates from source PDF."""
    pdf_path = _source_pdf_path(parse_result)
    if not pdf_path:
        return []
    try:
        import pdfplumber
    except ImportError:
        logger.debug("[BankWideTableRecovery] pdfplumber unavailable")
        return []

    page_tables: list[list[list[str]]] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    normalized = _normalize_table(table)
                    if normalized:
                        page_tables.append(normalized)
    except Exception as exc:
        logger.debug("[BankWideTableRecovery] native PDF table recovery failed: %s", exc)
        return []

    candidates = _recover_cross_page_wide_tables(page_tables)
    for table in page_tables:
        wide = _select_wide_bank_table(table)
        if wide:
            candidates.append(wide)
    candidates = _dedupe_tables(candidates)

    if candidates:
        logger.info("[BankWideTableRecovery] recovered %d native wide table(s)", len(candidates))
    return candidates


def count_expected_rows_from_bank_footer(text: str) -> int:
    """Read expected transaction count from bank-statement footer/header totals."""
    source = text or ""
    for pat in _COUNT_PATTERNS:
        if m := pat.search(source):
            return _safe_count(m.group("count"))
    for pat in _SPLIT_COUNT_PATTERNS:
        if m := pat.search(source):
            return _safe_count(int(m.group("debit")) + int(m.group("credit")))
    return 0


def audit_bank_statement_invariants(records: list[dict[str, Any]], text: str) -> list[str]:
    """Hard semantic gates for bank ledger rows against source footer totals."""
    failures: list[str] = []
    expected = count_expected_rows_from_bank_footer(text)
    if expected > 0 and len(records) != expected:
        failures.append(f"bank_invariant_failed:row_count:{len(records)}/{expected}")

    normalized = [rec.get("normalized") or {} for rec in records]
    debit_rows = [row for row in normalized if row.get("direction") == "expense"]
    credit_rows = [row for row in normalized if row.get("direction") == "income"]
    debit_total = _footer_amount(text, _DEBIT_TOTAL_PATTERNS)
    credit_total = _footer_amount(text, _CREDIT_TOTAL_PATTERNS)
    if debit_total is not None:
        actual = round(sum(_float(row.get("amount")) for row in debit_rows), 2)
        if abs(actual - debit_total) > 0.01:
            failures.append(f"bank_invariant_failed:debit_total:{actual:.2f}/{debit_total:.2f}")
    if credit_total is not None:
        actual = round(sum(_float(row.get("amount")) for row in credit_rows), 2)
        if abs(actual - credit_total) > 0.01:
            failures.append(f"bank_invariant_failed:credit_total:{actual:.2f}/{credit_total:.2f}")

    breaks, checked = _best_balance_chain_breaks(normalized)
    if checked > 0 and breaks > 0:
        failures.append(f"bank_invariant_failed:balance_chain:{breaks}/{checked}")
        failures.extend(_balance_chain_break_review_items(normalized, limit=3))
    return failures


def _best_balance_chain_breaks(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Return min breaks across chronological and reverse-chronological order."""
    forward = _balance_chain_breaks(rows)
    backward = _balance_chain_breaks(list(reversed(rows)))
    if backward[1] > forward[1]:
        return backward
    if forward[1] > backward[1]:
        return forward
    return min(forward, backward, key=lambda item: item[0])


def _balance_chain_breaks(rows: list[dict[str, Any]]) -> tuple[int, int]:
    checked = 0
    breaks = 0
    prev_balance: float | None = None
    for row in rows:
        direction = row.get("direction")
        if direction not in ("income", "expense"):
            continue
        balance = row.get("balance")
        amount = row.get("amount")
        if balance in (None, "") or amount in (None, ""):
            continue
        balance_f = _float(balance)
        amount_f = _float(amount)
        if prev_balance is not None:
            checked += 1
            expected_balance = prev_balance + amount_f if direction == "income" else prev_balance - amount_f
            if abs(round(expected_balance - balance_f, 2)) > 0.01:
                breaks += 1
        prev_balance = balance_f
    return breaks, checked


def _balance_chain_break_review_items(rows: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    items: list[str] = []
    prev_balance: float | None = None
    prev_row: dict[str, Any] | None = None
    for row_index, row in enumerate(rows, start=1):
        direction = row.get("direction")
        if direction not in ("income", "expense"):
            continue
        balance = row.get("balance")
        amount = row.get("amount")
        if balance in (None, "") or amount in (None, ""):
            continue
        balance_f = _float(balance)
        amount_f = _float(amount)
        if prev_balance is not None:
            expected_balance = prev_balance + amount_f if direction == "income" else prev_balance - amount_f
            delta = round(balance_f - expected_balance, 2)
            if abs(delta) > 0.01:
                items.append(
                    "bank_review:balance_chain_gap:"
                    f"row={row_index}:"
                    f"date={row.get('date') or row.get('transaction_date') or ''}:"
                    f"direction={direction}:"
                    f"amount={amount_f:.2f}:"
                    f"prev_balance={prev_balance:.2f}:"
                    f"expected_balance={expected_balance:.2f}:"
                    f"actual_balance={balance_f:.2f}:"
                    f"delta={delta:.2f}"
                )
                missing_candidate = _single_missing_row_candidate(
                    previous_row=prev_row,
                    current_row=row,
                    current_row_index=row_index,
                    previous_balance=prev_balance,
                    current_balance=balance_f,
                    current_amount=amount_f,
                )
                if missing_candidate:
                    items.append(missing_candidate)
                    repair_request = _single_missing_row_repair_request(
                        previous_row=prev_row,
                        current_row=row,
                        current_row_index=row_index,
                    )
                    items.append(_repair_request_review_item(repair_request))
                if len(items) >= limit:
                    break
        prev_balance = balance_f
        prev_row = row
    return items


def _single_missing_row_candidate(
    *,
    previous_row: dict[str, Any] | None,
    current_row: dict[str, Any],
    current_row_index: int,
    previous_balance: float,
    current_balance: float,
    current_amount: float,
) -> str:
    """Return a review-only candidate when one missing row can bridge a gap."""
    if previous_row is None:
        return ""
    current_direction = current_row.get("direction")
    if current_direction == "income":
        bridge_balance = current_balance - current_amount
    elif current_direction == "expense":
        bridge_balance = current_balance + current_amount
    else:
        return ""

    missing_delta = round(bridge_balance - previous_balance, 2)
    if abs(missing_delta) <= 0.01:
        return ""
    missing_direction = "income" if missing_delta > 0 else "expense"
    missing_amount = abs(missing_delta)
    if missing_amount <= 0 or missing_amount > 1_000_000_000:
        return ""

    previous_date = previous_row.get("date") or previous_row.get("transaction_date") or ""
    current_date = current_row.get("date") or current_row.get("transaction_date") or ""
    return (
        "bank_review:missing_row_candidate:"
        f"before_row={current_row_index}:"
        f"date_range={previous_date}..{current_date}:"
        f"direction={missing_direction}:"
        f"amount={missing_amount:.2f}:"
        f"balance={bridge_balance:.2f}:"
        "evidence=balance_chain_only:"
        "action=manual_review:not_auto_adopted"
    )


def _single_missing_row_repair_request(
    *,
    previous_row: dict[str, Any] | None,
    current_row: dict[str, Any],
    current_row_index: int,
) -> RepairRequest:
    previous_date = ""
    if previous_row is not None:
        previous_date = previous_row.get("date") or previous_row.get("transaction_date") or ""
    current_date = current_row.get("date") or current_row.get("transaction_date") or ""
    return RepairRequest(
        request_id=f"bank-ledger-balance-gap-before-row-{current_row_index}",
        domain="bank_statement",
        kind="missing_ledger_row_local_ocr",
        expected_schema=("date", "direction", "amount", "balance"),
        constraints=(
            "bank.balance_chain_consistency",
            "bank.date_order",
            "bank.amount_format",
            "bank.no_duplicate_transaction",
        ),
        context={
            "before_row": current_row_index,
            "date_range": f"{previous_date}..{current_date}",
            "previous_date": previous_date,
            "current_date": current_date,
        },
        reason="balance_chain_gap_single_missing_row_candidate",
    )


def _repair_request_review_item(request: RepairRequest) -> str:
    data = request.to_dict()
    return (
        "bank_review:repair_request:"
        f"id={data['request_id']}:"
        f"kind={data['kind']}:"
        f"can_render={str(data['can_render']).lower()}:"
        "action=manual_review:"
        "reason=missing_page_bbox"
    )


def is_footer_or_total_row(row: list[str] | tuple[str, ...] | None) -> bool:
    """Return true when a table row is a footer/total rather than a transaction."""
    if not row:
        return False
    joined = " ".join(str(cell or "").strip() for cell in row if str(cell or "").strip())
    return bool(joined and any(marker in joined for marker in _FOOTER_MARKERS))


def is_wide_bank_header(row: list[str] | tuple[str, ...] | None) -> bool:
    if not row:
        return False
    headers = [normalize_header_cell(str(cell or "")) for cell in row]
    joined = "".join(headers)
    has_required = all(normalize_header_cell(item) in joined for item in _DEBIT_CREDIT_REQUIRED) or all(
        normalize_header_cell(item) in joined for item in _INCOME_EXPENSE_REQUIRED
    )
    has_anchor = any(normalize_header_cell(item) in joined for item in _ROW_ANCHOR_HEADERS)
    return has_required and has_anchor


def _select_wide_bank_table(table: list[list[str]]) -> list[list[str]]:
    if not table:
        return []
    for idx, row in enumerate(table[:8]):
        if not is_wide_bank_header(row):
            continue
        header = [str(cell or "").strip() for cell in row]
        rows = [header]
        for data_row in table[idx + 1 :]:
            if not data_row or not any(str(cell or "").strip() for cell in data_row):
                continue
            if is_footer_or_total_row(data_row):
                continue
            if _looks_like_transaction_row(data_row):
                rows.append([str(cell or "").strip() for cell in data_row])
        if len(rows) > 1:
            return rows
    return []


def _looks_like_transaction_row(row: list[str]) -> bool:
    first = str(row[0] or "").strip()
    joined = " ".join(str(cell or "").strip() for cell in row)
    if not re.fullmatch(r"\d{1,6}", first):
        return False
    if not re.search(r"\b\d{8}\b|\b\d{4}-\d{2}-\d{2}\b", joined):
        return False
    if not re.search(r"(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}", joined):
        return False
    return True


def _recover_cross_page_wide_tables(page_tables: list[list[list[str]]]) -> list[list[list[str]]]:
    """Compose first-header + continuation native PDF tables into one logical ledger."""
    recovered: list[list[list[str]]] = []
    current_header: list[str] | None = None
    current_rows: list[list[str]] = []
    previous_seq = 0

    def flush() -> None:
        nonlocal current_header, current_rows, previous_seq
        if current_header and current_rows:
            recovered.append([current_header, *current_rows])
        current_header = None
        current_rows = []
        previous_seq = 0

    for table in page_tables:
        if not table:
            continue
        table = [[_clean_native_cell(cell) for cell in row] for row in table]
        header_idx = next((idx for idx, row in enumerate(table[:8]) if is_wide_bank_header(row)), -1)
        if header_idx >= 0:
            if current_rows:
                flush()
            current_header = [str(cell or "").strip() for cell in table[header_idx]]
            data_rows = table[header_idx + 1 :]
        elif current_header and _is_continuation_table(table, current_header, previous_seq):
            data_rows = table
        else:
            continue

        for row in data_rows:
            if not row or is_footer_or_total_row(row) or not _looks_like_transaction_row(row):
                continue
            normalized = _fit_row_width([str(cell or "").strip() for cell in row], len(current_header))
            seq = _row_sequence(normalized)
            if previous_seq and seq and seq != previous_seq + 1:
                flush()
                current_header = [str(cell or "").strip() for cell in table[header_idx]] if header_idx >= 0 else None
                if current_header is None:
                    continue
            current_rows.append(normalized)
            if seq:
                previous_seq = seq
    flush()
    return recovered


def _is_continuation_table(table: list[list[str]], header: list[str], previous_seq: int) -> bool:
    data_rows = [row for row in table if row and not is_footer_or_total_row(row) and _looks_like_transaction_row(row)]
    if not data_rows:
        return False
    width_ok = abs(max((len(row) for row in data_rows), default=0) - len(header)) <= 2
    first_seq = _row_sequence(data_rows[0])
    sequence_ok = not previous_seq or not first_seq or first_seq == previous_seq + 1
    return width_ok and sequence_ok


def _row_sequence(row: list[str]) -> int:
    first = str(row[0] or "").strip()
    return int(first) if re.fullmatch(r"\d{1,6}", first) else 0


def _fit_row_width(row: list[str], width: int) -> list[str]:
    if len(row) > width:
        return row[:width]
    if len(row) < width:
        return [*row, *([""] * (width - len(row)))]
    return row


def _dedupe_tables(tables: list[list[list[str]]]) -> list[list[list[str]]]:
    out: list[list[list[str]]] = []
    seen: set[tuple[int, str, str]] = set()
    for table in sorted(tables, key=lambda tbl: len(tbl), reverse=True):
        if not table:
            continue
        key = (
            len(table),
            "|".join(table[0]),
            "|".join(table[-1] if len(table) > 1 else []),
        )
        if key in seen:
            continue
        if any(_table_contains(existing, table) for existing in out):
            continue
        seen.add(key)
        out.append(table)
    return out


def _table_contains(larger: list[list[str]], smaller: list[list[str]]) -> bool:
    if len(larger) < len(smaller) or not larger or not smaller:
        return False
    if larger[0] != smaller[0]:
        return False
    large_rows = {"|".join(row) for row in larger[1:]}
    return all("|".join(row) in large_rows for row in smaller[1:])


def _normalize_table(table: list[list[Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    width = max((len(row or []) for row in table or []), default=0)
    for row in table or []:
        values = [_clean_native_cell(cell) for cell in row or []]
        if len(values) < width:
            values.extend([""] * (width - len(values)))
        if any(values):
            rows.append(values)
    return rows


def _clean_native_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(\d{4}-\d{2})-\s+(\d{1,2})", r"\1-\2", text)
    text = re.sub(r"(\d{1,2}:\d{2}:\d)\s+(\d)\b", r"\1\2", text)
    return text.strip()


def _footer_amount(text: str, patterns: tuple[re.Pattern[str], ...]) -> float | None:
    for pat in patterns:
        if m := pat.search(text or ""):
            return _float(m.group("value"))
    return None


def _safe_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return count if 0 < count <= 10000 else 0


def _float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _source_pdf_path(parse_result: Any) -> Path | None:
    candidates = [
        getattr(parse_result, "file_path", None),
        getattr(parse_result, "source_path", None),
    ]
    provenance = getattr(parse_result, "provenance", None)
    if provenance is not None:
        props = getattr(provenance, "document_properties", None)
        if isinstance(props, dict):
            candidates.extend([props.get("file_path"), props.get("source_path"), props.get("path")])

    parser_info = getattr(parse_result, "parser_info", None)
    if parser_info is not None:
        opts = getattr(parser_info, "options", None)
        if isinstance(opts, dict):
            candidates.extend([opts.get("file_path"), opts.get("source_path")])

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate)).expanduser()
        if path.is_file() and path.suffix.lower() == ".pdf":
            return path
    return None
