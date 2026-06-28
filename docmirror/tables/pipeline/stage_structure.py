# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Table pipeline structure stage — data row cleanup and column repairs.

Purpose: Splits merged columns, repairs split numbers, filters junk rows, and
applies structure fixes before domain hooks.

Main components: ``run`` (structure stage), ``filter_junk_rows``,
``apply_structure_fixes``.

Upstream: Header-normalized table.

Downstream: ``stage_domain``, ``table.table_structure_fix``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from docmirror.structure.utils.text_utils import (
    _RE_DATE_COMPACT,
    _RE_DATE_HYPHEN,
    _RE_ONLY_CJK,
    _RE_TIME,
    parse_amount,
)
from docmirror.structure.utils.vocabulary import (
    _is_junk_row,
    _normalize_for_vocab,
)
from docmirror.tables.char.semantic_column_mapper import SemanticColumnMapper
from docmirror.tables.pipeline.stage_preamble import _extract_preamble_kv
from docmirror.tables.table_structure_fix import merge_split_rows

logger = logging.getLogger(__name__)

_RE_SEQ_PLUS_DESC = re.compile(
    r"^(\d{1,6})"  # Sequence number (1-6 digits)
    r"([^\d\s,.].*)",  # Followed by non-numeric text (the description)
    re.DOTALL,
)
_RE_BALANCE_PLUS_TEXT = re.compile(
    r"^([\d,]+\.\d{2})"  # Amount with 2 decimal places (e.g. 56,264.17)
    r"([^\d\s,.].*)",  # Followed by non-numeric text (remarks)
    re.DOTALL,
)


def _split_merged_columns(
    header: list[str],
    data_rows: list[list[str]],
) -> tuple[list[str], list[list[str]]] | None:
    """Semantic column split: detect and repair cells where adjacent columns
    were merged due to narrow spatial gaps in the PDF.

    Detectable patterns:
      1. 序号+摘要 merge: cell = "2851消费" → split into ["2851", "消费"]
      2. 余额+附言 merge: cell = "56,264.17财付通-微信支付" → split into ["56,264.17", "财付通-..."]

    Activation: only triggers when >30% of data rows show the pattern.
    Safety: does nothing for columns that don't match the patterns.

    Returns:
        ``(new_header, new_data_rows)`` if any split was applied, else ``None``.
    """
    if not header or not data_rows or len(data_rows) < 5:
        return None

    n_cols = len(header)
    n_rows = len(data_rows)

    # ── Detect mergeable columns ──
    # For each column, count how many rows have a pattern match
    split_specs = []  # (col_idx, pattern, new_header_left, new_header_right, match_count)

    for ci in range(n_cols):
        h = _normalize_for_vocab(header[ci]) if ci < len(header) else ""

        # Pattern 1: Sequence-number column with appended description
        if h in ("序号", "交易序号", "编号", "no", "no.", "序列号"):
            match_count = sum(
                1 for r in data_rows if ci < len(r) and r[ci] and _RE_SEQ_PLUS_DESC.match(str(r[ci]).strip())
            )
            if match_count > n_rows * 0.3:
                # Find the next column — it should be the empty summary-column target
                next_empty_ci = None
                for nci in range(ci + 1, n_cols):
                    nh = _normalize_for_vocab(header[nci]) if nci < len(header) else ""
                    empty_count = sum(1 for r in data_rows if nci < len(r) and not (r[nci] or "").strip())
                    if empty_count > n_rows * 0.3 or nh in ("摘要", "交易摘要", "用途", "附言"):
                        next_empty_ci = nci
                        break
                if next_empty_ci is not None:
                    split_specs.append((ci, _RE_SEQ_PLUS_DESC, next_empty_ci))

        # Pattern 2: Balance column with appended remarks
        # Look for columns where values look like "56,264.17<company>-<product>" (numeric balance with appended text)
        # Trigger: check ANY column for this pattern (not just specific headers)
        match_count = sum(
            1 for r in data_rows if ci < len(r) and r[ci] and _RE_BALANCE_PLUS_TEXT.match(str(r[ci]).strip())
        )
        if match_count > n_rows * 0.3:
            # The balance portion should go to the PREVIOUS column (if mostly empty)
            prev_ci = ci - 1
            if prev_ci >= 0:
                prev_empty = sum(1 for r in data_rows if prev_ci < len(r) and not (r[prev_ci] or "").strip())
                if prev_empty > n_rows * 0.3:
                    split_specs.append((ci, _RE_BALANCE_PLUS_TEXT, -(prev_ci)))

    if not split_specs:
        return None

    # ── Apply splits ──
    modified = False
    new_data_rows = []

    for row in data_rows:
        new_row = list(row)
        # Pad to header length
        while len(new_row) < n_cols:
            new_row.append("")

        for ci, pattern, target_ci in split_specs:
            if ci >= len(new_row):
                continue
            cell = str(new_row[ci] or "").strip()
            if not cell:
                continue

            m = pattern.match(cell)
            if not m:
                continue

            left_part = m.group(1).strip()
            right_part = m.group(2).strip()

            if target_ci < 0:
                # Balance+text: balance goes to previous column, text stays
                prev_ci = -target_ci
                if prev_ci < len(new_row) and not (new_row[prev_ci] or "").strip():
                    new_row[prev_ci] = left_part
                    new_row[ci] = right_part
                    modified = True
            else:
                # Seq+desc: sequence stays, description goes to next column
                if target_ci < len(new_row) and not (new_row[target_ci] or "").strip():
                    new_row[ci] = left_part
                    new_row[target_ci] = right_part
                    modified = True

        new_data_rows.append(new_row)

    if not modified:
        return None

    # Count how many rows were actually split
    split_count = sum(1 for orig, new in zip(data_rows, new_data_rows) if orig != new)

    spec_desc = ", ".join(f"col {ci}->{target_ci}" for ci, _, target_ci in split_specs)
    logger.info(
        f"[TableFix] Applied semantic column split for concatenated cells (e.g. CCB format): repaired {split_count}/{n_rows} rows ({spec_desc})"
    )

    return header, new_data_rows


def _clean_cell(cell: str, col_name: str) -> str:
    """General-purpose cell cleaning (adaptive to column-name features)."""
    cell = (cell or "").strip()
    if not cell:
        return cell

    col_lower = col_name.lower()

    # ── F-5: account-number / ID columns — return as-is, no formatting ──
    _ID_KEYWORDS = [
        "\u8d26\u53f7",
        "\u5361\u53f7",
        "\u5e8f\u53f7",
        "\u7f16\u53f7",
        "\u51ed\u8bc1",
        "\u6d41\u6c34\u53f7",
        "\u65e5\u5fd7\u53f7",
        "account",
        "\u50a8\u79cd",
        "\u5730\u533a",
    ]
    if any(kw in col_lower for kw in _ID_KEYWORDS):
        return cell

    # ── F-4: date-time columns — preserve complete date and time ──
    if any(kw in col_lower for kw in ["\u65e5\u671f", "\u65f6\u95f4", "date"]):
        # Extract time from the original cell (including spaces)
        time_match = _RE_TIME.search(cell)

        compact = cell.replace(" ", "")
        date_match = _RE_DATE_HYPHEN.search(compact)
        if not date_match:
            raw_match = _RE_DATE_COMPACT.search(compact)
            if raw_match:
                d = raw_match.group(1)
                date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
                date_match = _RE_DATE_HYPHEN.search(date_str)
                # Try extracting HHMMSS from after the compact date (e.g. 20250921162345)
                if not time_match:
                    after_date = compact[raw_match.end() :]
                    hhmmss = re.match(r"(\d{2})(\d{2})(\d{2})", after_date)
                    if hhmmss:
                        h, m, s = int(hhmmss.group(1)), int(hhmmss.group(2)), int(hhmmss.group(3))
                        if 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59:
                            time_match = type("M", (), {"group": lambda _self: f"{h:02d}:{m:02d}:{s:02d}"})()

        if date_match:
            # Also try finding standard time format (HH:MM:SS) from compact string
            if not time_match:
                time_match = _RE_TIME.search(compact)
            return f"{date_match.group()} {time_match.group()}" if time_match else date_match.group()

    if any(kw in col_lower for kw in ["\u91d1\u989d", "\u4f59\u989d", "\u53d1\u751f", "amount", "balance"]):
        return parse_amount(cell)

    if any(kw in col_lower for kw in ["\u5e01", "currency"]):
        cleaned = _RE_ONLY_CJK.sub("", cell)
        return cleaned if cleaned else cell

    return cell


def _repair_split_numbers(data_rows: list[list[str]]) -> None:
    """Reassemble cross-column digit overflow fragments in place."""
    _RE_TRAILING_FRAG = re.compile(r"(\s+)(\d{1,3},)$")
    for row in data_rows:
        for j in range(len(row) - 1):
            cell = (row[j] or "").strip()
            next_cell = (row[j + 1] or "").strip()
            if not cell or not next_cell:
                continue
            if not re.match(r"\d", next_cell):
                continue
            if re.fullmatch(r"\d{1,3},", cell):
                row[j] = ""
                row[j + 1] = cell + next_cell
                continue
            m = _RE_TRAILING_FRAG.search(cell)
            if m:
                tail = m.group(2)
                row[j] = cell[: m.start()].strip()
                row[j + 1] = tail + next_cell


def filter_junk_rows(
    _header: list[str],
    data_rows: list[list[str]],
    preamble_kv: dict[str, str],
) -> list[list[str]]:
    """Remove junk/short rows; merge tail summary KV into preamble_kv."""
    clean_rows = []
    tail_junk_rows = []
    for r in data_rows:
        if len(r) < 2:
            continue
        if _is_junk_row(r):
            tail_junk_rows.append(r)
            continue
        clean_rows.append(r)
    if tail_junk_rows:
        tail_kv = _extract_preamble_kv(tail_junk_rows)
        if tail_kv:
            preamble_kv.update(tail_kv)
            logger.debug(f"tail summary KV: {tail_kv}")
    return clean_rows


def apply_structure_fixes(
    header: list[str],
    data_rows: list[list[str]],
) -> tuple[list[str], list[list[str]]]:
    """Semantic column split + split-number repair."""
    try:
        split_result = _split_merged_columns(header, data_rows)
        if split_result is not None:
            header, data_rows = split_result
    except Exception as e:
        logger.debug(f"split_merged rollback: {e}")
    try:
        mapped_rows = SemanticColumnMapper().map_table(data_rows, headers=header)
        if mapped_rows is not None:
            data_rows = mapped_rows
    except Exception as e:
        logger.debug(f"semantic_column_mapper rollback: {e}")
    _repair_split_numbers(data_rows)
    return header, data_rows


def clean_data_rows(header: list[str], data_rows: list[list[str]]) -> list[list[str]]:
    """Align row width and clean cells."""
    result: list[list[str]] = [header]
    for row in data_rows:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        elif len(row) > len(header):
            row = row[: len(header)]
        try:
            row = [_clean_cell(cell, col_name) for cell, col_name in zip(row, header)]
        except Exception as e:
            logger.debug(f"clean_cell rollback: {e}")
        result.append(row)
    return result


def run(ctx: Any, rows: list[list[str]]) -> list[list[str]]:
    """Structure stage for staged TNP — merge split rows when header present."""
    if not rows or len(rows) < 2:
        return rows
    _ = ctx
    try:
        return merge_split_rows(rows)
    except Exception:
        return rows


__all__ = [
    "_clean_cell",
    "_split_merged_columns",
    "apply_structure_fixes",
    "clean_data_rows",
    "filter_junk_rows",
    "merge_split_rows",
    "run",
]
