# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Formula zone handler — math/formula recognition for formula zones.

Purpose: Crops formula regions and runs ``FormulaEngine`` / char-based LaTeX
extraction to produce formula blocks.

Main components: ``handle_formula_zone``.

Upstream: Formula zones from ``page_segment``.

Downstream: ``ocr.formula_engine``, ``ocr.formula_chars``.
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

from docmirror.models.entities.domain import Block
from docmirror.core.pipeline.handlers.zone_utils import crop_zone_image, recognize_formula

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)
_clock = time.perf_counter

def handle_formula_zone(extractor: "PageExtractor",
    zone,
    block_id: str,
    page_idx: int,
    fitz_page,
    width: float,
    height: float,
    content_type: str,
    reading_order: int,
) -> tuple[Block | None, float]:
    """Handle a formula-type zone → Block conversion.

    Returns:
        (block_or_none, formula_ms): The formula block (or None if no formula
        was detected) and the time spent in ms.
    """
    _fml_t = _clock()
    # Perf #10: Skip formula detection for text/table dominant docs
    _skip_formula = content_type in ("text_dominant", "table_dominant") or not extractor._host._formula_engine
    if _skip_formula:
        if zone.text:
            block = Block(
                block_id=block_id,
                block_type="text",
                bbox=zone.bbox,
                reading_order=reading_order,
                page=page_idx + 1,
                raw_content=zone.text,
            )
            return block, (_clock() - _fml_t) * 1000
        return None, (_clock() - _fml_t) * 1000

    # ── 3-tier formula zone gating (skip false-positive OCR) ──
    _skip_formula_ocr = False

    # Gate 1: YOLO confidence threshold
    if zone.confidence < 0.65:
        _skip_formula_ocr = True
        logger.debug(f"formula gate: skipped zone (confidence={zone.confidence:.2f} < 0.65)")

    # Gate 2: Zone area filter (formulas are small)
    if not _skip_formula_ocr:
        zone_area = (zone.bbox[2] - zone.bbox[0]) * (zone.bbox[3] - zone.bbox[1])
        page_area = width * height
        if page_area > 0 and zone_area > page_area * 0.3:
            _skip_formula_ocr = True
            logger.debug(f"formula gate: skipped zone (area={zone_area:.0f} > 30% page)")

    # Gate 3: Character content pre-check (must have math indicators)
    if not _skip_formula_ocr:
        _MATH_INDICATORS = set("∑∫∂√±≤≥≠∞∈∉∝∀∃αβγδεθλμπσφψω")
        zone_text = zone.text or ""
        has_math_chars = bool(set(zone_text) & _MATH_INDICATORS)
        has_operator_pattern = bool(
            re.search(
                r"[≤≥±×÷∑∫]"  # Unambiguous math symbols
                r"|[a-zA-Z]\^[\d{]"  # Superscript notation: x^2, x^{n}
                r"|[a-zA-Z]_[\d{]"  # Subscript notation: a_1, a_{ij}
                r"|\\\\[a-z]{3,}"  # LaTeX commands: \\frac, \\sqrt
                r"|\{[^}]+\}",  # Braced expressions: {n+1}
                zone_text,
            )
        )

        # True superscript detection: small chars that are ELEVATED
        has_superscript = False
        if zone.chars and len(zone.chars) >= 3:
            sizes = [c.get("size", 12) for c in zone.chars if c.get("size", 0) > 0]
            if sizes:
                median_size = sorted(sizes)[len(sizes) // 2]
                if median_size > 5:
                    tops = [c["top"] for c in zone.chars]
                    median_top = sorted(tops)[len(tops) // 2]
                    has_superscript = any(
                        c.get("size", 12) < median_size * 0.6 and c["top"] < median_top - 2 for c in zone.chars
                    )

        if not (has_math_chars or has_operator_pattern or has_superscript):
            _skip_formula_ocr = True
            logger.debug(f"formula gate: skipped zone (no math indicators in '{zone_text[:30]}')")

    # K1: prefer extracting from character stream (zero latency)
    latex_str = None
    try:
        from docmirror.core.ocr.formula_chars import extract_formula_from_chars

        if zone.chars:
            latex_str = extract_formula_from_chars(zone.chars, zone.bbox)
    except Exception as exc:
        logger.debug(f"operation: suppressed {exc}")

    # K1 fallback: OCR cropped image recognition (ONLY if gates passed)
    if not latex_str and not _skip_formula_ocr:
        formula_img = crop_zone_image(fitz_page, zone.bbox)
        latex_str = recognize_formula(extractor, formula_img)
    _formula_ms = (_clock() - _fml_t) * 1000

    if latex_str:
        block = Block(
            block_id=block_id,
            block_type="formula",
            bbox=zone.bbox,
            reading_order=reading_order,
            page=page_idx + 1,
            raw_content=latex_str,
        )
        return block, _formula_ms
    elif _skip_formula_ocr and zone.text:
        block = Block(
            block_id=block_id,
            block_type="text",
            bbox=zone.bbox,
            reading_order=reading_order,
            page=page_idx + 1,
            raw_content=zone.text,
        )
        return block, _formula_ms
    return None, _formula_ms

