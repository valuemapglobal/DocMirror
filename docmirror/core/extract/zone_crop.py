# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Zone crop — geometry helpers to crop pages to table zones.

Purpose: Crops fitz pages or images to table zone bboxes (simple and padded
variants) before backend extraction.

Main components: ``crop_to_table_zone``, ``crop_simple_to_table_zone``.

Upstream: ``Zone`` bboxes from segmentation.

Downstream: ``extract.engine``, ``ocr`` preprocess paths.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from ..utils.vocabulary import _RE_IS_AMOUNT, _RE_IS_DATE, _is_header_cell, _score_header_by_vocabulary

logger = logging.getLogger(__name__)


def crop_to_table_zone(
    page_plum,
    table_zone_bbox: tuple[float, float, float, float],
) -> tuple:
    """Crop page to table zone with upward header probe expansion.

    The header probe scans above the declared zone bbox for header rows
    that may have been excluded from YOLO's table zone prediction. Uses
    vocabulary scoring to select the best candidate header row and
    multi-row header detection.

    Args:
        page_plum: pdfplumber page object.
        table_zone_bbox: ``(x0, y0, x1, y1)`` bounding box of the table zone.

    Returns:
        ``(work_page, y0, y1)`` — the cropped page and the (possibly
        expanded) y-coordinate boundaries.
    """
    x0, y0, x1, y1 = table_zone_bbox

    # Upward header probe: header row may sit above the data_table zone
    _probe_dist = 120
    h_lines_above = [
        l
        for l in (page_plum.lines or [])
        if abs(l["top"] - l["bottom"]) < 2 and l["top"] < y0 - 5 and l["top"] > y0 - _probe_dist
    ]
    if h_lines_above:
        _probe_dist = max(_probe_dist, y0 - min(l["top"] for l in h_lines_above) + 10)
    probe_top = max(0, y0 - _probe_dist)

    if probe_top < y0:
        try:
            probe = page_plum.crop((x0, probe_top, x1, y0 + 1))
            probe_words = probe.extract_words(keep_blank_chars=True, x_tolerance=2)
            if probe_words:
                _probe_rows = defaultdict(list)
                for w in probe_words:
                    yk = round(w["top"] / 3) * 3
                    _probe_rows[yk].append(w)

                best_candidate = None
                for yk in sorted(_probe_rows):
                    texts = [w["text"].strip() for w in _probe_rows[yk] if w["text"].strip()]
                    if len(texts) < 3:
                        continue
                    kv_count = sum(1 for t in texts if ":" in t or "：" in t)
                    if kv_count / len(texts) >= 0.5:
                        continue
                    hdr_count = sum(1 for t in texts if _is_header_cell(t))
                    if hdr_count / len(texts) < 0.5:
                        continue
                    vocab = _score_header_by_vocabulary(texts)
                    candidate = (vocab, hdr_count / len(texts), len(texts), yk)
                    if best_candidate is None or candidate > best_candidate:
                        best_candidate = candidate

                if best_candidate:
                    chosen_yk = best_candidate[3]
                    header_y = min(w["top"] for w in _probe_rows[chosen_yk]) - 2

                    # Multi-row header detection
                    all_yks = sorted(_probe_rows)
                    chosen_idx = all_yks.index(chosen_yk)
                    if chosen_idx > 0:
                        prev_yk = all_yks[chosen_idx - 1]
                        prev_texts = [w["text"].strip() for w in _probe_rows[prev_yk] if w["text"].strip()]
                        row_gap = chosen_yk - prev_yk
                        if (
                            len(prev_texts) >= 2
                            and row_gap < 20
                            and not any(_RE_IS_DATE.search(t) for t in prev_texts)
                            and not any(_RE_IS_AMOUNT.match(t.replace(",", "")) for t in prev_texts)
                        ):
                            prev_hdr = sum(1 for t in prev_texts if _is_header_cell(t))
                            if prev_hdr / len(prev_texts) >= 0.5:
                                header_y = min(w["top"] for w in _probe_rows[prev_yk]) - 2
                                logger.debug(f"header probe: multi-row header detected, expanded to {header_y:.0f}")

                    y0 = max(0, header_y)
                    logger.debug(
                        f"header probe: "
                        f"expanded zone top "
                        f"from {table_zone_bbox[1]:.0f}"
                        f" to {y0:.0f}"
                        f" (vocab={best_candidate[0]}, words={best_candidate[2]})"
                    )
        except Exception as exc:
            logger.debug(f"operation: suppressed {exc}")

    crop_x0 = 0
    crop_x1 = page_plum.width
    work_page = page_plum.crop((crop_x0, y0, crop_x1, y1))
    logger.debug(f"cropped to table zone: x={crop_x0:.0f}-{crop_x1:.0f}, y={y0:.0f}-{y1:.0f}")
    return work_page, y0, y1


def crop_simple_to_table_zone(
    page_plum,
    table_zone_bbox: tuple[float, float, float, float],
) -> tuple:
    """Fast crop without header probe — used on ledger continuation pages."""
    _x0, y0, _x1, y1 = table_zone_bbox
    work_page = page_plum.crop((0, y0, page_plum.width, y1))
    return work_page, y0, y1
