# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OCR token splitting and deduplication for field-grid assignment."""

from __future__ import annotations

from collections.abc import Iterable

from docmirror.structure.ocr.field_grid.geometry import bbox_area, bbox_iou
from docmirror.structure.ocr.micro_grid.models import OCRToken


def _source_priority(token: OCRToken) -> int:
    source = token.source.lower()
    if "line_split" in source:
        return 30
    if "char_split" in source:
        return 80
    if token.source_token_id is None and len(token.text.strip()) == 1:
        return 100
    return 60


def split_token_to_char_tokens(token: OCRToken) -> list[OCRToken]:
    chars = [ch for ch in token.text if not ch.isspace()]
    if len(chars) <= 1:
        return [token]
    x0, y0, x1, y1 = token.bbox
    step = max(x1 - x0, 1.0) / len(chars)
    out: list[OCRToken] = []
    for idx, ch in enumerate(chars):
        out.append(
            OCRToken(
                token_id=f"{token.token_id}_c{idx}",
                text=ch,
                bbox=(x0 + step * idx, y0, x0 + step * (idx + 1), y1),
                confidence=token.confidence,
                page=token.page,
                source=f"{token.source}_char_split",
                coordinate_system=token.coordinate_system,
                raw_bbox=token.raw_bbox,
                raw_coordinate_system=token.raw_coordinate_system,
                source_token_id=token.token_id,
            )
        )
    return out


def expand_tokens_to_char_tokens(tokens: Iterable[OCRToken]) -> list[OCRToken]:
    chars: list[OCRToken] = []
    for token in tokens:
        chars.extend(split_token_to_char_tokens(token))
    return dedupe_visual_tokens(chars)


def dedupe_visual_tokens(tokens: Iterable[OCRToken], *, iou_threshold: float = 0.62) -> list[OCRToken]:
    ordered = sorted(
        list(tokens),
        key=lambda t: (-_source_priority(t), -t.confidence, bbox_area(t.bbox), t.bbox[1], t.bbox[0]),
    )
    kept: list[OCRToken] = []
    for token in ordered:
        text = token.text.strip()
        if not text:
            continue
        duplicate = False
        for existing in kept:
            if existing.text.strip() != text:
                continue
            if bbox_iou(existing.bbox, token.bbox) >= iou_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(token)
    return sorted(kept, key=lambda t: (t.bbox[1], t.bbox[0], t.token_id))
