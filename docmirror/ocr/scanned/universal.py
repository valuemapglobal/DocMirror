# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Universal scanned OCR — generic OCR extraction without table assumptions.

Purpose: Detects table presence, groups OCR words into lines, and extracts
universal text/table content for mixed scanned layouts.

Main components: ``ocr_extract_universal``, ``_group_words_into_lines``.

Upstream: OCR word stream from ``runner``.

Downstream: ``ocr.scanned.analyze_page``, text block assembly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

from docmirror.ocr.micro_grid.models import OCRToken, TieredTokenCollection
from docmirror.ocr.preprocess.pipeline import _render_page_to_bgr
from docmirror.ocr.recognize.runner import _run_ocr
from docmirror.ocr.reconstruct.grid import _detect_table_lines_hough
from docmirror.ocr.scanned.analyze_page import analyze_scanned_page


def _detect_has_table(img, page_h: int) -> bool:
    """Check whether the page image has genuine table line structure.

    Rejects decorative border frames by verifying that detected columns
    have comparable widths (widest / median ≤ 5).
    """
    col_bounds = _detect_table_lines_hough(img, page_h, img.shape[1] if img is not None else 0)
    if not col_bounds or len(col_bounds) < 3:
        return False

    # Reject border-frame false positives: in a real table, columns
    # have roughly comparable widths.  A frame has very narrow border
    # columns flanking one huge content area.
    widths = sorted(b - a for a, b in col_bounds)
    median_w = widths[len(widths) // 2]
    max_w = widths[-1]
    if median_w > 0 and max_w / median_w > 5:
        return False

    return True


def _group_words_into_lines(words: list[tuple], y_tolerance: float = 12.0) -> list[dict]:
    """Group OCR words into text lines by y-proximity.

    Returns a list of line dicts sorted in reading order, each with:
        {"text": str, "bbox": (x0, y0, x1, y1)}
    """
    if not words:
        return []

    # Sort by y, then x
    sorted_w = sorted(words, key=lambda w: (w[1], w[0]))

    lines: list[dict] = []
    cur_words = [sorted_w[0]]
    cur_y = sorted_w[0][1]

    for w in sorted_w[1:]:
        if abs(w[1] - cur_y) <= y_tolerance:
            cur_words.append(w)
        else:
            # Finish current line
            cur_words.sort(key=lambda ww: ww[0])
            text = " ".join(ww[4] for ww in cur_words)
            x0 = min(ww[0] for ww in cur_words)
            y0 = min(ww[1] for ww in cur_words)
            x1 = max(ww[2] for ww in cur_words)
            y1 = max(ww[3] for ww in cur_words)
            lines.append({"text": text, "bbox": (x0, y0, x1, y1)})
            cur_words = [w]
            cur_y = w[1]

    # Last line
    if cur_words:
        cur_words.sort(key=lambda ww: ww[0])
        text = " ".join(ww[4] for ww in cur_words)
        x0 = min(ww[0] for ww in cur_words)
        y0 = min(ww[1] for ww in cur_words)
        x1 = max(ww[2] for ww in cur_words)
        y1 = max(ww[3] for ww in cur_words)
        lines.append({"text": text, "bbox": (x0, y0, x1, y1)})

    return lines


def _words_to_ocr_tokens(words: list[tuple], *, page_idx: int) -> list[OCRToken]:
    """Convert RapidOCR word tuples to OCRToken objects using the universal factory.

    Returns OCRToken objects so downstream consumers get rich typed data
    with bbox, confidence, source tracking, and confidence_tier.
    Call .to_dict() when serialization is needed.
    """
    tokens: list[OCRToken] = []
    for idx, word in enumerate(words or []):
        try:
            token = OCRToken.from_rapidocr_word(word, page=page_idx + 1, source="rapidocr", idx=idx)
            tokens.append(token)
        except (ValueError, TypeError):
            continue
    return tokens


def ocr_extract_universal(
    fitz_page,
    page_idx: int,
    min_confidence: float = 0.3,
    *,
    page_quality: int | None = None,
    external_ocr_threshold: int | None = None,
    external_ocr_provider: Callable[..., list[tuple] | dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Universal OCR extraction — auto-detects document type.

    When ``page_quality`` is below ``external_ocr_threshold`` and
    ``external_ocr_provider`` is set, delegates to the external provider
    instead of built-in OCR (for 99% recognition targets on very poor scans).

    For table-dominant pages, delegates to ``analyze_scanned_page``
    to preserve the stable table extraction contract.  For general documents (licenses,
    certificates, contracts, etc.), returns all text lines in reading
    order with real bounding boxes.

    Returns:
        dict with ``content_type`` ("table" or "general") plus:
        - table: same format as ``analyze_scanned_page``
        - general: ``{"lines": [{"text", "bbox"}, ...], "page_h", "page_w"}``
        Returns ``None`` on failure.
    """
    try:
        # ── External OCR handoff: quality too low for built-in ──
        if (
            page_quality is not None
            and external_ocr_threshold is not None
            and page_quality < external_ocr_threshold
            and external_ocr_provider is not None
        ):
            img_bgr, page_h, page_w = _render_page_to_bgr(fitz_page, dpi=200)
            try:
                out = external_ocr_provider(img_bgr, page_idx=page_idx, dpi=200, min_confidence=min_confidence)
            except Exception as e:
                logger.warning(f"[external_ocr] Provider failed on page {page_idx}: {e}")
                out = None
            if out is not None:
                if isinstance(out, dict) and out.get("content_type") in ("table", "general"):
                    if out.get("content_type") == "table":
                        from docmirror.ocr.ocr_postprocess import postprocess_ocr_result

                        postprocess_ocr_result(out)
                    logger.info(f"[DocMirror] Page {page_idx} delegated to external OCR (quality={page_quality})")
                    return out
                if isinstance(out, list) and out:
                    # List of (x0,y0,x1,y1,text,conf) → continue with our pipeline
                    all_words, img = out, img_bgr
                    page_w = img.shape[1]
                    has_table = _detect_has_table(img, page_h)
                    if has_table:
                        table_words = [(w[0], w[1], w[2], w[3], w[4]) for w in all_words]
                        table_result = analyze_scanned_page(
                            fitz_page,
                            page_idx,
                            min_confidence,
                            pre_existing_words=table_words,
                            pre_existing_img=img,
                            pre_existing_page_h=page_h,
                        )
                        if table_result:
                            table_result["content_type"] = "table"
                            return table_result
                    lines = _group_words_into_lines(all_words, y_tolerance=12.0)
                    return {
                        "content_type": "general",
                        "lines": lines,
                        "tokens": _words_to_ocr_tokens(all_words, page_idx=page_idx),
                        "_page_image": img,
                        "page_h": page_h,
                        "page_w": page_w,
                    }
            # External failed or returned invalid → fall through to built-in

        all_words, img, page_h = _run_ocr(fitz_page, min_confidence)
        if all_words is None:
            return None

        page_w = img.shape[1] if img is not None else 0

        # Decide: table or general?
        has_table = _detect_has_table(img, page_h)

        if has_table:
            # Pass pre-existing words to avoid duplicate OCR in analyze_scanned_page
            table_words = [(w[0], w[1], w[2], w[3], w[4]) for w in all_words]
            table_result = analyze_scanned_page(
                fitz_page,
                page_idx,
                min_confidence,
                pre_existing_words=table_words,
                pre_existing_img=img,
                pre_existing_page_h=page_h,
            )
            if table_result:
                table_result["content_type"] = "table"
                return table_result
            # If table pipeline fails, fall through to general

        # General document: output all text lines in reading order
        lines = _group_words_into_lines(all_words, y_tolerance=12.0)

        tokens_for_general = _words_to_ocr_tokens(all_words, page_idx=page_idx)
        tiered_for_general = TieredTokenCollection.from_tokens(tokens_for_general)
        return {
            "content_type": "general",
            "lines": lines,
            "tokens": tokens_for_general,
            "low_confidence_tokens": [t.to_dict() for t in tiered_for_general.low],
            "_tiered": tiered_for_general,
            "_page_image": img,
            "page_h": page_h,
            "page_w": page_w,
        }

    except Exception as e:
        logger.warning(f"[universal] OCR error on page {page_idx}: {e}")
        return None
