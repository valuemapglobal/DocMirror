# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cell-level recognition helpers for scanned micro-grids."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from docmirror.core.ocr.micro_grid.models import BBox


@dataclass(frozen=True)
class CellRecognition:
    text: str
    confidence: float = 0.0
    source: str = "none"
    raw_text: str = ""
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "source": self.source,
            "raw_text": self.raw_text,
            "audit": self.audit,
        }


_CONFUSION_MAP = {
    "Ｏ": "0",
    "O": "0",
    "o": "0",
    "〇": "0",
    "。": "0",
    ".": "0",
    "·": "0",
    "Ｉ": "1",
    "l": "1",
    "|": "1",
    "Ｓ": "5",
    "S": "5",
}


def normalize_allowlist_text(text: str, allowed_charset: Iterable[str], *, max_chars: int | None = None) -> str:
    """Normalize OCR text under a strict allowlist.

    This is intentionally conservative: characters outside the allowlist are
    discarded after a small OCR-confusion normalization pass.
    """
    allowed = set(allowed_charset)
    out: list[str] = []
    for ch in str(text or "").strip():
        normalized = ch if ch in allowed else _CONFUSION_MAP.get(ch, ch)
        if normalized in allowed:
            out.append(normalized)
        if max_chars is not None and len(out) >= max_chars:
            break
    return "".join(out)


def pdf_bbox_to_image_region(
    bbox: BBox,
    *,
    page_width: float,
    page_height: float,
    image_width: int,
    image_height: int,
    pad_px: int = 3,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    sx = image_width / max(page_width, 1.0)
    sy = image_height / max(page_height, 1.0)
    ix0 = max(0, int(round(x0 * sx)) - pad_px)
    iy0 = max(0, int(round(y0 * sy)) - pad_px)
    ix1 = min(image_width, int(round(x1 * sx)) + pad_px)
    iy1 = min(image_height, int(round(y1 * sy)) + pad_px)
    return ix0, iy0, ix1, iy1


def recognize_micro_cell_from_image(
    page_image: Any,
    bbox: BBox,
    *,
    page_width: float,
    page_height: float,
    allowed_charset: Iterable[str],
    max_chars: int | None = None,
    min_confidence: float = 0.35,
) -> CellRecognition:
    """Run OCR on one micro-grid cell crop and filter with an allowlist."""
    shape = getattr(page_image, "shape", None)
    if not shape or len(shape) < 2:
        return CellRecognition("", 0.0, "unavailable", audit={"reason": "missing_page_image"})

    image_height, image_width = int(shape[0]), int(shape[1])
    region = pdf_bbox_to_image_region(
        bbox,
        page_width=page_width,
        page_height=page_height,
        image_width=image_width,
        image_height=image_height,
    )
    if region[2] - region[0] < 3 or region[3] - region[1] < 3:
        return CellRecognition("", 0.0, "unavailable", audit={"reason": "empty_region", "region": region})

    try:
        from docmirror.core.ocr.vision.rapidocr_engine import get_ocr_engine

        engine = get_ocr_engine()
        raw = engine.force_recognize_regions(page_image, [region])
    except Exception as exc:
        return CellRecognition("", 0.0, "cell_crop_ocr_error", audit={"reason": str(exc), "region": region})

    if not raw:
        return CellRecognition("", 0.0, "cell_crop_ocr", audit={"reason": "no_text", "region": region})

    best = max(raw, key=lambda item: float(item[5]) if len(item) > 5 else 0.0)
    raw_text = str(best[4] if len(best) > 4 else "")
    confidence = float(best[5] if len(best) > 5 else 0.0)
    text = normalize_allowlist_text(raw_text, allowed_charset, max_chars=max_chars)
    if confidence < min_confidence or not text:
        return CellRecognition(
            "",
            confidence,
            "cell_crop_ocr",
            raw_text=raw_text,
            audit={"reason": "filtered", "region": region},
        )
    return CellRecognition(
        text,
        confidence,
        "cell_crop_ocr",
        raw_text=raw_text,
        audit={"region": region},
    )
