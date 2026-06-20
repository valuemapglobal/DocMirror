# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Table pipeline header stage — header row detection and repair.

Purpose: Vocabulary-guided header index detection, multi-row header merge,
and header cell fixes.

Main components: ``run_header_stage``, ``detect_header_index``,
``_fix_header_by_vocabulary``.

Upstream: Preamble-stripped table matrix.

Downstream: ``table.pipeline.stage_structure``, ``table.column_anchor``.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.core.table.pipeline.stage_preamble import _extract_preamble_kv, _strip_preamble
from docmirror.core.table.pipeline.vocab_match import _find_vocab_words_in_string
from docmirror.core.utils.text_utils import normalize_table as normalize_table_rows
from docmirror.core.utils.vocabulary import (
    _is_data_row,
    _is_header_row,
    _score_header_by_vocabulary,
)

logger = logging.getLogger(__name__)


def _fix_header_by_vocabulary(
    table: list[list[str]],
) -> list[list[str]]:
    """Vocabulary-driven header correction: fix concatenated column names
    without changing the column count or data rows.

    Strategy: concatenate all header cells, then use vocabulary matching
    to find more column names; fill the matched names back into the
    original columns in positional order.
    """
    if not table or len(table) < 2:
        return table

    header = table[0]
    n_cols = len(header)
    old_score = _score_header_by_vocabulary(header)

    concat = "".join((c or "").strip() for c in header)
    if not concat:
        return table

    found = _find_vocab_words_in_string(concat)

    # Guard 1: matched word count must significantly exceed existing matches (indicates concatenation)
    min_improvement = max(3, old_score + 3) if old_score >= 3 else old_score * 2 + 1
    if len(found) <= min_improvement:
        return table
    # Guard 2: at least 3 vocabulary matches
    if len(found) < 3:
        return table
    # Guard 3: vocabulary words must cover >= 50 % of the concatenated string
    # Note: use de-spaced length since PDF headers often have large inter-column spaces
    concat_nospace = concat.replace(" ", "").replace("\u3000", "")
    covered = sum(end - start for _, start, end in found)
    if covered / max(len(concat_nospace), 1) < 0.5:
        return table

    # Replace header row only; data rows are untouched
    new_header = [w for w, _, _ in found]
    if len(new_header) > n_cols:
        new_header = new_header[:n_cols]
    elif len(new_header) < n_cols:
        new_header += header[len(new_header) :]

    logger.info(f"vocab header fix: score {old_score}\u2192{len(found)}, header {header[:3]}\u2192{new_header[:3]}")

    result = [new_header] + table[1:]
    return result


def detect_header_index(rows: list[list[str]], *, categories: list[str] | None = None) -> int:
    """Return header row index or -1 if not found."""
    cats = categories or ["BANK_STATEMENT"]
    header_row_idx = -1
    best_vocab_score = 0
    for i, row in enumerate(rows[:10]):
        vs = _score_header_by_vocabulary(row, categories=cats)
        if vs > best_vocab_score:
            best_vocab_score = vs
            header_row_idx = i
    if best_vocab_score < 3:
        header_row_idx = -1
        for i, row in enumerate(rows[:5]):
            if _is_header_row(row):
                header_row_idx = i
                break
        if header_row_idx == -1:
            for i, row in enumerate(rows[1:6], 1):
                if _is_data_row(row):
                    return 0
            return -1
    return header_row_idx


def _merge_multirow_header(header: list[str], data_rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Merge sub-header row that fills empty parent header cells."""
    if not data_rows:
        return header, data_rows
    candidate = data_rows[0]
    empty_in_header = {i for i, c in enumerate(header) if not (c or "").strip()}
    filled_in_candidate = {i for i, c in enumerate(candidate) if i < len(candidate) and (c or "").strip()}
    fills_empty = filled_in_candidate & empty_in_header
    candidate_is_header_like = _is_header_row(candidate) or _score_header_by_vocabulary(candidate) >= 1
    if fills_empty and candidate_is_header_like and not _is_data_row(candidate):
        merged_header = list(header)
        for i in filled_in_candidate:
            if i < len(merged_header):
                merged_header[i] = (candidate[i] or "").strip()
        logger.info(
            f"multi-row header merge: {len(fills_empty)} gap-fills + "
            f"{len(filled_in_candidate - empty_in_header)} span-refinements"
        )
        return merged_header, data_rows[1:]
    return header, data_rows


def run_header_stage(
    rows: list[list[str]],
    *,
    confirmed_header: list[str] | None = None,
) -> tuple[list[list[str]], dict[str, str], list[str] | None]:
    """Header detection + preamble KV (structure/clean in monolith orchestrator)."""
    if not rows or len(rows) < 2:
        return rows, {}, confirmed_header

    rows = normalize_table_rows([list(r) for r in rows])
    if confirmed_header:
        rows = _strip_preamble(rows, confirmed_header)
        if not rows:
            return [], {}, confirmed_header

    header_row_idx = detect_header_index(rows)
    if header_row_idx == -1:
        return rows, {}, None

    preamble_kv: dict[str, str] = {}
    if header_row_idx > 0:
        preamble_kv = _extract_preamble_kv(rows[:header_row_idx])
        if preamble_kv:
            logger.debug(f"preamble KV extracted: {preamble_kv}")

    header = rows[header_row_idx]
    data_rows = list(rows[header_row_idx + 1 :])
    header, data_rows = _merge_multirow_header(header, data_rows)
    data_rows = _strip_preamble(data_rows, header)

    try:
        preliminary = _fix_header_by_vocabulary([header] + data_rows)
        header = preliminary[0]
        data_rows = preliminary[1:]
    except Exception as e:
        logger.debug(f"header fix rollback: {e}")

    return [header] + data_rows, preamble_kv, header


def run(ctx: Any, rows: list[list[str]]) -> tuple[list[list[str]], dict[str, str]]:
    """TNP header stage entrypoint."""
    confirmed = getattr(ctx, "confirmed_header", None)
    out, kv, _ = run_header_stage(rows, confirmed_header=confirmed)
    return out, kv


__all__ = [
    "_find_vocab_words_in_string",
    "_fix_header_by_vocabulary",
    "detect_header_index",
    "run",
    "run_header_stage",
]
