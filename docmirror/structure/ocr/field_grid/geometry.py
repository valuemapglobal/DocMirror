# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""BBox geometry helpers shared by field-grid reconstruction."""

from __future__ import annotations

from docmirror.structure.ocr.micro_grid.models import BBox


def bbox_area(bbox: BBox) -> float:
    x0, y0, x1, y1 = bbox
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def bbox_intersection(a: BBox, b: BBox) -> BBox | None:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def bbox_overlap_ratio(inner: BBox, outer: BBox) -> float:
    inter = bbox_intersection(inner, outer)
    if inter is None:
        return 0.0
    area = bbox_area(inner)
    if area <= 0.0:
        return 0.0
    return bbox_area(inter) / area


def bbox_iou(a: BBox, b: BBox) -> float:
    inter = bbox_intersection(a, b)
    if inter is None:
        return 0.0
    inter_area = bbox_area(inter)
    denom = bbox_area(a) + bbox_area(b) - inter_area
    return inter_area / denom if denom > 0.0 else 0.0
