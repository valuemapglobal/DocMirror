# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Table access layer — unified API for reading tables from ParseResult.

Purpose: Provides ``get_logical_tables``, ``table_flatten``, and
``get_physical_tables`` so plugins prefer composed logical tables with raw
fallback to page tables.

Main components: ``get_logical_tables``, ``table_flatten``, ``get_physical_tables``.

Upstream: canonical ``ParseResult`` (logical + physical tables).

Downstream: Plugins, benchmarks, and external consumers.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from docmirror.models.entities.parse_result import (
    LogicalTable,
    ParseResult,
    RowProvenance,
    TableRow,
)

logger = logging.getLogger(__name__)


def get_logical_tables(result: ParseResult) -> list[LogicalTable]:
    """Get logical tables from a ParseResult.

    Priority:
      1. ``result.logical_tables`` — composed cross-page tables.
      2. Fallback: ``result.pages[0].tables`` (raw merged table).

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

        logical.append(
            LogicalTable(
                table_id=table.table_id,
                headers=list(table.headers),
                rows=all_rows,
                confidence=table.confidence,
                source_pages=source_pages,
                page_span=(min(source_pages), max(source_pages)),
                row_count=table.row_count,
                provenance=provenance,
                merge_log=merge_log,
            )
        )

    return logical


def primary_export_logical_table(result: ParseResult) -> LogicalTable | None:
    """Primary export logical table — passed LTs only; raw max row_count fallback."""
    logical = get_logical_tables(result)
    if not logical:
        return None
    passed = [lt for lt in logical if getattr(lt, "quality_passed", True)]
    candidates = passed if passed else logical
    return max(
        candidates,
        key=lambda lt: int(getattr(lt, "data_row_estimate", 0) or getattr(lt, "row_count", 0) or 0),
    )


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


def get_physical_cell_bbox(result: ParseResult, ref: dict[str, Any]) -> list[float] | None:
    """Resolve a logical source cell ref to a physical cell bbox."""
    page_no = int(ref.get("page") or 0)
    table_id = str(ref.get("table_id") or "")
    row_idx = int(ref.get("row") if ref.get("row") is not None else -1)
    col_idx = int(ref.get("col") if ref.get("col") is not None else -1)
    if page_no <= 0 or row_idx < 0 or col_idx < 0:
        return None
    for page in result.pages:
        if page.page_number != page_no:
            continue
        for table in page.tables:
            if table_id and table.table_id != table_id:
                continue
            if row_idx >= len(table.rows):
                continue
            row = table.rows[row_idx]
            if col_idx >= len(row.cells):
                continue
            return row.cells[col_idx].bbox
    return None


__all__ = [
    "get_logical_tables",
    "primary_export_logical_table",
    "table_flatten",
    "get_physical_tables",
    "get_physical_cell_bbox",
]
