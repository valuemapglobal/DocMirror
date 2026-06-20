# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unified bank statement header resolution — SSOT for strict and relaxed matching.

Merges OCR header aliases, layout profile aliases, and ``ColumnMatcher`` into
``detect_headers`` with configurable strictness (minimum columns, lookahead rows).
Single entry for all bank style parsers when locating header rows and column maps.

Pipeline role: used by ``row_extract``, ``grid_standard``, and ``borderless_ocr``
before row iteration; bridges ``core.profile.registry`` with plugin column registry.

Key exports: ``HeaderMatch``, ``detect_headers``, ``canonical_key_for_field``,
``has_split_debit_credit_headers``, strict/relaxed threshold constants.

Dependencies: ``column_registry.ColumnMatcher``, ``bank_statement.institution``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from docmirror.core.profile.registry import resolve_header_aliases
from docmirror.plugins._base.column_registry import ColumnMatcher
from docmirror.plugins.bank_statement.institution import get_bank_layout_profile

# OCR / regional header variants merged into plugin-layer SSOT (not Mirror EPO).
_OCR_HEADER_ALIASES: dict[str, str] = {
    "值日": "交易日期",
    "交易日": "交易日期",
    "记账日": "交易日期",
    "交易说明": "摘要",
    "交易摘要": "摘要",
    "发生金额": "交易金额",
    "发生额(元)": "交易金额",
    "交易额(元)": "交易金额",
    "账面余领": "余额",
    "账 面余额": "余额",
    "账 面 余 额": "余额",
    "账面余额": "余额",
    "卡余额": "余额",
    "本次余额": "余额",
    "对手信息": "对方户名",
    "对⼿信息": "对方户名",
    "交易地点/附言": "摘要",
}
_PROFILE_TO_REGISTRY: dict[str, str] = {
    "交易时间": "交易日期",
    "账户余额": "余额",
}

STRICT_MIN_COLUMNS = 3
RELAXED_MIN_COLUMNS = 2
STRICT_LOOKAHEAD = 8
RELAXED_LOOKAHEAD = 15


@dataclass(frozen=True)
class HeaderMatch:
    table_index: int
    row_index: int
    raw_headers: list[str]
    col_map: dict[str, int]
    mode: str  # strict | relaxed


def normalize_header_cell(text: str) -> str:
    cell = unicodedata.normalize("NFKC", str(text or "").strip())
    if not cell:
        return cell
    profile = get_bank_layout_profile()
    cell = resolve_header_aliases(profile, cell)
    cell = _OCR_HEADER_ALIASES.get(cell, cell)
    cell = _PROFILE_TO_REGISTRY.get(cell, cell)
    return re.sub(r"[\s\n\r\t\u3000]", "", cell).replace("\u00a0", "")


def canonical_key_for_field(field_name: str, registry: dict[str, Any]) -> str:
    for canonical_name, mapping in registry.items():
        if mapping.field == field_name:
            return canonical_name
    return field_name


def _match_row(
    row: list[str],
    registry: dict[str, Any],
    *,
    min_columns: int,
) -> tuple[list[str], dict[str, int]] | None:
    matcher = ColumnMatcher(registry)
    normalized_row = [normalize_header_cell(c) for c in row]
    col_map = matcher.match(normalized_row)
    if len(col_map) >= min_columns:
        return [str(c or "").strip() for c in row], col_map
    return None


def best_header_match(
    tables: list[list[list[str]]],
    registry: dict[str, Any],
    *,
    max_rows: int,
    min_columns: int,
) -> HeaderMatch | None:
    best: HeaderMatch | None = None
    best_count = 0

    for tbl_idx, tbl in enumerate(tables):
        if not tbl:
            continue
        for row_idx, row in enumerate(tbl[:max_rows]):
            matched = _match_row(row, registry, min_columns=min_columns)
            if matched is None:
                continue
            raw_headers, col_map = matched
            count = len(col_map)
            mode = "strict" if count >= STRICT_MIN_COLUMNS else "relaxed"
            candidate = HeaderMatch(tbl_idx, row_idx, raw_headers, col_map, mode)
            if count > best_count:
                best = candidate
                best_count = count
            if count >= STRICT_MIN_COLUMNS:
                return candidate

    return best


def detect_headers(
    tables: list[list[list[str]]],
    registry: dict[str, Any],
    *,
    prefer_strict: bool = True,
) -> HeaderMatch | None:
    """Cascade strict → relaxed header detection."""
    if prefer_strict:
        strict = best_header_match(
            tables,
            registry,
            max_rows=STRICT_LOOKAHEAD,
            min_columns=STRICT_MIN_COLUMNS,
        )
        if strict is not None:
            return strict
    return best_header_match(
        tables,
        registry,
        max_rows=RELAXED_LOOKAHEAD,
        min_columns=RELAXED_MIN_COLUMNS,
    )


def registry_strict_header_match_count(
    tables: list[list[list[str]]],
    registry: dict[str, Any],
) -> int:
    """Max ColumnMatcher hits without OCR alias normalization (institution cells only)."""
    matcher = ColumnMatcher(registry)
    best = 0
    for tbl in tables:
        if not tbl:
            continue
        for row in tbl[:STRICT_LOOKAHEAD]:
            col_map = matcher.match([str(c or "").strip() for c in row])
            best = max(best, len(col_map))
    return best


def strict_header_match_count(tables: list[list[list[str]]], registry: dict[str, Any]) -> int:
    """Max normalized ColumnMatcher hits (includes OCR + profile aliases)."""
    best = 0
    for tbl in tables:
        if not tbl:
            continue
        for row in tbl[:STRICT_LOOKAHEAD]:
            matched = _match_row(row, registry, min_columns=1)
            if matched:
                best = max(best, len(matched[1]))
    return best


def has_split_debit_credit_headers(tables: list[list[list[str]]]) -> bool:
    for tbl in tables:
        for row in tbl[:RELAXED_LOOKAHEAD]:
            joined = "".join(normalize_header_cell(c) for c in row)
            if ("收入" in joined and "支出" in joined) or ("借方发生额" in joined and "贷方发生额" in joined):
                return True
    return False
