# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Legacy OCR runner — multi-scale recognition and fragment merging.

Purpose: Runs OCR at multiple scales, merges line fragments and overlapping
words into a coherent char/word stream.

Main components: ``_run_ocr``, ``_merge_line_fragments``, ``_merge_multi_scale_words``.

Upstream: ``ocr.preprocess.legacy_fallback`` prepared images.

Downstream: ``ocr.table_reconstruction``, ``ocr.scanned.universal``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from docmirror.structure.ocr.preprocess.legacy_fallback import (
    _deskew_image,
    _preprocess_image_for_ocr,
    _preprocess_minimal,
    _read_exif_orientation,
)
from docmirror.structure.ocr.reconstruct.grid_legacy import _probe_best_orientation


def _merge_line_fragments(words):
    """Merge OCR word fragments that belong to the same text line.

    Conservative rules:
        - Vertical overlap > 50% of the shorter word's height.
        - Horizontal gap < 1.5× average character height.
    Sorts by reading order (top→bottom, left→right) after merging.

    Args:
        words: list of (x0, y0, x1, y1, text, conf) tuples.
    Returns:
        Merged list in the same format.
    """
    if not words or len(words) < 2:
        return words

    # Sort by y-centre then x
    ws = sorted(words, key=lambda w: (((w[1] + w[3]) / 2), w[0]))
    merged = [list(ws[0])]

    for w in ws[1:]:
        last = merged[-1]
        # Heights
        h_last = last[3] - last[1]
        h_curr = w[3] - w[1]
        min_h = min(h_last, h_curr)
        if min_h <= 0:
            merged.append(list(w))
            continue

        # Vertical overlap
        overlap_top = max(last[1], w[1])
        overlap_bot = min(last[3], w[3])
        v_overlap = max(0, overlap_bot - overlap_top)

        # Horizontal gap
        h_gap = w[0] - last[2]

        avg_char_h = (h_last + h_curr) / 2

        if v_overlap > 0.5 * min_h and h_gap < 1.5 * avg_char_h:
            # Merge: extend bounding box, concatenate text
            last[0] = min(last[0], w[0])
            last[1] = min(last[1], w[1])
            last[2] = max(last[2], w[2])
            last[3] = max(last[3], w[3])
            last[4] = last[4] + w[4]
            # Weighted average confidence
            last[5] = (last[5] * len(last[4]) + w[5] * len(w[4])) / (len(last[4]) + len(w[4]))
        else:
            merged.append(list(w))

    return [tuple(m) for m in merged]


def _merge_multi_scale_words(all_scale_words: list[tuple[int, list[tuple]]]) -> list[tuple]:
    """Fuse words from multiple DPI scales using Non-Maximum Suppression (NMS).

    Args:
        all_scale_words: List of (dpi, words) tuples.
            words are (x0, y0, x1, y1, text, conf) in the scale's coordinate space.
    Returns:
        Fused list of words in the 72 DPI (standard PDF) coordinate space.
    """
    if not all_scale_words:
        return []

    BASE_DPI = 72.0
    projected_words = []

    # Project all words to 72 DPI space
    for dpi, words in all_scale_words:
        scale = BASE_DPI / float(dpi)
        for w in words:
            px0, py0 = w[0] * scale, w[1] * scale
            px1, py1 = w[2] * scale, w[3] * scale
            # Store tuple: (x0, y0, x1, y1, text, conf, dpi, area)
            area = (px1 - px0) * (py1 - py0)
            if area > 0:
                projected_words.append((px0, py0, px1, py1, w[4], w[5], dpi, area))

    if not projected_words:
        return []

    # Sort primarily by confidence (descending), secondarily by area (descending)
    projected_words.sort(key=lambda x: (x[5], x[7]), reverse=True)

    kept_words = []

    def _compute_iou(b1, b2):
        # Axis-aligned box tuple layout: x0, y0, x1, y1
        ix0 = max(b1[0], b2[0])
        iy0 = max(b1[1], b2[1])
        ix1 = min(b1[2], b2[2])
        iy1 = min(b1[3], b2[3])

        iw = max(0, ix1 - ix0)
        ih = max(0, iy1 - iy0)
        intersection = iw * ih

        area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
        union = area1 + area2 - intersection

        if union <= 0:
            return 0.0
        return intersection / union

    def _compute_intersection_over_min_area(b1, b2):
        # Stricter overlap for tiny text inside big text boxes
        ix0 = max(b1[0], b2[0])
        iy0 = max(b1[1], b2[1])
        ix1 = min(b1[2], b2[2])
        iy1 = min(b1[3], b2[3])

        iw = max(0, ix1 - ix0)
        ih = max(0, iy1 - iy0)
        intersection = iw * ih

        area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
        min_area = min(area1, area2)

        if min_area <= 0:
            return 0.0
        return intersection / min_area

    # NMS Loop
    for p_word in projected_words:
        b1 = p_word[0:4]
        is_suppressed = False

        for k_word in kept_words:
            b2 = k_word[0:4]
            # If overlap is massive (>60% of the smaller box), they represent the same text
            overlap_ratio = _compute_intersection_over_min_area(b1, b2)
            if overlap_ratio > 0.6:
                is_suppressed = True
                break

        if not is_suppressed:
            kept_words.append(p_word)

    # Re-scale kept words back to the coordinate space of the highest DPI we processed
    # (Because the rest of the pipeline expects coordinates in the rendered image space)
    target_dpi = max(dpi for dpi, _ in all_scale_words)
    inv_scale = target_dpi / BASE_DPI

    final_output = []
    for w in kept_words:
        fx0, fy0 = w[0] * inv_scale, w[1] * inv_scale
        fx1, fy1 = w[2] * inv_scale, w[3] * inv_scale
        final_output.append((fx0, fy0, fx1, fy1, w[4], w[5]))

    # Sort by reading order
    return sorted(final_output, key=lambda w: (((w[1] + w[3]) / 2), w[0]))


def _run_ocr(fitz_page, min_confidence: float = 0.3, *, dpi_list: list[int] | None = None):
    """Run OCR on a fitz page with adaptive strategy escalation.

    Performance-optimized approach:
      - Try Strategy B (minimal) first — fastest (~100ms)
      - Escalate to A (full) only if B score is insufficient
      - Try C (KMeans color slice) only as last resort
      - Early exit when composite score exceeds threshold
      - Rescue (DET/REC decoupling) only when word count < 5

    Args:
        dpi_list: DPI values to try. Defaults to [150, 200, 300].

    Returns:
        (all_words, img, page_h) where each word is
        (x0, y0, x1, y1, text, confidence).
        Returns (None, None, 0) on failure.
    """
    import cv2
    import numpy as np

    if dpi_list is None:
        dpi_list = [150, 200, 300]

    # Locate OCR engine
    ocr_engine = None
    try:
        from rapidocr_onnxruntime import RapidOCR as _RapidOCR

        ocr_engine = _RapidOCR()
    except ImportError:
        try:
            from docmirror.structure.ocr.vision.rapidocr_engine import get_ocr_engine

            _eng = get_ocr_engine()
            if _eng and _eng._engine:
                ocr_engine = _eng._engine
        except ImportError:
            pass

    if ocr_engine is None:
        logger.debug("[universal] OCR skipped: no OCR engine available")
        return None, None, 0

    # ── Auto-orientation ──
    # Try EXIF first (reliable), fall back to probe
    best_angle = _read_exif_orientation(fitz_page)
    if best_angle == 0:
        probe_pix = fitz_page.get_pixmap(dpi=100)
        probe_img = np.frombuffer(probe_pix.samples, dtype=np.uint8).reshape(probe_pix.h, probe_pix.w, probe_pix.n)
        if probe_pix.n == 3:
            probe_img = cv2.cvtColor(probe_img, cv2.COLOR_RGB2BGR)
        elif probe_pix.n == 4:
            probe_img = cv2.cvtColor(probe_img, cv2.COLOR_RGBA2BGR)
        best_angle = _probe_best_orientation(probe_img, ocr_engine)

    # ── Helper: single OCR pass ──
    def _ocr_pass(img_input, preprocess_fn, label):
        img_pp = preprocess_fn(img_input.copy())
        img_pp, _ = _deskew_image(img_pp)
        try:
            result, _ = ocr_engine(img_pp)
        except Exception as exc:
            logger.debug(f"operation: suppressed {exc}")
            return [], 0.0
        if not result:
            return [], 0.0
        words = []
        for box, text, conf in result:
            text = text.strip()
            if not text:
                continue
            x_coords = [p[0] for p in box]
            y_coords = [p[1] for p in box]
            words.append(
                (
                    min(x_coords),
                    min(y_coords),
                    max(x_coords),
                    max(y_coords),
                    text,
                    conf,
                )
            )
        score = sum(w[5] for w in words)
        logger.debug(f"[OCR] {label}: {len(words)} words, score={score:.1f}")
        return words, score

    # ── Helper: Dynamic Color Slice (Strategy C: HSV/YcbCr KMeans) ──
    def _ocr_dynamic_color_slice(img_input):
        """Extract dominant ink layers using HSV KMeans, and run OCR on YCbCr Luminance."""
        import cv2
        import numpy as np

        best_slice_words, best_slice_score = [], 0.0

        # 1. YCbCr Luminance (Y channel) - best for human/OCR perception of detail
        ycbcr = cv2.cvtColor(img_input, cv2.COLOR_BGR2YCrCb)
        y_channel = ycbcr[:, :, 0]
        y_bgr = cv2.cvtColor(y_channel, cv2.COLOR_GRAY2BGR)
        w, s = _ocr_pass(y_bgr, _preprocess_minimal, "Ch-Y(Luminance)")
        if s > best_slice_score:
            best_slice_words, best_slice_score = w, s

        # 2. Dynamic HSV Hue extraction for colored overlays (e.g. red seals)
        hsv = cv2.cvtColor(img_input, cv2.COLOR_BGR2HSV)
        h_channel = hsv[:, :, 0]

        # Subsample for fast KMeans (e.g., max 500x500 points)
        scale_k = min(1.0, 500.0 / max(img_input.shape[0:2]))
        small_h = cv2.resize(h_channel, (0, 0), fx=scale_k, fy=scale_k)
        pixels = np.float32(small_h.reshape(-1))

        # Find 3 dominant hues (Background, Text, Overlay/Seal)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(pixels, 3, None, criteria, 3, cv2.KMEANS_PP_CENTERS)

        centers = np.uint8(centers.flatten())

        # Generate a mask for each dominant hue layer and run OCR on it
        for i, center_val in enumerate(centers):
            # Create mask for pixels close to this hue
            lower_bound = max(0, int(center_val) - 15)
            upper_bound = min(179, int(center_val) + 15)

            mask = cv2.inRange(h_channel, lower_bound, upper_bound)

            # Apply mask to original luminance channel
            # We want to keep the text (dark) in the masked region
            masked_y = np.full_like(y_channel, 255)  # White background
            masked_y[mask > 0] = y_channel[mask > 0]

            slice_bgr = cv2.cvtColor(masked_y, cv2.COLOR_GRAY2BGR)
            w, s = _ocr_pass(slice_bgr, _preprocess_minimal, f"HSV-Slice-{i}(H={center_val})")

            if s > best_slice_score:
                best_slice_words, best_slice_score = w, s

        return best_slice_words, best_slice_score

    # ── Helper: DET/REC Decoupling Rescue (Strategy D) ──
    def _rescue_missing_regions(img_input, existing_words):
        """Force REC on regions that DET missed using OpenCV morphology."""
        import cv2

        from docmirror.structure.ocr.vision.rapidocr_engine import get_ocr_engine

        # 1. Enhance and binarize for connected components
        gray = cv2.cvtColor(img_input, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Adaptive threshold to find dark blobs
        binary = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)

        # Connect nearby characters into text lines
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        dilated = cv2.dilate(binary, kernel, iterations=1)

        # Find contours of potential text blocks
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours
        candidate_regions = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            # Filter noise (too small) and huge blocks (too big)
            if 15 < h < 100 and 15 < w < img_input.shape[1] * 0.8:
                # Add padding
                pad_x, pad_y = 5, 5
                cx0 = max(0, x - pad_x)
                cy0 = max(0, y - pad_y)
                cx1 = min(img_input.shape[1], x + w + pad_x)
                cy1 = min(img_input.shape[0], y + h + pad_y)

                # Check if this region is ALREADY covered by existing DET words
                is_covered = False
                for ex_w in existing_words:
                    ew_x0, ew_y0, ew_x1, ew_y1 = ex_w[0:4]
                    # Calculate IoU or partial overlap
                    ix0, iy0 = max(cx0, ew_x0), max(cy0, ew_y0)
                    ix1, iy1 = min(cx1, ew_x1), min(cy1, ew_y1)
                    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
                    if iw * ih > 0:
                        is_covered = True
                        break

                if not is_covered:
                    candidate_regions.append((cx0, cy0, cx1, cy1))

        # Force recognize these candidate regions
        rescued_words = []
        if candidate_regions:
            engine = get_ocr_engine()
            raw_rescued = engine.force_recognize_regions(img_input, candidate_regions)
            rescued_words = list(raw_rescued)

        score = sum(w[5] for w in rescued_words)
        return rescued_words, score

    # ── Multi-Dimensional composite scoring ──
    def _composite_score(words, raw_score):
        if not words:
            return 0.0
        n = len(words)
        mean_conf = raw_score / n if n > 0 else 0.0
        unique_chars = len(set("".join(w[4] for w in words)))
        return (n * mean_conf * max(1, unique_chars)) ** (1.0 / 3.0)

    # ══════════════════════════════════════════════════════════════════════
    # Main loop: adaptive DPI + early-exit strategy escalation
    # ══════════════════════════════════════════════════════════════════════
    all_scale_results = []
    final_img = None
    final_page_h = 0

    # Early-exit threshold: skip remaining DPIs/strategies when score is good enough
    _GOOD_ENOUGH_SCORE = 8.0
    # Half-threshold: below this, try heavy strategies
    _ESCALATION_THRESHOLD = _GOOD_ENOUGH_SCORE * 0.5

    for dpi in dpi_list:
        pix = fitz_page.get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)

        # Apply orientation correction
        if best_angle == 90:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif best_angle == 180:
            img = cv2.rotate(img, cv2.ROTATE_180)
        elif best_angle == 270:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

        page_h = img.shape[0]

        # ── Adaptive strategy escalation (lightest first) ──
        # Step 1: Try Strategy B (minimal — fastest, ~100ms)
        words_b, score_b = _ocr_pass(img, _preprocess_minimal, "Strategy-B(minimal)")
        cs_b = _composite_score(words_b, score_b)
        best_words, best_cs, winner = words_b, cs_b, "B"

        # Step 2: Only escalate to Strategy A if B is insufficient
        if cs_b < _GOOD_ENOUGH_SCORE:
            words_a, score_a = _ocr_pass(img, _preprocess_image_for_ocr, "Strategy-A(full)")
            cs_a = _composite_score(words_a, score_a)
            if cs_a > best_cs:
                best_words, best_cs, winner = words_a, cs_a, "A"

        # Step 3: Only try Strategy C (heavy KMeans) if both A and B are poor
        if best_cs < _ESCALATION_THRESHOLD:
            words_c, score_c = _ocr_dynamic_color_slice(img)
            cs_c = _composite_score(words_c, score_c)
            if cs_c > best_cs:
                best_words, best_cs, winner = words_c, cs_c, "C"

        logger.debug(f"[OCR] DPI={dpi}: winner=Strategy-{winner} (score={best_cs:.2f})")

        # Step 4: Rescue only when word count is suspiciously low
        if len(best_words) < 5:
            try:
                rescued_words, rescued_score = _rescue_missing_regions(img, best_words)
                if rescued_words:
                    best_words = list(best_words) + rescued_words
                    logger.debug(f"[OCR] DPI={dpi}: Rescued {len(rescued_words)} missing regions.")
            except Exception as exc:
                logger.debug(f"[OCR] Rescue skipped: {exc}")

        all_scale_results.append((dpi, best_words))
        final_img = img
        final_page_h = page_h

        # ── Early exit: if score is good enough, skip remaining DPIs ──
        if best_cs >= _GOOD_ENOUGH_SCORE and dpi < max(dpi_list):
            logger.debug(f"[OCR] Early exit at DPI={dpi} (score={best_cs:.2f} >= {_GOOD_ENOUGH_SCORE})")
            break

    # ── Multi-Scale NMS Fusion ──
    best_words = _merge_multi_scale_words(all_scale_results)

    if len(best_words) < 3:
        return None, None, 0

    # ── Text line merge: join fragments on the same line ──
    best_words = _merge_line_fragments(best_words)

    return best_words, final_img, final_page_h
