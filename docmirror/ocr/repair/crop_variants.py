# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Crop variant generation for local OCR repair."""

from __future__ import annotations

from collections.abc import Iterable


def bbox_to_image_region(
    bbox: tuple[float, float, float, float],
    *,
    page_width: float,
    page_height: float,
    image_width: int,
    image_height: int,
    pad_px: int = 0,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    sx = image_width / max(page_width, 1.0)
    sy = image_height / max(page_height, 1.0)
    ix0 = max(0, int(round(x0 * sx)) - pad_px)
    iy0 = max(0, int(round(y0 * sy)) - pad_px)
    ix1 = min(image_width, int(round(x1 * sx)) + pad_px)
    iy1 = min(image_height, int(round(y1 * sy)) + pad_px)
    return ix0, iy0, ix1, iy1


def crop_regions(
    bbox: tuple[float, float, float, float],
    *,
    page_width: float,
    page_height: float,
    image_width: int,
    image_height: int,
    pads_px: Iterable[int] = (0, 4, 8, 14),
    vertical_shifts_px: Iterable[int] = (0, -4, 4),
) -> list[dict[str, object]]:
    """Return deterministic crop variants around a PDF-space bbox."""
    base = bbox_to_image_region(
        bbox,
        page_width=page_width,
        page_height=page_height,
        image_width=image_width,
        image_height=image_height,
    )
    regions: list[dict[str, object]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for pad in pads_px:
        for shift in vertical_shifts_px:
            x0 = max(0, base[0] - int(pad))
            y0 = max(0, base[1] - int(pad) + int(shift))
            x1 = min(image_width, base[2] + int(pad))
            y1 = min(image_height, base[3] + int(pad) + int(shift))
            region = (x0, y0, x1, y1)
            if x1 - x0 < 3 or y1 - y0 < 3 or region in seen:
                continue
            seen.add(region)
            regions.append({"region": region, "pad_px": int(pad), "vertical_shift_px": int(shift)})
    return regions


__all__ = ["bbox_to_image_region", "crop_regions"]
