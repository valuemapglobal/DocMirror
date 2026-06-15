# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Borderless OCR bank ledger — relaxed header detection + char_strategy tables."""

from __future__ import annotations

from typing import Any

from docmirror.plugins._base.standardizer import normalize_amount
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.header_resolve import (
    RELAXED_MIN_COLUMNS,
    detect_headers,
    has_split_debit_credit_headers,
    registry_strict_header_match_count,
)
from docmirror.plugins.bank_statement.header_resolve import (
    registry_strict_header_match_count as strict_header_match_count,
)
from docmirror.plugins.bank_statement.institution import match_institution, normalize_table_headers
from docmirror.plugins.bank_statement.row_extract import count_transaction_data_rows, extract_all_tables
from docmirror.plugins.bank_statement.styles import grid_standard

PARSER_ID = "borderless_ocr"
STYLE_ID = "borderless_ocr"


def _prepare_tables(ctx: StyleContext) -> list[list[list[str]]]:
    variant = match_institution(ctx.full_text, ctx.institution)
    return normalize_table_headers(ctx.tables, variant=variant)


def is_ocr_dominant(ctx: StyleContext) -> bool:
    pr = ctx.parse_result
    if pr is None:
        return False
    info = getattr(pr, "parser_info", None)
    if info is None:
        return False
    method = getattr(info, "extraction_method", None)
    if method is None:
        return False
    val = method.value if hasattr(method, "value") else str(method)
    return val in ("ocr", "hybrid", "image")


def table_is_borderless_ocr(ctx: StyleContext, registry: dict[str, Any] | None = None) -> bool:
    """True when strict headers fail but relaxed headers + data rows succeed."""
    from docmirror.plugins.bank_statement.styles.compact_merged import table_has_compact_ledger
    from docmirror.plugins.bank_statement.styles.signed_amount import table_has_signed_amount_cells

    if not ctx.tables:
        return False
    if table_has_compact_ledger(ctx.tables) or table_has_signed_amount_cells(ctx.tables):
        return False

    if registry is None:
        from docmirror.plugins.bank_statement.community_plugin import BANK_COLUMN_REGISTRY

        registry = BANK_COLUMN_REGISTRY

    prepared = _prepare_tables(ctx)
    if has_split_debit_credit_headers(prepared) and registry_strict_header_match_count(prepared, registry) >= 2:
        return False

    registry_strict = registry_strict_header_match_count(prepared, registry)
    if registry_strict >= 3:
        return False

    header = detect_headers(prepared, registry, prefer_strict=False)
    if header is None or len(header.col_map) < RELAXED_MIN_COLUMNS:
        return False

    if count_transaction_data_rows(prepared, header) < 2:
        return False

    return is_ocr_dominant(ctx) or registry_strict < 3


def extract_transactions(ctx: StyleContext, plugin: Any) -> list[dict[str, str]]:
    prepared = _prepare_tables(ctx)
    batch = extract_all_tables(
        prepared,
        plugin.column_registry,
        prefer_strict=False,
        strict_first_col=False,
    )
    if batch:
        return batch
    return grid_standard.extract_transactions(ctx, plugin)


def normalize_record(raw_txn: dict[str, str], plugin: Any) -> dict[str, Any]:
    split = grid_standard.normalize_split_debit_credit(raw_txn, plugin)
    if split is not None:
        return split

    normalized = plugin._normalize(raw_txn)
    if normalized.get("amount") is None:
        for key, value in raw_txn.items():
            if any(n in key for n in ("金额", "发生", "Amount")):
                amount = normalize_amount(value)
                if amount is not None:
                    normalized["amount"] = float(amount)
                    normalized["amount_cny"] = float(amount)
                    break
    return normalized


def detect_headers_relaxed(
    tables: list[list[list[str]]],
    registry: dict[str, Any],
) -> tuple[int, list[str], dict[str, int]]:
    header = detect_headers(tables, registry, prefer_strict=False)
    if header is None:
        return 0, [], {}
    return header.row_index, header.raw_headers, header.col_map


__all__ = [
    "PARSER_ID",
    "STYLE_ID",
    "detect_headers_relaxed",
    "extract_transactions",
    "is_ocr_dominant",
    "normalize_record",
    "strict_header_match_count",
    "table_is_borderless_ocr",
]
