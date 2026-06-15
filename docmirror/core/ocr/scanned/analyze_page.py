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
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

from typing import Any

from docmirror.core.ocr.preprocess.legacy_fallback import (
    _deskew_image,
    _preprocess_image_for_ocr,
)
from docmirror.core.ocr.reconstruct.grid_legacy import (
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

        # Try to import an OCR engine
        ocr_engine = None
        try:
            from docmirror.core.ocr.vision.rapidocr_engine import get_ocr_engine

            ocr_engine = get_ocr_engine()
        except ImportError:
            pass

        if ocr_engine is None or not ocr_engine._engine:
            logger.debug("OCR skipped: no OCR engine available")
            return None

        # ── Auto-orientation probe ──
        # Render at low DPI for fast probe, detect best rotation
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
        # Adaptive DPI passes: start at target_dpi, escalate if needed
        dpi_passes = [target_dpi]
        if target_dpi < 300:
            dpi_passes.append(300)  # escalation pass
        for dpi in dpi_passes:
            pix = fitz_page.get_pixmap(dpi=dpi)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            if pix.n == 3:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)

            # Apply orientation correction if needed
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
                conf = w[8] if len(w) > 8 else 1.0
                if conf < min_confidence:
                    continue
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

        raw_result = {
            "table": main_table,
            "tables": tables if len(tables) > 1 else None,
            "header_text": header_text,
            "footer_text": footer_text,
        }

        # Apply OCR post-processing corrections (amount / date / domain terms)
        from .ocr_postprocess import postprocess_ocr_result

        return postprocess_ocr_result(raw_result)

    except ImportError:
        logger.debug("OCR skipped: required libraries not installed")
        return None
    except Exception as e:
        logger.warning(f"OCR error on page {page_idx}: {e}")
        return None
