# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin-supplemental local structure candidate detectors."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from docmirror.ocr.local_structure.models import LocalStructureCandidate
from docmirror.ocr.micro_grid.models import OCRToken

SupplementDetector = Callable[
    ...,
    list[LocalStructureCandidate],
]

_SUPPLEMENT_DETECTORS: list[SupplementDetector] = []
_LOADED = False


def register_local_structure_supplement(detector: SupplementDetector) -> SupplementDetector:
    if detector not in _SUPPLEMENT_DETECTORS:
        _SUPPLEMENT_DETECTORS.append(detector)
    return detector


def _ensure_supplements_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from docmirror.layout.segment.page_blocks import detect_pre_grid_field_supplements

    register_local_structure_supplement(detect_pre_grid_field_supplements)


def supplement_local_structure_candidates(
    items: list[dict[str, Any]],
    *,
    tokens: Iterable[OCRToken] | None = None,
    page: int,
    page_width: float | None = None,
    page_height: float | None = None,
    existing: Iterable[LocalStructureCandidate] | None = None,
) -> list[LocalStructureCandidate]:
    """Return additional candidates from registered domain supplements."""
    _ensure_supplements_loaded()
    if not _SUPPLEMENT_DETECTORS:
        return []
    existing_list = list(existing or [])
    extra: list[LocalStructureCandidate] = []
    for detector in _SUPPLEMENT_DETECTORS:
        try:
            found = detector(
                items,
                tokens=tokens,
                page=page,
                page_width=page_width,
                page_height=page_height,
                existing=existing_list,
            )
        except Exception:
            continue
        extra.extend(found or [])
    if not extra:
        return []
    merged = list(existing_list)
    for cand in extra:
        if any(_overlaps(existing.bbox, cand.bbox) for existing in merged):
            continue
        merged.append(cand)
    return merged[len(existing_list) :]


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return False
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(a[2] - a[0], 0.0) * max(a[3] - a[1], 0.0)
    area_b = max(b[2] - b[0], 0.0) * max(b[3] - b[1], 0.0)
    base = min(area_a, area_b)
    return base > 0 and inter / base >= 0.55
