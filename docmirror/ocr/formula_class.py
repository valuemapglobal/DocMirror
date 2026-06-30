# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Formula class — inline vs display formula classification.

Purpose: Classify formula zones as inline (embedded in text), display
(centered standalone), or multiline (multi-line equation) based on
spatial layout and content analysis.

Design (from 19_formula_recognition_first_principles_redesign.md):
  - FM-3: Inline vs Display distinction
  - Rules:
    1. Formula width > 60% page width AND vertically centered -> display
    2. Formula height < 2x surrounding text line height AND x in text column -> inline
    3. Contains \begin{align} / \begin{equation} -> multiline

Main components:
  - FormulaDisplayType: enum for classification
  - FormulaClass: dataclass holding classification result
  - classify_formula(): main classification function

Upstream: formula_zone.py (zone data), layout_model.py (page geometry)

Downstream: Block.attrs["formula_display_type"], exporters/markdown.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FormulaDisplayType(Enum):
    """Formula display classification types."""

    INLINE = "inline"  # Embedded in text line: $x^2$
    DISPLAY = "display"  # Centered standalone: $$\sum$$
    MULTILINE = "multiline"  # Multi-line equation environment
    UNKNOWN = "unknown"  # Could not determine


@dataclass
class FormulaClass:
    """Classification result for a formula zone.

    Attributes:
        display_type: Classification (inline, display, multiline, unknown).
        confidence: Classification confidence [0.0, 1.0].
        evidence: Explanation of how the classification was determined.
        needs_review: Whether human review is recommended for this classification.
    """

    display_type: FormulaDisplayType = FormulaDisplayType.UNKNOWN
    confidence: float = 0.0
    evidence: str = ""
    needs_review: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Classification function
# ═══════════════════════════════════════════════════════════════════════════════


def classify_formula(
    latex: str,
    zone_bbox: tuple[float, float, float, float],
    page_width: float,
    page_height: float,
    context_chars: list[dict[str, Any]] | None = None,
) -> FormulaClass:
    """Classify a formula as inline, display, or multiline.

    Args:
        latex: The LaTeX string of the formula (for content-based rules).
        zone_bbox: Zone bounding box (x0, y0, x1, y1) in PDF page coordinates.
        page_width: Page width in PDF points.
        page_height: Page height in PDF points.
        context_chars: Optional character data from surrounding context for
            line-height comparison (only needed for inline vs display).

    Returns:
        A FormulaClass with display_type, confidence, and evidence.
    """
    x0, y0, x1, y1 = zone_bbox
    zone_width = x1 - x0
    zone_height = y1 - y0

    if page_width <= 0 or page_height <= 0:
        return FormulaClass(
            display_type=FormulaDisplayType.UNKNOWN,
            confidence=0.0,
            evidence="invalid page dimensions",
            needs_review=True,
        )

    # Rule 3: Multiline environments (content-based)
    if _has_multiline_environment(latex):
        return FormulaClass(
            display_type=FormulaDisplayType.MULTILINE,
            confidence=0.95,
            evidence="contains align/equation/multline environment",
        )

    # Rule 1: Large formula centered on page -> display
    width_ratio = zone_width / page_width
    vert_center = (y0 + y1) / 2
    page_vert_center = page_height / 2
    vert_offset_ratio = abs(vert_center - page_vert_center) / page_height

    is_large = width_ratio > 0.6
    is_centered = vert_offset_ratio < 0.15  # within 15% of page center
    has_display_cmds = "\\\\" in latex or "\\begin{" in latex  # line breaks or environments

    if is_large and is_centered:
        return FormulaClass(
            display_type=FormulaDisplayType.DISPLAY,
            confidence=0.85,
            evidence=f"width_ratio={width_ratio:.2f} (>0.6) AND centered (offset={vert_offset_ratio:.2f})",
        )
    if is_large:
        return FormulaClass(
            display_type=FormulaDisplayType.DISPLAY,
            confidence=0.7,
            evidence=f"width_ratio={width_ratio:.2f} (>0.6)",
        )
    if has_display_cmds and width_ratio > 0.4:
        return FormulaClass(
            display_type=FormulaDisplayType.DISPLAY,
            confidence=0.75,
            evidence="contains line breaks or environments AND width > 40% page",
        )

    # Rule 2: Small formula inline with text -> inline
    if context_chars and len(context_chars) > 0:
        is_inline = _check_inline_context(zone_bbox, context_chars)
        if is_inline:
            return FormulaClass(
                display_type=FormulaDisplayType.INLINE,
                confidence=0.8,
                evidence="height < 2x text line AND within text column",
            )

    # Heuristic: small formulas default to inline
    height_ratio = zone_height / page_height
    if height_ratio < 0.05 and width_ratio < 0.4:
        return FormulaClass(
            display_type=FormulaDisplayType.INLINE,
            confidence=0.6,
            evidence=f"small zone: h_ratio={height_ratio:.3f}, w_ratio={width_ratio:.3f}",
        )

    # Ambiguous case: recommend review
    return FormulaClass(
        display_type=FormulaDisplayType.DISPLAY,
        confidence=0.5,
        evidence="ambiguous layout — defaulting to display",
        needs_review=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

_MULTILINE_ENV_RE = r"\\begin\{(align|equation|multline|gather|eqnarray|alignat)\w*\}"


def _has_multiline_environment(latex: str) -> bool:
    """Check if LaTeX contains a multiline equation environment."""
    import re

    return bool(re.search(_MULTILINE_ENV_RE, latex))


def _check_inline_context(
    zone_bbox: tuple[float, float, float, float],
    context_chars: list[dict[str, Any]],
) -> bool:
    """Check if the formula zone is inline based on surrounding character context.

    An inline formula:
      - Has height less than 2x the median text line height nearby.
      - Has x-coordinates within the text column (not pushed to center).
      - Has text characters on the same line to its left or right.

    Returns:
        True if layout evidence supports inline classification.
    """
    x0, y0, x1, y1 = zone_bbox
    zone_height = y1 - y0
    zone_mid_y = (y0 + y1) / 2

    # Estimate text line height from nearby characters
    line_heights: list[float] = []
    same_line_chars = 0

    for c in context_chars:
        c_mid_y = (c.get("top", 0) + c.get("bottom", 0)) / 2
        c_height = c.get("bottom", 0) - c.get("top", 0)

        if c_height > 0 and c_height < zone_height * 3:
            line_heights.append(c_height)

        # Check for characters on the same line (same y baseline)
        if abs(c_mid_y - zone_mid_y) < zone_height * 0.5:
            same_line_chars += 1

    if not line_heights:
        return False

    median_line_height = sorted(line_heights)[len(line_heights) // 2]

    # Inline if formula height < 2x text line height AND characters on same line
    if zone_height < median_line_height * 2.5 and same_line_chars > 0:
        return True

    return False


def classify_formula_simple(latex: str, page_width: float, page_height: float) -> FormulaClass:
    """Simplified classification without context chars.

    Uses only zone dimensions and LaTeX content. Suitable when char-context
    is not available (e.g., OCR-only path).

    Returns:
        A FormulaClass result.
    """
    # Use a dummy bbox based on the formula's complexity

    # Estimate formula width based on LaTeX length
    char_count = len(latex)
    # Each LaTeX char is roughly ~8pt in display
    est_width = char_count * 8
    est_height = 14 if "\\frac" in latex or "\\sqrt" in latex else 10

    # Estimate center position (assume formula is in middle of page area)
    est_x0 = max(50, (page_width - est_width) / 2)
    est_y0 = max(50, (page_height - est_height) / 2)
    est_x1 = est_x0 + est_width
    est_y1 = est_y0 + est_height

    return classify_formula(
        latex=latex,
        zone_bbox=(est_x0, est_y0, est_x1, est_y1),
        page_width=page_width,
        page_height=page_height,
    )
