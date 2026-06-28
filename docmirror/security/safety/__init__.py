# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
AI Safety Layer (GA1.0-ODL-04)
================================

Inspects parsed document content for signs of manipulation before passing
it to LLM pipelines. Three independent detectors plus a Safety Aggregator.

Public API::

    from docmirror.security.safety import analyze_safety, sanitize, SafetyReport

    report = analyze_safety(full_text, text_blocks)
    safe_text = sanitize(full_text, strictness="medium")
    # report.sanitized, report.injection_risk, report.hidden_text_count, ...
"""

from __future__ import annotations

from typing import Any

from docmirror.security.safety.hidden_text import HiddenTextDetector, HiddenTextFlag
from docmirror.security.safety.zero_width import ZeroWidthDetector, ZeroWidthFlag
from docmirror.security.safety.injection import InjectionDetector, InjectionResult
from docmirror.security.safety.aggregator import SafetyAggregator, SafetyReport, SafetyStrictness

_aggregator: SafetyAggregator | None = None


def get_aggregator() -> SafetyAggregator:
    """Get or create the singleton SafetyAggregator."""
    global _aggregator
    if _aggregator is None:
        _aggregator = SafetyAggregator()
    return _aggregator


def analyze_safety(text: str, text_blocks: list[dict] | None = None) -> SafetyReport:
    """Run all safety detectors and return a unified report.

    Args:
        text: The full document text to analyze.
        text_blocks: Optional list of text block dicts (with bbox, bounding_box,
            opacities) for hidden text detection.

    Returns:
        SafetyReport with findings, risk scores, and sanitization status.
    """
    return get_aggregator().analyze(text, text_blocks=text_blocks)


def sanitize(text: str, *, strictness: str = "medium", text_blocks: list[dict] | None = None) -> str:
    """Sanitize document text at the given strictness level.

    Args:
        text: The full document text to sanitize.
        strictness: One of "off", "low", "medium", "high".
        text_blocks: Optional text block dicts for geometric hidden text detection.

    Returns:
        Sanitized text string.
    """
    return get_aggregator().sanitize(text, strictness=strictness, text_blocks=text_blocks)


__all__ = [
    "HiddenTextDetector",
    "HiddenTextFlag",
    "InjectionDetector",
    "InjectionResult",
    "SafetyAggregator",
    "SafetyReport",
    "SafetyStrictness",
    "ZeroWidthDetector",
    "ZeroWidthFlag",
    "analyze_safety",
    "sanitize",
]
