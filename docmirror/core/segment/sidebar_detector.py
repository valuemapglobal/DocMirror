# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Sidebar zone detection — keep legal/disclaimer columns out of table extraction."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_SIDEBAR_KEYWORDS = (
    "说明",
    "声明",
    "本证明",
    "仅供参考",
    "财付通",
    "微信支付",
    "隐私",
    "法律效力",
)


def sidebar_x_cutoff(page_width: float, sidebar_x_ratio: float | None) -> float | None:
    """Return x coordinate separating main content from sidebar."""
    if sidebar_x_ratio is None or page_width <= 0:
        return None
    return page_width * sidebar_x_ratio


def crop_bbox_for_table_zone(
    bbox: tuple[float, float, float, float],
    page_width: float,
    sidebar_x_ratio: float | None,
) -> tuple[float, float, float, float]:
    """Crop table zone bbox to exclude right sidebar column."""
    cutoff = sidebar_x_cutoff(page_width, sidebar_x_ratio)
    if cutoff is None:
        return bbox
    x0, y0, x1, y1 = bbox
    if x0 >= cutoff:
        return bbox
    return (x0, y0, min(x1, cutoff), y1)


def extract_sidebar_text_blocks(
    page_plum,
    sidebar_x_ratio: float | None,
    page_idx: int = 0,
) -> list[dict[str, Any]]:
    """Extract chars in sidebar region as mirror text blocks."""
    if sidebar_x_ratio is None:
        return []

    page_w = getattr(page_plum, "width", 0) or 0
    cutoff = sidebar_x_cutoff(page_w, sidebar_x_ratio)
    if cutoff is None:
        return []

    chars = getattr(page_plum, "chars", []) or []
    sidebar_chars = [c for c in chars if c.get("x0", 0) >= cutoff - 2]
    if not sidebar_chars:
        return []

    lines: dict[int, list[str]] = {}
    for c in sidebar_chars:
        top = int(round(c.get("top", 0)))
        lines.setdefault(top, []).append(c.get("text", ""))

    blocks: list[dict[str, Any]] = []
    for top in sorted(lines.keys()):
        text = "".join(lines[top]).strip()
        if len(text) < 4:
            continue
        blocks.append(
            {
                "text": text,
                "mirror_role": "legal_sidebar",
                "page": page_idx + 1,
                "reading_order": top,
                "bbox": (cutoff, top, page_w, top + 12),
            }
        )
    return blocks


def is_likely_sidebar_cell(cell_text: str) -> bool:
    """Heuristic: cell content looks like sidebar legal text."""
    t = (cell_text or "").strip()
    if len(t) < 12:
        return False
    keyword_hits = sum(1 for kw in _SIDEBAR_KEYWORDS if kw in t)
    if keyword_hits >= 2:
        return True
    return keyword_hits >= 1 and len(t) > 24


def filter_sidebar_rows_from_table(rows: list[list[str]]) -> list[list[str]]:
    """Remove rows dominated by sidebar legal text."""
    if not rows:
        return rows
    filtered = []
    for row in rows:
        if not row:
            continue
        joined = " ".join(str(c) for c in row if c)
        if is_likely_sidebar_cell(joined):
            continue
        filtered.append(row)
    return filtered if filtered else rows
