# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from docmirror.ocr.micro_grid.models import OCRToken
from docmirror.ocr.scanned.universal import ocr_extract_universal


def scaled_tokens(raw_tokens: list[dict[str, Any]] | None, *, page_number: int, sx: float, sy: float) -> list[OCRToken]:
    out: list[OCRToken] = []
    for idx, token in enumerate(raw_tokens or []):
        bbox = token.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        text = str(token.get("text") or "").strip()
        if not text:
            continue
        x0, y0, x1, y1 = [float(v) for v in bbox]
        raw_bbox = token.get("raw_bbox") or bbox
        out.append(
            OCRToken(
                token_id=str(token.get("token_id") or f"ocr_p{page_number}_t{idx}"),
                text=text,
                bbox=(x0 * sx, y0 * sy, x1 * sx, y1 * sy),
                confidence=float(token.get("confidence", 1.0) or 1.0),
                page=page_number,
                source=str(token.get("source", "rapidocr")),
                raw_bbox=tuple(float(v) for v in raw_bbox),
            )
        )
    return out


def ocr_page_as_pdf_points(page: Any, page_index: int) -> tuple[dict[str, Any], list[dict[str, Any]], list[OCRToken]]:
    ocr = ocr_extract_universal(page, page_index)
    if not ocr or ocr.get("content_type") != "general":
        return ocr or {}, [], []

    sx = page.rect.width / max(float(ocr.get("page_w") or 1), 1.0)
    sy = page.rect.height / max(float(ocr.get("page_h") or 1), 1.0)
    lines: list[dict[str, Any]] = []
    for line in ocr.get("lines") or []:
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        x0, y0, x1, y1 = [float(v) for v in line.get("bbox", (0, 0, 0, 0))]
        lines.append(
            {
                "content": text,
                "bbox": [x0 * sx, y0 * sy, x1 * sx, y1 * sy],
                "confidence": float(line.get("confidence", 1.0) or 1.0),
            }
        )
    return ocr, lines, scaled_tokens(ocr.get("tokens"), page_number=page_index + 1, sx=sx, sy=sy)
