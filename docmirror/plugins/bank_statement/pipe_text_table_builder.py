# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Pipe-delimited bank ledger table builder from Mirror full text.

When Mirror reports zero physical tables but full_text contains ASCII pipe rows
(BOC / mainframe style), reconstructs a multi-column grid with split debit/credit
columns for downstream ``split_debit_credit`` parsing.

Pipeline role: S1 strategy inside ``ltro.reconstruct_tables``.

Key exports: ``detect_pipe_header_in_text``, ``build_tables_from_pipe_text``,
``count_expected_primary_rows``.

Dependencies: ``core.table.pipe_row_merge.merge_pipe_continuation_rows``.
"""

from __future__ import annotations

import re

from docmirror.core.table.pipe_row_merge import merge_pipe_continuation_rows

_PIPE_HEADER_ZH = re.compile(r"\|?\s*序号\s*\|.*记账日", re.IGNORECASE)
_PIPE_HEADER_EN = re.compile(r"\|\s*No\.\s*\|.*Bk\.D\.", re.IGNORECASE)
_SPLIT_AMOUNT_MARKERS = ("借方发生额", "贷方发生额", "Debit Amount", "Credit Amount")
_PRIMARY_ROW_RE = re.compile(r"^\|\s*\d+\s*\|")
_HLINE_RE = re.compile(r"^[\s─━\-|]+$")
_FOOTER_MARKERS = ("借方合计", "Debit Total", "本对账期末余额")
_HEADER_REPEAT_RE = re.compile(r"\|?\s*序号\s*\|.*记账日")


def split_pipe_row(line: str) -> list[str]:
    """Split a pipe-delimited line into trimmed cell values."""
    parts = [p.strip() for p in line.split("|")]
    if line.strip().startswith("|") and parts and parts[0] == "":
        parts = parts[1:]
    if line.strip().endswith("|") and parts and parts[-1] == "":
        parts = parts[:-1]
    return parts


def _line_has_split_amount_headers(line: str) -> bool:
    return any(m in line for m in _SPLIT_AMOUNT_MARKERS)


def detect_pipe_header_in_text(text: str) -> bool:
    """True when text looks like a pipe ledger with split debit/credit columns."""
    if not text or "|" not in text:
        return False
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not (_PIPE_HEADER_ZH.search(line) or _PIPE_HEADER_EN.search(line)):
            continue
        window = "\n".join(lines[i : i + 3])
        if _line_has_split_amount_headers(window):
            return True
    return False


def _is_header_row(line: str) -> bool:
    return bool(_HEADER_REPEAT_RE.search(line)) and _line_has_split_amount_headers(line)


def _is_data_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped or not stripped.startswith("|"):
        return False
    if _HLINE_RE.match(stripped):
        return False
    if any(m in stripped for m in _FOOTER_MARKERS):
        return False
    return bool(_PRIMARY_ROW_RE.match(stripped))


def _is_continuation_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    if _HLINE_RE.match(stripped):
        return False
    if _is_header_row(stripped):
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


def build_tables_from_pipe_text(text: str) -> list[list[list[str]]]:
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

    if len(table) < 2:
        return []
    return [table]


def count_expected_primary_rows(text: str) -> int:
    """Count primary pipe rows (with sequence number) before continuation merge."""
    if not detect_pipe_header_in_text(text):
        return 0
    return sum(1 for line in text.splitlines() if _is_data_row(line.strip()))
