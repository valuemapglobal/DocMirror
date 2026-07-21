# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Cell normalizer — cleans and normalizes table cell text.

Purpose: Strips noise, normalizes ID-like cells, and batch-normalizes table
cell matrices after extraction.

Main components: ``normalize_cell_text``, ``normalize_table_cells``.

Upstream: Raw table grids from any extract backend.

Downstream: ``table.pipeline.stage_structure``, ``table.table_structure_fix``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docmirror.models.entities.extraction_profile import ExtractionProfile

_RE_MULTI_SPACE = re.compile(r" +")
_RE_ID_LIKE = re.compile(r"^[A-Za-z0-9\-_]{8,}$")
_RE_DATE_TIME_LINES = re.compile(r"^\s*((?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2})\s*\n\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*$")


def _is_id_like_cell(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 10:
        return False
    if _RE_ID_LIKE.match(compact):
        return True
    digit_ratio = sum(c.isdigit() for c in compact) / max(len(compact), 1)
    return digit_ratio > 0.5 and len(compact) >= 12


def normalize_cell_line_breaks(text: str) -> str:
    """Remove visual line wrapping without corrupting IDs or datetimes."""
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in value:
        return value
    datetime_match = _RE_DATE_TIME_LINES.fullmatch(value)
    if datetime_match:
        return f"{datetime_match.group(1)} {datetime_match.group(2)}"
    compact = re.sub(r"\s+", "", value)
    if _is_id_like_cell(compact):
        return compact
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return ""
    joined = lines[0]
    for line in lines[1:]:
        cjk_boundary = bool(re.search(r"[\u3400-\u9fff]$", joined) and re.match(r"^[\u3400-\u9fff]", line))
        joined += ("" if cjk_boundary else " ") + line
    return joined


def normalize_cell_text(
    text: str,
    *,
    profile: ExtractionProfile | None = None,
) -> str:
    """Normalize a single cell according to profile policy."""
    if not text:
        return ""
    s = str(text)
    if profile and profile.normalize_intracellular_newlines:
        s = normalize_cell_line_breaks(s)
    if profile and profile.collapse_duplicate_spaces:
        s = _RE_MULTI_SPACE.sub(" ", s.strip())
    return s


def normalize_table_cells(
    tables: list[list[list[str]]],
    profile: ExtractionProfile | None = None,
) -> list[list[list[str]]]:
    """Apply cell normalization to all tables in-place copy."""
    if not profile or not (profile.normalize_intracellular_newlines or profile.collapse_duplicate_spaces):
        return tables
    out: list[list[list[str]]] = []
    for tbl in tables:
        if not tbl:
            out.append(tbl)
            continue
        normalized = [[normalize_cell_text(cell, profile=profile) for cell in row] for row in tbl]
        out.append(normalized)
    return out
