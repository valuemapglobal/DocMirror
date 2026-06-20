# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build logical pipe tables from plain text (Core SSOT, CCP-safe)."""

from __future__ import annotations

import re

from docmirror.core.table.pipe_row_merge import merge_pipe_continuation_rows
from docmirror.core.table.row_kind import RowKind, classify_pipe_line, filter_pipe_table_rows
from docmirror.core.table.structure_detect.pipe_grid import (
    count_primary_pipe_rows,
    detect_pipe_header_in_text,
    split_pipe_row,
)

_SPLIT_AMOUNT_MARKERS = ("借方发生额", "贷方发生额", "Debit Amount", "Credit Amount")
_HLINE_RE = re.compile(r"^[\s─━\-|]+$")
_FOOTER_MARKERS = ("借方合计", "Debit Total", "本对账期末余额")
_PRIMARY_ROW_RE = re.compile(r"^\|\s*\d+\s*\|")


def _is_header_row(line: str) -> bool:
    return classify_pipe_line(line) == RowKind.HEADER


def _is_data_row(line: str) -> bool:
    return classify_pipe_line(line) == RowKind.DATA


def _is_continuation_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    if classify_pipe_line(stripped) in (RowKind.SEPARATOR, RowKind.HEADER, RowKind.FOOTER):
        return False
    cells = split_pipe_row(stripped)
    if not cells:
        return False
    first = cells[0].strip()
    return not first and any(c.strip() for c in cells[1:])


def _normalize_row_width(row: list[str], width: int) -> list[str]:
    if len(row) < width:
        return row + [""] * (width - len(row))
    if len(row) > width:
        return row[:width]
    return row


def build_pipe_table_from_text(text: str) -> list[list[list[str]]]:
    """Parse pipe-delimited ledger text into a single logical table."""
    if not detect_pipe_header_in_text(text):
        return []

    lines = text.splitlines()
    header_row: list[str] | None = None
    header_width = 0
    data_rows: list[list[str]] = []
    header_seen = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _HLINE_RE.match(stripped):
            continue

        if _is_header_row(stripped):
            cells = split_pipe_row(stripped)
            if not header_seen:
                header_row = cells
                header_width = len(cells)
                header_seen = True
            continue

        if header_row is None:
            continue

        if any(m in stripped for m in _FOOTER_MARKERS):
            continue

        if _is_data_row(stripped) or _is_continuation_row(stripped):
            cells = _normalize_row_width(split_pipe_row(stripped), header_width)
            data_rows.append(cells)

    if header_row is None or not data_rows:
        return []

    table = [header_row] + data_rows
    table = merge_pipe_continuation_rows(table)
    table = filter_pipe_table_rows(table)

    if len(table) < 2:
        return []
    return [table]


def count_expected_primary_rows(text: str) -> int:
    return count_primary_pipe_rows(text)
