# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Cell normalization pipeline for extract-layer table fidelity."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docmirror.models.entities.extraction_profile import ExtractionProfile

_RE_MULTI_SPACE = re.compile(r" +")
_RE_ID_LIKE = re.compile(r"^[A-Za-z0-9\-_]{8,}$")


def _is_id_like_cell(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 10:
        return False
    if _RE_ID_LIKE.match(compact):
        return True
    digit_ratio = sum(c.isdigit() for c in compact) / max(len(compact), 1)
    return digit_ratio > 0.5 and len(compact) >= 12


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
        if _is_id_like_cell(s.replace("\n", "").replace(" ", "")):
            s = re.sub(r"\s+", "", s)
        else:
            s = s.replace("\n", " ")
    if profile and profile.collapse_duplicate_spaces:
        s = _RE_MULTI_SPACE.sub(" ", s.strip())
    return s


def normalize_table_cells(
    tables: list[list[list[str]]],
    profile: ExtractionProfile | None = None,
) -> list[list[list[str]]]:
    """Apply cell normalization to all tables in-place copy."""
    if not profile or not (
        profile.normalize_intracellular_newlines or profile.collapse_duplicate_spaces
    ):
        return tables
    out: list[list[list[str]]] = []
    for tbl in tables:
        if not tbl:
            out.append(tbl)
            continue
        normalized = [
            [normalize_cell_text(cell, profile=profile) for cell in row]
            for row in tbl
        ]
        out.append(normalized)
    return out
