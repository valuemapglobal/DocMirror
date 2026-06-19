# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Page styles handler — typographic style and heading inference.

Purpose: Extracts font/size/color spans and infers heading levels for title
and text block rendering.

Main components: ``extract_page_styles``, ``build_spans``, ``infer_heading_level``.

Upstream: Fitz page char dicts in prepare/assemble.

Downstream: ``physical.models.TextSpan``, ``output.markdown_exporter``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from docmirror.models.entities.domain import Style, TextSpan
from docmirror.core.extraction.foundation import FitzEngine

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)

def extract_page_styles(_extractor: PageExtractor, fitz_page) -> dict[str, Style]:
    """Extract visual features of text within the page."""
    style_map: dict[str, Style] = {}
    try:
        spans = FitzEngine.extract_page_blocks_with_style(fitz_page)
        for span_info in spans:
            text = span_info["text"].strip()
            if not text:
                continue
            key = text[:20]
            flags = span_info["flags"]
            color_int = span_info["color"]
            style = Style(
                font_name=span_info["font_name"],
                font_size=round(span_info["font_size"], 1),
                color=f"#{color_int:06x}" if isinstance(color_int, int) else "#000000",
                is_bold=bool(flags & 16),
                is_italic=bool(flags & 2),
            )
            style_map[key] = style
    except Exception as e:
        logger.debug(f"[DocMirror] style extraction error: {e}")
    return style_map



def build_spans(
    text: str,
    bbox: tuple[float, float, float, float],
    style_map: dict[str, Style],
) -> tuple[TextSpan, ...]:
    """Build TextSpan sequence from text + coordinates + style_map."""
    if not text:
        return ()

    key = text[:20]
    style = style_map.get(key, Style())
    return (TextSpan(text=text, bbox=bbox, style=style),)



def infer_heading_level(
    text: str,
    style_map: dict[str, Style],
) -> int | None:
    """Infer heading level based on font size and bold attributes.

    Strategy:
        - Collect all font sizes from style_map
        - Calculate median body text font size as baseline
        - Determine h1/h2/h3 based on relative size + bold:
          * font_size >= baseline * 1.6 and bold -> h1
          * font_size >= baseline * 1.2 and bold -> h2
          * bold only -> h3
          * not bold but notably larger font -> h2

    Returns:
        1, 2, 3 or None (when indeterminate)
    """
    if not text:
        return None

    key = text[:20]
    style = style_map.get(key)
    if not style:
        return None

    # Collect all font sizes within the page as context
    all_sizes = [s.font_size for s in style_map.values() if s.font_size > 0]
    if not all_sizes:
        return 3 if style.is_bold else None

    all_sizes.sort()
    # Median as body text baseline
    mid = len(all_sizes) // 2
    baseline = all_sizes[mid] if all_sizes else 10.0

    fs = style.font_size
    is_bold = style.is_bold

    if baseline <= 0:
        return 3 if is_bold else None

    ratio = fs / baseline

    if is_bold and ratio >= 1.6:
        return 1
    elif is_bold and ratio >= 1.2:
        return 2
    elif is_bold:
        return 3
    elif ratio >= 1.6:
        return 2  # large font but not bold -> h2
    else:
        return None



__all__ = ["PageExtractor"]
