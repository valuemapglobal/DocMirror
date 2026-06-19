# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small bbox primitives using PDF point coordinates."""

from __future__ import annotations

from typing import Iterable, Sequence

BBox = tuple[float, float, float, float]


def normalize(bbox: Sequence[float] | None) -> BBox | None:
    """Return ``(x0, y0, x1, y1)`` with sorted edges, or ``None``."""
    if not bbox or len(bbox) < 4:
        return None
    x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def area(bbox: Sequence[float] | None) -> float:
    b = normalize(bbox)
    if b is None:
        return 0.0
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def center(bbox: Sequence[float] | None) -> tuple[float, float] | None:
    b = normalize(bbox)
    if b is None:
        return None
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def union(boxes: Iterable[Sequence[float] | None]) -> BBox | None:
    valid = [b for b in (normalize(box) for box in boxes) if b is not None and area(b) > 0]
    if not valid:
        return None
    return (
        min(b[0] for b in valid),
        min(b[1] for b in valid),
        max(b[2] for b in valid),
        max(b[3] for b in valid),
    )


def intersection(a: Sequence[float] | None, b: Sequence[float] | None) -> BBox | None:
    aa = normalize(a)
    bb = normalize(b)
    if aa is None or bb is None:
        return None
    out = (max(aa[0], bb[0]), max(aa[1], bb[1]), min(aa[2], bb[2]), min(aa[3], bb[3]))
    return out if area(out) > 0 else None


def iou(a: Sequence[float] | None, b: Sequence[float] | None) -> float:
    inter = intersection(a, b)
    inter_area = area(inter)
    if inter_area <= 0:
        return 0.0
    denom = area(a) + area(b) - inter_area
    return inter_area / denom if denom > 0 else 0.0


def contains(outer: Sequence[float] | None, inner: Sequence[float] | None, *, tolerance: float = 1.0) -> bool:
    o = normalize(outer)
    i = normalize(inner)
    if o is None or i is None:
        return False
    return (
        o[0] - tolerance <= i[0]
        and o[1] - tolerance <= i[1]
        and o[2] + tolerance >= i[2]
        and o[3] + tolerance >= i[3]
    )
