# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic candidate detection for scanned micro-grids."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from docmirror.structure.ocr.micro_grid.models import BBox, MicroGridCandidate, OCRToken

_ANCHOR_HINTS = ("记录", "明细", "情况", "状态")


def _bbox(obj: Any) -> BBox | None:
    raw = obj.get("bbox") if isinstance(obj, dict) else getattr(obj, "bbox", None)
    if raw and len(raw) == 4:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    return None


def _text(obj: Any) -> str:
    return str(obj.get("content") if isinstance(obj, dict) else getattr(obj, "text", "") or "").strip()


def _union_bbox(boxes: Iterable[BBox]) -> BBox:
    vals = list(boxes)
    return (
        min(b[0] for b in vals),
        min(b[1] for b in vals),
        max(b[2] for b in vals),
        max(b[3] for b in vals),
    )


def detect_micro_grid_candidates(
    tokens: Iterable[OCRToken] | None = None,
    *,
    lines: Iterable[Any] | None = None,
    page: int,
    page_width: float | None = None,
    page_height: float | None = None,
) -> list[MicroGridCandidate]:
    """Detect local regions that may contain small OCR grids.

    This detector is intentionally weak and generic: it emits candidates and
    reason codes only. Domain code decides whether a candidate maps to a
    concrete schema.
    """
    token_list = list(tokens or [])
    line_list = list(lines or [])
    candidates: list[MicroGridCandidate] = []

    for idx, line in enumerate(line_list):
        text = _text(line)
        bbox = _bbox(line)
        if not text or bbox is None:
            continue
        if not any(hint in text for hint in _ANCHOR_HINTS):
            continue

        x0, y0, x1, y1 = bbox
        roi_bottom = min(page_height or y1 + 180.0, y1 + 180.0)
        nearby_tokens = [
            token
            for token in token_list
            if y1 <= token.center[1] <= roi_bottom and x0 - 260.0 <= token.center[0] <= x1 + 360.0
        ]
        reason_codes = ["anchor_text"]
        score = 0.35
        if "记录" in text:
            reason_codes.append("anchor_temporal_record")
            score += 0.25
        short_tokens = [t for t in nearby_tokens if 1 <= len(t.text.strip()) <= 3]
        if len(short_tokens) >= 6:
            reason_codes.append("small_token_density")
            score += 0.20
        digitish = [t for t in nearby_tokens if any(ch.isdigit() for ch in t.text)]
        if len(digitish) >= 4:
            reason_codes.append("numeric_header_or_cells")
            score += 0.10

        boxes = [bbox] + [t.bbox for t in nearby_tokens]
        roi = _union_bbox(boxes) if nearby_tokens else (x0, y0, x1, roi_bottom)
        if page_width is not None:
            roi = (max(0.0, roi[0]), roi[1], min(page_width, roi[2]), roi[3])

        candidates.append(
            MicroGridCandidate(
                candidate_id=f"mgcand_p{page}_{idx}",
                page=page,
                bbox=roi,
                anchors=(text,),
                reason_codes=tuple(reason_codes),
                score=min(score, 1.0),
            )
        )

    return sorted(candidates, key=lambda c: c.score, reverse=True)
