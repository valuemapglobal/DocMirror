# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Row taxonomy for ledger tables — Mirror Core SSOT (BS-003 / design Phase 4).

Classifies pipe-delimited and grid rows as data, header, preamble, footer, etc.
Used by pipe extraction and ledger post-process to drop repeated headers without
bank-specific plugin logic.
"""

from __future__ import annotations

import re
from enum import Enum

from docmirror.layout.profile.registry import load_table_semantics

_PIPE_RULES = load_table_semantics().get("pipe_grid") or {}
_PIPE_HEADER_PATTERNS = tuple(
    re.compile(str(pattern), re.IGNORECASE) for pattern in _PIPE_RULES.get("header_patterns", ())
)
_PRIMARY_SEQ_RE = re.compile(r"^\d+$")
_PREAMBLE_FIRST = frozenset(str(value).lower() for value in _PIPE_RULES.get("preamble_first", ()))
_FOOTER_MARKERS = tuple(str(value) for value in _PIPE_RULES.get("footer_markers", ()))
_SPLIT_AMOUNT_MARKERS = tuple(str(value) for value in _PIPE_RULES.get("split_amount_markers", ()))
_HLINE_RE = re.compile(r"^[\s─━\-|]+$")


class RowKind(str, Enum):
    DATA = "data"
    HEADER = "header"
    PREAMBLE = "preamble"
    FOOTER = "footer"
    SEPARATOR = "separator"
    JUNK = "junk"


def _joined(cells: list[str]) -> str:
    return "|".join(str(c or "") for c in cells)


def _has_split_amount_headers(text: str) -> bool:
    return any(m in text for m in _SPLIT_AMOUNT_MARKERS)


def classify_pipe_cells(cells: list[str]) -> RowKind:
    """Classify a pipe/grid row from cell values."""
    if not cells:
        return RowKind.JUNK

    joined = _joined(cells)
    stripped = joined.strip()
    if not stripped:
        return RowKind.JUNK
    if _HLINE_RE.match(stripped):
        return RowKind.SEPARATOR

    first = (cells[0] or "").strip()
    first_lower = first.lower()

    if any(pattern.search(joined) for pattern in _PIPE_HEADER_PATTERNS) and _has_split_amount_headers(joined):
        return RowKind.HEADER
    if first_lower in _PREAMBLE_FIRST:
        return RowKind.PREAMBLE
    if any(m in joined for m in _FOOTER_MARKERS):
        return RowKind.FOOTER
    if _PRIMARY_SEQ_RE.match(first):
        return RowKind.DATA
    if not first and any(str(c or "").strip() for c in cells[1:]):
        return RowKind.DATA
    if _has_split_amount_headers(joined) and not _PRIMARY_SEQ_RE.match(first):
        return RowKind.PREAMBLE
    return RowKind.JUNK


def classify_pipe_line(line: str) -> RowKind:
    """Classify a raw pipe-delimited text line."""
    from docmirror.tables.structure_detect.pipe_grid import split_pipe_row

    stripped = (line or "").strip()
    if not stripped:
        return RowKind.JUNK
    if _HLINE_RE.match(stripped):
        return RowKind.SEPARATOR
    if any(m in stripped for m in _FOOTER_MARKERS):
        return RowKind.FOOTER
    if not stripped.startswith("|"):
        return RowKind.JUNK
    cells = split_pipe_row(stripped)
    return classify_pipe_cells(cells)


def is_pipe_data_row(cells: list[str]) -> bool:
    return classify_pipe_cells(cells) == RowKind.DATA


def is_pipe_header_row(cells: list[str]) -> bool:
    return classify_pipe_cells(cells) == RowKind.HEADER


def filter_pipe_table_rows(table: list[list[str]]) -> list[list[str]]:
    """Drop repeated headers, preamble, footer — keep one header + data rows."""
    if not table or len(table) < 2:
        return table

    header: list[str] | None = None
    out: list[list[str]] = []
    for row in table:
        kind = classify_pipe_cells(row)
        if kind == RowKind.HEADER:
            if header is None:
                header = row
                out.append(row)
            continue
        if kind in (RowKind.PREAMBLE, RowKind.FOOTER, RowKind.SEPARATOR, RowKind.JUNK):
            continue
        out.append(row)

    return out if len(out) >= 2 else table


__all__ = [
    "RowKind",
    "classify_pipe_cells",
    "classify_pipe_line",
    "filter_pipe_table_rows",
    "is_pipe_data_row",
    "is_pipe_header_row",
]
