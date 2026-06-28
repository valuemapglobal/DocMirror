# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Table pipeline preamble stage — strip summary rows before header.

Purpose: Extracts preamble KV entities and strips non-data rows above the
detected header row.

Main components: ``run`` (preamble stage), ``_extract_preamble_kv``,
``_strip_preamble``.

Upstream: Raw table with summary header bands.

Downstream: ``stage_header``, ``table.pipeline.kv_summary``.
"""

from __future__ import annotations

import logging
import re

from docmirror.structure.utils.vocabulary import (
    _RE_IS_AMOUNT,
    _RE_IS_DATE,
    _is_data_row,
    _normalize_for_vocab,
    _score_header_by_vocabulary,
)

logger = logging.getLogger(__name__)


def _extract_preamble_kv(rows: list[list[str]]) -> dict[str, str]:
    """Extract key-value metadata pairs from pre-header rows.

    Rule: adjacent non-empty cells matching a (CJK label, numeric/date value)
    pattern are extracted as KV pairs.  ``None`` cells are skipped first to
    produce a compact cell list.
    """
    kv: dict[str, str] = {}
    for row in rows:
        # Filter out None / whitespace to get a compact non-empty cell list
        cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
        i = 0
        while i < len(cells) - 1:
            key = cells[i]
            val = cells[i + 1]
            # key: non-empty, contains CJK, not a pure number / date
            # val: non-empty, is an amount / date / pure number
            if (
                key
                and val
                and re.search(r"[\u4e00-\u9fff]", key)
                and not _RE_IS_DATE.match(key)
                and not _RE_IS_AMOUNT.match(key.replace(",", ""))
            ):
                clean_val = val.replace(",", "").replace("\u00a5", "").replace(" ", "")
                is_num_or_date = bool(
                    _RE_IS_DATE.search(val) or (_RE_IS_AMOUNT.match(clean_val) if clean_val else False)
                )
                if is_num_or_date:
                    kv[key] = val
                    i += 2  # Skip the value cell
                    continue
            i += 1
    return kv


def _strip_preamble(
    rows: list[list[str]],
    confirmed_header: list[str],
    categories: list[str] | None = None,
) -> list[list[str]]:
    """Strip duplicate summary rows and repeated headers from the beginning
    of a continuation-page table.

    Args:
        rows: Rows to filter.
        confirmed_header: The confirmed header row.
        categories: Vocabulary categories for matching; defaults to ``["BANK_STATEMENT"]``.
    """
    if not confirmed_header or not rows:
        return rows

    # Non-empty cells of the confirmed header (normalised)
    header_cells = {_normalize_for_vocab(c).strip() for c in confirmed_header if c and c.strip()}

    if not categories:
        categories = ["BANK_STATEMENT"]

    max_scan = min(10, len(rows))

    # Two-phase scan:
    # Phase 1: scan the first max_scan rows; find the last row with vocab_score >= 3
    #          (duplicate header row)
    last_header_idx = -1
    for i in range(max_scan):
        vs = _score_header_by_vocabulary(rows[i], categories=categories)
        if vs >= 3:
            last_header_idx = i

    if last_header_idx >= 0:
        # F-7: strip protection — cap at 5 rows to avoid data loss
        if last_header_idx > 5:
            logger.warning(
                f"strip_preamble: vocab header at row {last_header_idx} (> 5 rows) \u2014 capping to avoid data loss"
            )
            last_header_idx = 5
        logger.debug(f"strip_preamble: skip rows 0-{last_header_idx} (vocab repeated header at row {last_header_idx})")
        return rows[last_header_idx + 1 :]

    # Phase 2: no duplicate header found; try header-similarity matching
    for i in range(max_scan):
        row = rows[i]
        norm_cells = {_normalize_for_vocab(c).strip() for c in row if c and c.strip()}
        if header_cells and norm_cells:
            overlap = len(norm_cells & header_cells) / len(header_cells)
            if overlap >= 0.5:
                logger.debug(f"strip_preamble: skip rows 0-{i} (header overlap={overlap:.2f})")
                return rows[i + 1 :]
        # Stop similarity detection once a real data row is encountered
        if _is_data_row(row):
            break

    return rows


def run(ctx, rows, preamble_kv):  # noqa: ANN001
    """Preamble stage hook — KV already extracted in header stage for monolith path."""
    _ = ctx
    return rows, preamble_kv


__all__ = ["_extract_preamble_kv", "_strip_preamble", "run"]
