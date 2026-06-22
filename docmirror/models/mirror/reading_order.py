# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ReadingOrderResolver — column-aware document reading order.

Strategies:
  - physical_order_preserve: prefer extractor's explicit reading_order
  - column_aware_bbox_order: detect column zones, order within columns
  - page_canvas_block_order: use PageCanvas/UBI unified page nodes
  - section_aware_order: order by structure context (heading, body, table, caption)
  - model_rerank_order: P1 model-assisted reranking for complex layouts
"""

from __future__ import annotations

from typing import Any


def resolve_reading_order(
    page_items: list[dict[str, Any]],
    *,
    layout_zones: list[dict[str, Any]] | None = None,
    strategy: str = "physical_order_preserve",
) -> list[dict[str, Any]]:
    """Resolve reading order for a page's items.

    Args:
        page_items: List of page item dicts with at least ``reading_order``, ``bbox`` keys.
        layout_zones: Optional column/region zones from layout analysis.
        strategy: Ordering strategy name.

    Returns:
        Items sorted by resolved reading order.
    """
    if strategy == "physical_order_preserve":
        # Sort by explicit reading_order, then by type priority
        return sorted(page_items, key=_order_key)

    if strategy == "column_aware_bbox_order" and layout_zones:
        return _column_aware_sort(page_items, layout_zones)

    if strategy == "page_canvas_block_order":
        # Use PageCanvas block order if available
        return sorted(page_items, key=lambda x: (
            int(x.get("page_canvas_order", 0) or 0),
            _type_priority(x),
        ))

    # Fallback: simple bbox-based top-left order
    return sorted(page_items, key=lambda x: (
        _bbox_top(x.get("bbox")),
        _bbox_left(x.get("bbox")),
    ))


def _order_key(item: dict[str, Any]) -> tuple[int, int]:
    """Sort key: explicit reading_order first, then type priority."""
    ro = int(item.get("reading_order", 0) or 0)
    tp = _type_priority(item)
    return (ro, tp)


def _type_priority(item: dict[str, Any]) -> int:
    """Type priority for stable sorting within same reading_order."""
    item_type = str(item.get("type") or item.get("item_type") or "text")
    priorities = {
        "text": 0,
        "heading": 1,
        "paragraph": 2,
        "list_item": 3,
        "key_value": 4,
        "image": 5,
        "caption": 6,
        "formula": 7,
        "table": 8,
        "physical_table": 9,
        "logical_table": 10,
        "header": 11,
        "footer": 12,
        "watermark": 13,
    }
    return priorities.get(item_type, 100)


def _bbox_top(bbox: Any) -> float:
    """Extract top coordinate from bbox [x0, y0, x1, y1]."""
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 2:
        return float(bbox[1])
    return 0.0


def _bbox_left(bbox: Any) -> float:
    """Extract left coordinate from bbox [x0, y0, x1, y1]."""
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 1:
        return float(bbox[0])
    return 0.0


def _column_aware_sort(
    items: list[dict[str, Any]],
    zones: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort items respecting column layout.

    Detects which column each item belongs to, then orders top-down
    within columns and left-to-right across columns.
    """
    # Simply assign items to nearest column zone and sort within each column
    columns: list[list[dict[str, Any]]] = []
    for zone in zones:
        col_items = []
        zx0 = float((zone.get("bbox") or [0, 0, 0, 0])[0])
        zx1 = float((zone.get("bbox") or [0, 0, 0, 0])[2])
        for item in items:
            bbox = item.get("bbox")
            if bbox and len(bbox) >= 2:
                ix = float(bbox[0])
                if zx0 <= ix <= zx1:
                    col_items.append(item)
        col_items.sort(key=lambda x: _bbox_top(x.get("bbox")))
        columns.append(col_items)

    # If no columns defined, fall back to top-left sort
    if not columns:
        return sorted(items, key=lambda x: (_bbox_top(x.get("bbox")), _bbox_left(x.get("bbox"))))

    # Interleave columns top-down (simple strategy: column 0 first, then column 1)
    result: list[dict[str, Any]] = []
    for col in columns:
        result.extend(col)
    return result


__all__ = [
    "resolve_reading_order",
]
