# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build reusable OCR evidence for one normalized logical scan page.

The vNext PDF path already owns the upright logical-page image and the OCR
blocks at this point.  Materializing the generic evidence bundle here avoids a
second OCR pass and preserves the text that may later be absorbed by physical
table blocks.
"""

from __future__ import annotations

import statistics
from typing import Any


def _block_token(block: Any, *, page: int, index: int) -> dict[str, Any] | None:
    text = str(getattr(block, "raw_content", "") or "").strip()
    bbox = getattr(block, "bbox", None)
    if not text or not bbox or len(bbox) != 4:
        return None
    attrs = dict(getattr(block, "attrs", None) or {})
    raw_confidence = attrs.get("confidence", attrs.get("extraction_confidence", 0.0))
    try:
        confidence = max(0.0, min(1.0, float(raw_confidence)))
    except (TypeError, ValueError):
        confidence = 0.0
    evidence_ids = list(getattr(block, "evidence_ids", ()) or ())
    token_id = str(evidence_ids[0] if evidence_ids else getattr(block, "block_id", "") or f"ocr:p{page}:t{index}")
    return {
        "token_id": token_id,
        "content": text,
        "text": text,
        "bbox": [round(float(value), 4) for value in bbox],
        "confidence": round(confidence, 4),
        "page": page,
        "source": str(attrs.get("ocr_source") or "rapidocr_pdf_logical_page"),
        "evidence_ids": evidence_ids or [token_id],
    }


def _group_tokens_into_lines(tokens: list[dict[str, Any]], *, page: int) -> list[dict[str, Any]]:
    if not tokens:
        return []
    heights = [max(1.0, float(token["bbox"][3]) - float(token["bbox"][1])) for token in tokens]
    tolerance = max(3.0, min(8.0, statistics.median(heights) * 0.55))
    ordered = sorted(
        tokens, key=lambda token: ((float(token["bbox"][1]) + float(token["bbox"][3])) / 2.0, float(token["bbox"][0]))
    )
    rows: list[list[dict[str, Any]]] = []
    centers: list[float] = []
    for token in ordered:
        center_y = (float(token["bbox"][1]) + float(token["bbox"][3])) / 2.0
        row_index = next(
            (index for index, row_center in enumerate(centers) if abs(center_y - row_center) <= tolerance),
            None,
        )
        if row_index is None:
            rows.append([token])
            centers.append(center_y)
            continue
        rows[row_index].append(token)
        centers[row_index] = sum(
            (float(item["bbox"][1]) + float(item["bbox"][3])) / 2.0 for item in rows[row_index]
        ) / len(rows[row_index])

    lines: list[dict[str, Any]] = []
    for index, row in enumerate(sorted(rows, key=lambda value: min(float(item["bbox"][1]) for item in value))):
        row = sorted(row, key=lambda token: float(token["bbox"][0]))
        evidence_ids = [
            str(evidence_id)
            for token in row
            for evidence_id in (token.get("evidence_ids") or [token.get("token_id")])
            if evidence_id
        ]
        weights = [max(1, len(str(token.get("text") or ""))) for token in row]
        confidence = sum(float(token.get("confidence") or 0.0) * weight for token, weight in zip(row, weights)) / sum(
            weights
        )
        lines.append(
            {
                "line_id": f"ocr:p{page:04d}:line:{index:04d}",
                "content": " ".join(str(token.get("text") or "").strip() for token in row).strip(),
                "text": " ".join(str(token.get("text") or "").strip() for token in row).strip(),
                "bbox": [
                    min(float(token["bbox"][0]) for token in row),
                    min(float(token["bbox"][1]) for token in row),
                    max(float(token["bbox"][2]) for token in row),
                    max(float(token["bbox"][3]) for token in row),
                ],
                "confidence": round(confidence, 4),
                "page": page,
                "source": "rapidocr_pdf_logical_page",
                "evidence_ids": list(dict.fromkeys(evidence_ids)),
                "token_ids": [str(token["token_id"]) for token in row],
            }
        )
    return lines


def build_scanned_page_evidence_bundle(
    blocks: list[Any],
    *,
    page: int,
    source_page: int,
    page_width: float,
    page_height: float,
    page_image: Any | None = None,
) -> dict[str, Any]:
    """Return the canonical runtime evidence bundle for one logical page."""
    tokens = [
        token
        for index, block in enumerate(blocks)
        if (token := _block_token(block, page=page, index=index)) is not None
    ]
    lines = _group_tokens_into_lines(tokens, page=page)

    from docmirror.ocr.local_structure import extract_local_structure_evidence

    local = extract_local_structure_evidence(
        lines,
        tokens=tokens,
        page=page,
        page_width=page_width,
        page_height=page_height,
        page_image=page_image,
        enable_region_ocr=False,
    )
    local_evidence = {
        "page": page,
        "source_page": source_page,
        "page_width": page_width,
        "page_height": page_height,
        "source": "rapidocr_pdf_logical_page",
        "lines": lines,
        "tokens": tokens,
        "candidates": list(local.get("candidates") or []),
        "structures": list(local.get("structures") or []),
    }

    # Persist raw micro-grid evidence even if no materializer is currently
    # registered.  The credit-report plugin can materialize it after document
    # classification without OCRing the page again.
    micro_grid_evidence = {
        "page": page,
        "source_page": source_page,
        "page_width": page_width,
        "page_height": page_height,
        "source": "rapidocr_pdf_logical_page",
        "lines": lines,
        "tokens": tokens,
    }
    return {
        "page": page,
        "source_page_number": source_page,
        "page_width": page_width,
        "page_height": page_height,
        "source": "rapidocr_pdf_logical_page",
        "tokens": tokens,
        "local_structure_evidence": local_evidence,
        "micro_grid_evidence": micro_grid_evidence,
    }


__all__ = ["build_scanned_page_evidence_bundle"]
