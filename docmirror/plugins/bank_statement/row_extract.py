# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Shared row extraction utilities for grid and borderless bank ledger styles.

Header-aware transaction row detection, debit/credit split handling, and multi-table
harvest helpers shared by ``grid_standard`` and ``borderless_ocr`` style parsers.

Pipeline role: called from style parser modules during ``extract_rows`` phases;
uses ``header_resolve.detect_headers`` for column alignment.

Key exports: ``row_has_transaction_data``, ``extract_rows_from_header``,
``extract_all_tables``, ``count_transaction_data_rows``.

Dependencies: ``bank_statement.header_resolve``.
"""

from __future__ import annotations

import re
from typing import Any

from docmirror.plugins.bank_statement.header_resolve import HeaderMatch, detect_headers
from docmirror.plugins.bank_statement.header_resolve import canonical_key_for_field

_ISO_DATE_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}")
_ISO_DATETIME_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}")
_COMPACT_DATE_RE = re.compile(r"^\d{8}$")
_AMOUNT_RE = re.compile(r"^[+-]?\d[\d,]*\.?\d*$")
_SUMMARY_MARKERS = ("合计", "小计", "本页", "总计")


def _looks_like_date(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _ISO_DATE_RE.match(t) or _ISO_DATETIME_RE.match(t):
        return True
    if _COMPACT_DATE_RE.match(t):
        try:
            y, m, d = int(t[:4]), int(t[4:6]), int(t[6:8])
            return 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31
        except ValueError:
            return False
    return False


def row_has_transaction_data(row: list[str], *, strict_first_col: bool = False) -> bool:
    if not row or not any(str(c).strip() for c in row):
        return False
    texts = [str(c or "").strip() for c in row]
    has_date = any(_looks_like_date(t) for t in texts)
    if strict_first_col and texts:
        has_date = _looks_like_date(texts[0]) or has_date
    has_amount = any(
        _AMOUNT_RE.match(t.replace(",", "").replace("¥", "").replace("￥", ""))
        for t in texts
        if re.search(r"\d", t)
    )
    return has_date and has_amount


def count_transaction_data_rows(
    tables: list[list[list[str]]],
    header: HeaderMatch,
) -> int:
    count = 0
    tbl = tables[header.table_index]
    for row in tbl[header.row_index + 1 :]:
        if row_has_transaction_data(row, strict_first_col=False):
            count += 1
    return count


def extract_rows_from_header(
    tables: list[list[list[str]]],
    header: HeaderMatch,
    registry: dict[str, Any],
    *,
    strict_first_col: bool = False,
) -> list[dict[str, str]]:
    transactions: list[dict[str, str]] = []
    tbl = tables[header.table_index]
    for row in tbl[header.row_index + 1 :]:
        if not row or not any(str(c).strip() for c in row):
            continue
        first_cell = str(row[0] or "").strip()
        if any(kw in first_cell for kw in _SUMMARY_MARKERS):
            continue
        if not row_has_transaction_data(row, strict_first_col=strict_first_col):
            continue

        txn: dict[str, str] = {}
        for field_name, col_idx in header.col_map.items():
            if col_idx < len(row):
                key = canonical_key_for_field(field_name, registry)
                txn[key] = str(row[col_idx] or "").strip()
        if any(txn.values()):
            transactions.append(txn)
    return transactions


def extract_all_tables(
    tables: list[list[list[str]]],
    registry: dict[str, Any],
    *,
    prefer_strict: bool = True,
    strict_first_col: bool = False,
) -> list[dict[str, str]]:
    """Detect headers per table segment and merge transaction rows."""
    all_txns: list[dict[str, str]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()

    for tbl_idx, tbl in enumerate(tables):
        if not tbl:
            continue
        header = detect_headers([tbl], registry, prefer_strict=prefer_strict)
        if header is None:
            continue
        header = HeaderMatch(
            table_index=tbl_idx,
            row_index=header.row_index,
            raw_headers=header.raw_headers,
            col_map=header.col_map,
            mode=header.mode,
        )
        for txn in extract_rows_from_header(tables, header, registry, strict_first_col=strict_first_col):
            key = tuple(sorted(txn.items()))
            if key in seen:
                continue
            seen.add(key)
            all_txns.append(txn)
    return all_txns
