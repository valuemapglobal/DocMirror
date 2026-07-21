# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Recover OCR implicit ledger tables from canonical facts and evidence."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any

from docmirror.plugins.bank_statement.header_resolve import normalize_header_cell

logger = logging.getLogger(__name__)

_STANDARD_HEADER = ["交易日期", "收/支", "交易金额", "余额", "摘要", "对方账号", "对方户名", "机构", "柜员", "备注"]
_DATE_RE = re.compile(r"(20\d{6}|20\d{2}[-/]\d{1,2}[-/]\d{1,2})")
_DIRECTION_RE = re.compile(r"(收入|收人|支出|支山|支鼎|攴出)")
_AMOUNT_TOKEN_RE = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\s*\d{2})|\d+\.\s*\d{2}")
_ACCOUNT_RE = re.compile(r"\b\d{7,24}\b")
_NOISE_RE = re.compile(r"第\s*\d+\s*页|业务用章|交易机构|产品说明|账号序号|起始日期|终止日期")
_CACHE_KEY = "_bank_ocr_implicit_recovery"


def recover_ocr_implicit_ledger_tables(parse_result: Any, full_text: str = "") -> list[list[list[str]]]:
    """Build bank ledger tables from canonical tables and positioned text."""
    cached = _cached_tables(parse_result)
    if cached is not None:
        logger.debug("[BankOCRImplicitRecovery] cache hit rows=%d", _recovered_row_count(cached))
        return cached

    canonical = _canonical_payload(parse_result)
    tables = _extract_canonical_tables(canonical)
    recovered: list[list[list[str]]] = []
    recovered.extend(_extract_paragraph_ledger_tables(canonical))
    for table in tables:
        normalized = _normalize_implicit_table(table)
        if len(normalized) > 1:
            recovered.append(normalized)
    if recovered:
        _store_cache(parse_result, recovered, source="canonical_facts")
        logger.info("[BankOCRImplicitRecovery] recovered %d OCR implicit table(s)", len(recovered))
        return recovered
    recovered = _recover_from_text(full_text)
    _store_cache(parse_result, recovered, source="full_text" if recovered else "none")
    return recovered


def recovered_ocr_implicit_row_count(parse_result: Any) -> int:
    """Return cached OCR implicit recovery row count without triggering Mirror rebuild."""
    cached = _cached_tables(parse_result)
    return _recovered_row_count(cached or [])


def _domain_specific(parse_result: Any) -> dict[str, Any] | None:
    entities = getattr(parse_result, "entities", None)
    ds = getattr(entities, "domain_specific", None) if entities is not None else None
    return ds if isinstance(ds, dict) else None


def _cached_tables(parse_result: Any) -> list[list[list[str]]] | None:
    ds = _domain_specific(parse_result)
    if ds is None:
        return None
    cache = ds.get(_CACHE_KEY)
    if not isinstance(cache, dict) or cache.get("status") != "ready":
        return None
    tables = cache.get("tables")
    if not _is_table_list(tables):
        return None
    return deepcopy(tables)


def _store_cache(parse_result: Any, tables: list[list[list[str]]], *, source: str) -> None:
    ds = _domain_specific(parse_result)
    if ds is None:
        return
    ds[_CACHE_KEY] = {
        "status": "ready",
        "source": source,
        "table_count": len(tables),
        "row_count": _recovered_row_count(tables),
        "tables": deepcopy(tables),
    }


def _is_table_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(table, list) and all(isinstance(row, list) for row in table) for table in value
    )


def _recovered_row_count(tables: list[list[list[str]]]) -> int:
    return sum(max(len(table) - 1, 0) for table in tables)


def _canonical_payload(parse_result: Any) -> dict[str, Any]:
    if parse_result is None:
        return {}
    from docmirror.plugins._runtime.evidence_access import evidence_payload

    blocks: list[dict[str, Any]] = []
    for page in getattr(parse_result, "pages", []) or []:
        page_id = f"page:{int(getattr(page, 'page_number', 1) or 1):04d}"
        for table in getattr(page, "tables", []) or []:
            cells: list[dict[str, Any]] = []
            for col, text in enumerate(getattr(table, "headers", []) or []):
                cells.append({"row": 0, "col": col, "text": str(text)})
            for row_index, row in enumerate(getattr(table, "rows", []) or [], start=1):
                for col, cell in enumerate(getattr(row, "cells", []) or []):
                    cells.append({"row": row_index, "col": col, "text": str(getattr(cell, "text", ""))})
            if cells:
                blocks.append(
                    {
                        "type": "table",
                        "page_ids": [page_id],
                        "content": {"grid": {"cells": cells}},
                    }
                )
        for text in getattr(page, "texts", []) or []:
            content = str(getattr(text, "content", "") or "").strip()
            if content:
                blocks.append(
                    {
                        "type": "paragraph",
                        "page_ids": [page_id],
                        "bbox": getattr(text, "bbox", None),
                        "text": content,
                    }
                )
    return {"blocks": blocks, "evidence": evidence_payload(parse_result)}


def _extract_canonical_tables(payload: dict[str, Any]) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    for block in payload.get("blocks") or []:
        if not isinstance(block, dict) or block.get("type") != "table":
            continue
        cells = ((block.get("content") or {}).get("grid") or {}).get("cells") or []
        if not cells:
            continue
        max_row = max((int(cell.get("row", 0) or 0) for cell in cells), default=-1)
        max_col = max((int(cell.get("col", 0) or 0) for cell in cells), default=-1)
        if max_row < 0 or max_col < 0:
            continue
        rows = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
        for cell in cells:
            row = int(cell.get("row", 0) or 0)
            col = int(cell.get("col", 0) or 0)
            if row <= max_row and col <= max_col:
                rows[row][col] = _clean_cell(cell.get("text"))
        if rows:
            tables.append(rows)
    return tables


def _normalize_implicit_table(table: list[list[str]]) -> list[list[str]]:
    if not table:
        return []
    header_idx = next((idx for idx, row in enumerate(table[:6]) if _is_implicit_ledger_header(row)), -1)
    if header_idx < 0:
        return []
    header = table[header_idx]
    mapping = _header_mapping(header)
    out = [_STANDARD_HEADER]
    for row in table[header_idx + 1 :]:
        normalized = _normalize_row(row, mapping)
        if normalized:
            out.append(normalized)
    return out if len(out) > 1 else []


def _extract_paragraph_ledger_tables(payload: dict[str, Any]) -> list[list[list[str]]]:
    """Recover ledger rows that vNext kept as paragraph/list/footer text blocks.

    Scanned first pages often have valid OCR tokens and bboxes, but fail table-region
    reconstruction because stamps, page marks, or mixed multi-line cells disrupt the
    grid.  This path treats the visible ledger header as a column-role anchor and then
    uses domain invariants to parse the following text blocks into rows.
    """
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for block in payload.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        page_ids = block.get("page_ids") or []
        if not page_ids:
            continue
        by_page[str(page_ids[0])].append(block)

    tables: list[list[list[str]]] = []
    for _page_id, blocks in sorted(by_page.items()):
        ordered = sorted(blocks, key=_block_sort_key)
        header_idx = next((idx for idx, block in enumerate(ordered) if _is_paragraph_ledger_header(block)), -1)
        if header_idx < 0:
            continue
        rows: list[list[str]] = []
        prev_balance: float | None = None
        for block in ordered[header_idx + 1 :]:
            if str(block.get("type") or "") not in {"paragraph", "list", "footer", "unknown", "text"}:
                continue
            text = _clean_cell(block.get("text"))
            if not text or _is_header_or_meta_text(text):
                continue
            for fragment in _ledger_fragments(text):
                row = _parse_paragraph_ledger_fragment(fragment, prev_balance=prev_balance)
                if not row:
                    continue
                rows.append(row)
                try:
                    prev_balance = float(row[3])
                except ValueError:
                    prev_balance = None
        if rows:
            rows = _repair_balance_chain_rows(rows)
            tables.append([_STANDARD_HEADER, *rows])
    return tables


def _block_sort_key(block: dict[str, Any]) -> tuple[float, float]:
    bbox = block.get("bbox") or [0, 0, 0, 0]
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 2:
        return (0.0, 0.0)
    return (float(bbox[1] or 0), float(bbox[0] or 0))


def _is_paragraph_ledger_header(block: dict[str, Any]) -> bool:
    text = normalize_header_cell(str(block.get("text") or ""))
    return "交易日期" in text and ("收/支" in text or "收支" in text) and "交易金额" in text and "账户余额" in text


def _is_header_or_meta_text(text: str) -> bool:
    normalized = normalize_header_cell(text)
    if "交易日期" in normalized and "交易金额" in normalized:
        return True
    return bool(_NOISE_RE.search(text) and not _DATE_RE.search(text))


def _ledger_fragments(text: str) -> list[str]:
    """Split a text block into date-centered ledger fragments."""
    matches = list(_DATE_RE.finditer(text))
    if not matches:
        return []
    fragments: list[str] = []
    for idx, match in enumerate(matches):
        prev_end = matches[idx - 1].end() if idx > 0 else 0
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        start = prev_end
        end = next_start
        fragment = text[start:end].strip()
        if match.group(1) not in fragment:
            fragment = f"{match.group(1)} {fragment}"
        fragments.append(fragment)
    return fragments


def _parse_paragraph_ledger_fragment(fragment: str, *, prev_balance: float | None) -> list[str]:
    date_raw, direction_raw = _split_date_direction(fragment)
    date = _normalize_date(date_raw)
    direction = _normalize_direction(direction_raw or fragment)
    if not date or not direction:
        return []

    amounts = _amount_tokens(fragment)
    if len(amounts) < 2:
        return []
    amount, balance = _choose_amount_balance(amounts, direction, prev_balance)
    if amount is None or balance is None:
        return []

    counter_account = _extract_counter_account(fragment)
    summary = _extract_summary(fragment)
    counterparty = _extract_counterparty_from_fragment(fragment, counter_account)
    return [
        date,
        direction,
        f"{amount:.2f}",
        f"{balance:.2f}",
        summary,
        counter_account,
        counterparty,
        "",
        "",
        "",
    ]


def _amount_tokens(text: str) -> list[tuple[str, float, int]]:
    out: list[tuple[str, float, int]] = []
    for match in _AMOUNT_TOKEN_RE.finditer(text):
        raw = re.sub(r"\s+", "", match.group(0)).replace(",", "")
        try:
            out.append((raw, float(raw), match.start()))
        except ValueError:
            continue
    return out


def _choose_amount_balance(
    amounts: list[tuple[str, float, int]],
    direction: str,
    prev_balance: float | None,
) -> tuple[float | None, float | None]:
    if prev_balance is not None:
        best: tuple[float, float, float] | None = None
        for amount_idx, (_, amount, _) in enumerate(amounts):
            if amount <= 0:
                continue
            for balance_idx, (_, balance, _) in enumerate(amounts):
                if balance_idx == amount_idx:
                    continue
                expected = prev_balance + amount if direction == "收入" else prev_balance - amount
                error = abs(round(expected - balance, 2))
                candidate = (error, amount, balance)
                if best is None or candidate < best:
                    best = candidate
        if best is not None and best[0] <= 0.05:
            return best[1], best[2]

    if len(amounts) >= 2:
        return amounts[0][1], amounts[1][1]
    return None, None


def _repair_balance_chain_rows(rows: list[list[str]]) -> list[list[str]]:
    """Choose amount/balance orientation that minimizes page-local chain breaks."""
    if len(rows) < 2:
        return rows
    candidate_rows: list[list[list[str]]] = []
    for row in rows:
        candidates = [row]
        try:
            amount = float(row[2])
            balance = float(row[3])
        except (TypeError, ValueError):
            candidate_rows.append(candidates)
            continue
        if abs(amount - balance) > 0.001:
            swapped = list(row)
            swapped[2] = f"{balance:.2f}"
            swapped[3] = f"{amount:.2f}"
            candidates.append(swapped)
        candidate_rows.append(candidates)

    # dp[row][candidate] = (cost, previous_candidate_index)
    dp: list[list[tuple[float, int | None]]] = []
    dp.append([(0.02 * idx, None) for idx, _candidate in enumerate(candidate_rows[0])])
    for row_idx in range(1, len(candidate_rows)):
        current_scores: list[tuple[float, int | None]] = []
        for cand_idx, candidate in enumerate(candidate_rows[row_idx]):
            best: tuple[float, int | None] | None = None
            for prev_idx, prev_candidate in enumerate(candidate_rows[row_idx - 1]):
                prev_cost = dp[row_idx - 1][prev_idx][0]
                transition_cost = _balance_transition_cost(prev_candidate, candidate)
                swap_penalty = 0.02 * cand_idx
                score = prev_cost + transition_cost + swap_penalty
                if best is None or score < best[0]:
                    best = (score, prev_idx)
            current_scores.append(best or (9999.0, None))
        dp.append(current_scores)

    last_idx = min(range(len(dp[-1])), key=lambda idx: dp[-1][idx][0])
    selected = [0 for _ in rows]
    selected[-1] = last_idx
    for row_idx in range(len(rows) - 1, 0, -1):
        prev_idx = dp[row_idx][selected[row_idx]][1]
        selected[row_idx - 1] = int(prev_idx or 0)
    return [candidate_rows[row_idx][selected[row_idx]] for row_idx in range(len(rows))]


def _balance_transition_cost(previous: list[str], current: list[str]) -> float:
    try:
        prev_balance = float(previous[3])
        amount = float(current[2])
        balance = float(current[3])
    except (TypeError, ValueError):
        return 1.0
    direction = _normalize_direction(current[1])
    if direction == "收入":
        expected = prev_balance + amount
    elif direction == "支出":
        expected = prev_balance - amount
    else:
        return 1.0
    error = abs(round(expected - balance, 2))
    return 0.0 if error <= 0.01 else min(1.0, error / max(amount, 1.0))


def _extract_counter_account(fragment: str) -> str:
    for match in _ACCOUNT_RE.finditer(fragment):
        token = match.group(0)
        if _DATE_RE.fullmatch(token):
            continue
        return token
    return ""


def _extract_summary(fragment: str) -> str:
    for keyword in ("网络付款", "网络收款", "POS消费", "付息", "微信转账", "扫二维码", "美团支付"):
        if keyword in fragment:
            return keyword
    return ""


def _extract_counterparty_from_fragment(fragment: str, counter_account: str) -> str:
    text = fragment
    for value in _DATE_RE.findall(text) + _DIRECTION_RE.findall(text):
        text = text.replace(value, " ")
    for raw, _, _ in _amount_tokens(text):
        text = text.replace(raw, " ")
    if counter_account:
        text = text.replace(counter_account, " ")
    for keyword in ("网络付款", "网络收款", "POS消费", "付息", "微信转账", "扫二维码", "美团支付"):
        text = text.replace(keyword, " ")
    text = re.sub(r"\b(?:00)?98\b|\b(?:NY|YL)\d{4}\b|业务用章|第\s*\d+\s*页", " ", text)
    text = re.sub(r"[A-Za-z0-9&°]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _clean_counterparty(text)


def _is_implicit_ledger_header(row: list[str]) -> bool:
    joined = "".join(normalize_header_cell(cell) for cell in row)
    has_date = "交易日期" in joined
    has_amount = "交易金额" in joined or "金额" in joined
    has_balance = "账户余额" in joined or "余额" in joined
    has_direction = "收/支" in joined or "收支" in joined or any("收/支" in str(cell) for cell in row)
    return has_date and has_amount and has_balance and has_direction


def _header_mapping(header: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header):
        key = normalize_header_cell(cell)
        if "交易日期" in key and ("收/支" in cell or "收支" in key):
            mapping["combined_date_direction"] = idx
        elif "交易日期" in key:
            mapping["date"] = idx
        elif "收/支" in cell or "收支" in key or key in {"月收/支", "月收支"}:
            mapping["direction"] = idx
        elif "交易金额" in key or key == "金额":
            mapping["amount"] = idx
        elif "账户余额" in key or key == "余额":
            mapping["balance"] = idx
        elif "摘要" in key:
            mapping["summary"] = idx
        elif "对方账号" in key:
            mapping["counter_account"] = idx
        elif "对方户名" in key:
            mapping["counter_party"] = idx
        elif key == "机构":
            mapping["institution"] = idx
        elif "柜员" in key:
            mapping["teller"] = idx
        elif "备注" in key:
            mapping["remark"] = idx
    return mapping


def _normalize_row(row: list[str], mapping: dict[str, int]) -> list[str]:
    combined = _value(row, mapping.get("combined_date_direction"))
    date = _value(row, mapping.get("date"))
    direction = _value(row, mapping.get("direction"))
    if combined:
        parsed_date, parsed_direction = _split_date_direction(combined)
        date = date or parsed_date
        direction = direction or parsed_direction
    else:
        parsed_date, parsed_direction = _split_date_direction(f"{date}{direction}")
        date = parsed_date or date
        direction = parsed_direction or direction

    date = _normalize_date(date)
    direction = _normalize_direction(direction)
    amount = _normalize_amount_text(_value(row, mapping.get("amount")))
    balance = _normalize_amount_text(_value(row, mapping.get("balance")))
    if not date or not direction or not amount or not balance:
        return []
    return [
        date,
        direction,
        amount,
        balance,
        _value(row, mapping.get("summary")),
        _value(row, mapping.get("counter_account")),
        _clean_counterparty(_value(row, mapping.get("counter_party"))),
        _value(row, mapping.get("institution")),
        _value(row, mapping.get("teller")),
        _value(row, mapping.get("remark")),
    ]


def _split_date_direction(value: str) -> tuple[str, str]:
    text = _clean_cell(value)
    date_m = _DATE_RE.search(text)
    direction_m = _DIRECTION_RE.search(text)
    return (
        date_m.group(1) if date_m else "",
        direction_m.group(1) if direction_m else "",
    )


def _normalize_date(value: str) -> str:
    text = _clean_cell(value)
    if re.fullmatch(r"20\d{6}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    m = re.fullmatch(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def _normalize_direction(value: str) -> str:
    text = _clean_cell(value)
    if any(token in text for token in ("收入", "收人")):
        return "收入"
    if any(token in text for token in ("支出", "支山", "支鼎", "攴出")):
        return "支出"
    return ""


def _normalize_amount_text(value: str) -> str:
    text = _clean_cell(value).replace(",", "")
    text = re.sub(r"\s+", "", text)
    m = re.search(r"\d+(?:\.\d{1,2})?", text)
    return m.group(0) if m else ""


def _clean_counterparty(value: str) -> str:
    text = _clean_cell(value)
    text = re.sub(r"(?:00)?98", "", text)
    text = re.sub(r"\b(?:NY|YL)\d{4}\b", "", text)
    return text.strip()


def _value(row: list[str], idx: int | None) -> str:
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return _clean_cell(row[idx])


def _clean_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\n", " ")).strip()


def _recover_from_text(_full_text: str) -> list[list[list[str]]]:
    return []


__all__ = ["recover_ocr_implicit_ledger_tables", "recovered_ocr_implicit_row_count"]
