# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
table_access — Unified table access layer
===========================================

Provides a single entry point for Plugin and downstream code to read
tables from a ParseResult, with the following priority:

  1. ``logical_tables`` — composed cross-page tables (preferred).
  2. Fallback to ``pages[0].tables`` — legacy merged physical tables.

This decouples consumers from the internal representation and enables
the Physical + Logical dual-view transition described in the table layer
first-principles redesign.

Usage::

    from docmirror.core.table.table_access import get_logical_tables, table_flatten

    result = await perceive_document("statement.pdf")

    # Get all logical tables
    tables = get_logical_tables(result)

    # Flatten to list of dicts (for plugin consumption)
    rows = table_flatten(result)

    # Flatten with provenance
    rows = table_flatten(result, include_source=True)
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from docmirror.models.entities.parse_result import (
    ParseResult,
    LogicalTable,
    TableRow,
    RowProvenance,
)

logger = logging.getLogger(__name__)


def get_logical_tables(result: ParseResult) -> list[LogicalTable]:
    """Get logical tables from a ParseResult.

    Priority:
      1. ``result.logical_tables`` — composed cross-page tables.
      2. Fallback: ``result.pages[0].tables`` (legacy merged table).

    Returns:
        List of LogicalTable objects (may be empty).
    """
    if result.logical_tables:
        return result.logical_tables

    # Fallback: build logical tables from physical pages[0].tables
    if not result.pages:
        return []

    first_page = result.pages[0]
    logical: list[LogicalTable] = []

    for table in first_page.tables:
        # Check if physical pages after page 1 have tables that were merged
        # by old merger — if so, reconstruct LogicalTable
        all_rows = list(table.rows)
        provenance: list[RowProvenance] = []
        merge_log: list[dict] = []

        for page in result.pages:
            if page.page_number == 1:
                continue

        source_pages = list(dict.fromkeys(r.source_page for r in table.rows if r.source_page))
        if not source_pages:
            source_pages = [1]

        logical.append(LogicalTable(
            table_id=table.table_id,
            headers=list(table.headers),
            rows=all_rows,
            confidence=table.confidence,
            source_pages=source_pages,
            page_span=(min(source_pages), max(source_pages)),
            row_count=table.row_count,
            provenance=provenance,
            merge_log=merge_log,
        ))

    return logical


def table_flatten(
    result: ParseResult,
    include_source: bool = False,
) -> list[dict[str, Any]]:
    """Flatten logical tables to a list of dicts for plugin consumption.

    Each dict represents one row, keyed by header name.

    Args:
        result: ParseResult from perceive_document.
        include_source: If True, include ``_source_page`` and ``_source_row``.

    Returns:
        List of dicts, one per row.
    """
    out: list[dict[str, Any]] = []
    tables = get_logical_tables(result)

    for table in tables:
        headers = table.headers
        for row_idx, row in enumerate(table.rows):
            d: dict[str, Any] = {}
            for col_idx, cell in enumerate(row.cells):
                if col_idx < len(headers):
                    d[headers[col_idx]] = cell.cleaned or cell.text
            if include_source:
                if table.provenance and row_idx < len(table.provenance):
                    d["_source_page"] = table.provenance[row_idx].source_page
                    d["_source_row"] = table.provenance[row_idx].source_row_index
                else:
                    d["_source_page"] = row.source_page
                    d["_source_row"] = row_idx
            out.append(d)

    if not out:
        return out

    return out


def get_physical_tables(result: ParseResult) -> Iterator[tuple[int, int, list[str], list[TableRow]]]:
    """Iterate over physical (per-page) tables.

    Yields:
        (page_number, table_index, headers, rows) tuples.
    """
    for page in result.pages:
        for ti, table in enumerate(page.tables):
            yield page.page_number, ti, table.headers, table.rows


__all__ = [
    "get_logical_tables",
    "table_flatten",
    "get_physical_tables",
]
