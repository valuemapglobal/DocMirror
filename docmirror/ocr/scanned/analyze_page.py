# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Analyze scanned page — end-to-end OCR for image-only pages.

Purpose: Preprocesses scanned pages, runs OCR, detects table lines, and
reconstructs 2D table grids into extract-compatible structures.

Main components: ``analyze_scanned_page``.

Upstream: ``ocr.pipeline.run_scanned_page``, fitz page render.

Downstream: ``CoreExtractor`` scanned path, ``table.postprocess``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from typing import Any

from docmirror.ocr.micro_grid.models import OCRToken
from docmirror.ocr.preprocess.pipeline import (
    _deskew_image,
    _preprocess_image_for_ocr,
)
from docmirror.ocr.reconstruct.grid import (
    _detect_table_lines_hough,
    _group_chars_into_rows,
    _reconstruct_table_grid_2d,
    _split_tables_by_y_gap,
)


def analyze_scanned_page(
    fitz_page,
    page_idx: int,
    min_confidence: float = 0.3,
    table_bbox: tuple[float, float, float, float] | None = None,
    target_dpi: int = 200,
    *,
    pre_existing_words: list[tuple] | None = None,
    pre_existing_img: Any | None = None,
    pre_existing_page_h: int | None = None,
) -> dict[str, Any] | None:
    """Perform OCR-based extraction on a scanned document page.

    Pipeline:
        1. Optionally extract a text prior from the native text layer
           (hybrid text–vision prompt).
        2. Initialise an OCR engine (RapidOCR preferred).
        3. Render the page at ``target_dpi`` (retry at next tier if too few words).
        4. Preprocess the image and deskew.
        5. Run OCR; filter by confidence threshold.
        6. Segment into header / footer / table-body regions.
        7. Group characters into rows, detect columns (Hough or clustering),
           and build the table grid.
        8. Apply OCR post-processing corrections.

    Args:
        target_dpi: Rendering DPI for OCR.  Defaults to 200.
            The AdaptiveQualityRouter may pass 300 for dense/low-quality zones.

    Returns:
        A dict with keys ``table``, ``tables``, ``header_text``,
        ``footer_text``, or ``None`` on failure.
    """
    try:
        import cv2
        import numpy as np

        from ..extraction.foundation import FitzEngine

        # ── Hybrid text–vision prompt prior ──
        text_prior = ""
        if table_bbox:
            text_prior = FitzEngine.extract_raw_text_from_bbox(fitz_page, table_bbox)
        else:
            text_prior = FitzEngine.extract_page_text(fitz_page)

        if len(text_prior) > 1000:
            text_prior = text_prior[:1000]

        # ── Path A: Pre-existing words (skip OCR — use primary pass tokens) ──
        if pre_existing_words is not None:
            all_words = list(pre_existing_words)
            img = pre_existing_img
            page_h = pre_existing_page_h or (img.shape[0] if img is not None else 0)
            best_angle = 0  # Already oriented by the primary OCR pass
        else:
            # ── Path B: Full OCR (original rendering + recognition) ──
            try:
                from docmirror.ocr.vision.rapidocr_engine import get_ocr_engine

                ocr_engine = get_ocr_engine()
            except ImportError:
                pass

            if ocr_engine is None or not ocr_engine._engine:
                logger.debug("OCR skipped: no OCR engine available")
                return None

            # ── Auto-orientation probe ──
            probe_pix = fitz_page.get_pixmap(dpi=100)
            probe_img = np.frombuffer(probe_pix.samples, dtype=np.uint8).reshape(probe_pix.h, probe_pix.w, probe_pix.n)
            if probe_pix.n == 3:
                probe_img = cv2.cvtColor(probe_img, cv2.COLOR_RGB2BGR)
            elif probe_pix.n == 4:
                probe_img = cv2.cvtColor(probe_img, cv2.COLOR_RGBA2BGR)
            best_angle = _probe_best_orientation(probe_img, ocr_engine)

            all_words = []
            page_h = 0
            img = None
            dpi_passes = [target_dpi]
            if target_dpi < 300:
                dpi_passes.append(300)
            for dpi in dpi_passes:
                pix = fitz_page.get_pixmap(dpi=dpi)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                if pix.n == 3:
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                elif pix.n == 4:
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)

                if best_angle == 90:
                    img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                elif best_angle == 180:
                    img = cv2.rotate(img, cv2.ROTATE_180)
                elif best_angle == 270:
                    img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

                page_h = img.shape[0]

                img_processed = _preprocess_image_for_ocr(img)
                img_processed, skew_angle = _deskew_image(img_processed)

                words = ocr_engine.detect_image_words(img_processed, multi_scale=(dpi >= 300))
                if not words:
                    if dpi == 150:
                        continue
                    return None

                all_words = []
                for w in words:
                    text = w[4].strip()
                    if not text:
                        continue
                    all_words.append((w[0], w[1], w[2], w[3], text))

                if len(all_words) >= 10 or dpi == 300:
                    break

        if len(all_words) < 3:
            return None

        # ── Region segmentation ──
        header_y = page_h * 0.12
        footer_y = page_h * 0.90

        header_words = [w for w in all_words if w[3] < header_y]
        footer_words = [w for w in all_words if w[1] > footer_y]
        table_words = [w for w in all_words if w[1] >= header_y and w[3] <= footer_y]

        header_text = " ".join(w[4] for w in sorted(header_words, key=lambda w: (w[1], w[0])))
        footer_text = " ".join(w[4] for w in sorted(footer_words, key=lambda w: (w[1], w[0])))

        if len(table_words) < 2:
            return None

        chars = []
        for x0, y0, x1, y1, text in table_words:
            chars.append(
                {
                    "x0": float(x0),
                    "x1": float(x1),
                    "top": float(y0),
                    "bottom": float(y1),
                    "text": str(text),
                    "upright": True,
                }
            )

        rows_by_y = _group_chars_into_rows(chars, y_tolerance=8.0)
        if len(rows_by_y) < 2:
            return None

        _split_tables_by_y_gap(rows_by_y, page_h)

        # Detect column boundaries — Hough lines first
        col_bounds_hough = _detect_table_lines_hough(img, page_h, img.shape[1] if img is not None else 0)

        # ── Advanced 2D Grid Reconstruction ──
        # Group characters into independent tables first
        rows_by_y_raw = _group_chars_into_rows(chars, y_tolerance=8.0)
        table_groups_raw = _split_tables_by_y_gap(rows_by_y_raw, page_h)

        tables = []
        for group in table_groups_raw:
            # Flatten group chars
            grp_chars = []
            for _, r_chars in group:
                grp_chars.extend(r_chars)

            # Reconstruct 2D grid
            tb = _reconstruct_table_grid_2d(grp_chars, hough_lines=col_bounds_hough)

            # Clean up empty rows and single-column tables
            tb_clean = [row for row in tb if any(cell.strip() for cell in row)]
            if len(tb_clean) >= 2 and len(tb_clean[0]) >= 2:
                tables.append(tb_clean)

        if not tables:
            return None

        main_table = max(tables, key=len)

        # ── GA1.0-01: Build evidence-bus tokens from raw OCR words ──
        evidence_tokens: list[dict] = []
        for i, w in enumerate(all_words):
            try:
                token = OCRToken.from_rapidocr_word(w, page=page_idx, idx=i)
                evidence_tokens.append(token.to_dict())
            except (ValueError, IndexError):
                pass

        raw_result = {
            "table": main_table,
            "tables": tables if len(tables) > 1 else None,
            "header_text": header_text,
            "footer_text": footer_text,
            "tokens": evidence_tokens,
        }

        # GA1.0-05: Context-aware post-processing with column-aware correction
        from docmirror.ocr.ocr_postprocess import (
            ColumnContext,
            enrich_col_bands_with_context,
            infer_column_type,
            postprocess_ocr_result,
            postprocess_ocr_text,
            postprocess_table_context_aware,
        )

        # ── GA1.0-02/05: GCR-enhanced column context with data-pattern fallback ──
        col_contexts = []
        if main_table:
            ncols = max(len(r) for r in main_table)

            # Path A: GCR-enhanced column context (when pre_existing_words available)
            if pre_existing_words is not None:
                try:
                    from docmirror.ocr.reconstruct.gcr import GCRColumns

                    tokens = [
                        OCRToken.from_rapidocr_word(w, page=page_idx, idx=i) for i, w in enumerate(pre_existing_words)
                    ]
                    gcr = GCRColumns.from_tokens(tokens)
                    if gcr.col_bands and len(gcr.col_bands) >= 2:
                        header_texts = [main_table[0][ci] if ci < len(main_table[0]) else None for ci in range(ncols)]
                        sample_values = [
                            [r[ci].strip() for r in main_table[1:5] if ci < len(r) and r[ci].strip()]
                            for ci in range(ncols)
                        ]
                        band_dicts = [
                            {
                                "col_index": b.col_index,
                                "x_start": b.x_start,
                                "x_end": b.x_end,
                                "support_ratio": b.support_ratio,
                                "confidence": b.confidence,
                            }
                            for b in gcr.col_bands
                        ]
                        enriched = enrich_col_bands_with_context(
                            band_dicts,
                            header_texts,
                            sample_values,
                        )
                        for band in enriched:
                            ctx = band.get("column_context", {})
                            col_contexts.append(
                                ColumnContext(
                                    column_index=ctx.get("column_index", len(col_contexts)),
                                    header_text=ctx.get("header_text"),
                                    inferred_type=ctx.get("inferred_type", "unknown"),
                                    confidence=ctx.get("confidence", 0.0),
                                    column_bands=[band],
                                    supported_formats=ctx.get("supported_formats", []),
                                )
                            )
                except Exception:
                    logger.debug(
                        "GCR column context failed, fallback to data inference",
                        exc_info=True,
                    )

            # Path B: Data-pattern inference (fallback / non-GCR path)
            if not col_contexts:
                for ci in range(ncols):
                    hdr = main_table[0][ci] if ci < len(main_table[0]) else None
                    samples = [r[ci].strip() for r in main_table[1:5] if ci < len(r) and r[ci].strip()]
                    col_contexts.append(
                        infer_column_type(
                            header_text=hdr,
                            sample_values=samples,
                            column_index=ci,
                        )
                    )

        meaningful = [c for c in col_contexts if c.inferred_type != "unknown"]
        if meaningful and len(meaningful) >= max(2, len(col_contexts) * 0.3):
            raw_result["table"] = postprocess_table_context_aware(main_table, col_contexts)
            if raw_result.get("tables"):
                raw_result["tables"] = [
                    postprocess_table_context_aware(t, col_contexts[: len(t[0])]) for t in raw_result["tables"] if t
                ]
        else:
            raw_result = postprocess_ocr_result(raw_result)

        # Always correct header/footer text
        if raw_result.get("header_text"):
            raw_result["header_text"] = postprocess_ocr_text(raw_result["header_text"])
        if raw_result.get("footer_text"):
            raw_result["footer_text"] = postprocess_ocr_text(raw_result["footer_text"])

        return raw_result

    except ImportError:
        logger.debug("OCR skipped: required libraries not installed")
        return None
    except Exception as e:
        logger.warning(f"OCR error on page {page_idx}: {e}")
        return None
