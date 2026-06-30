# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Safety Aggregator — Coordinates all detectors into a unified safety layer.

The ``SafetyAggregator`` runs Hidden Text, Zero-Width, and Injection
detectors in sequence and produces a single ``SafetyReport``. The
``sanitize()`` method applies strictness-dependent transformations
to produce a clean text payload safe for LLM consumption.

Strictness levels::

    "off":      Pass-through, no detection, no sanitization.
    "low":      Detect only — report findings, no auto-sanitize.
    "medium":   Remove zero-width chars + flag hidden text + flag injections.
    "high":     Remove hidden text + zero-width chars + flag injections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from docmirror.security.safety.hidden_text import HiddenTextDetector, HiddenTextFlag
from docmirror.security.safety.injection import InjectionDetector, InjectionResult
from docmirror.security.safety.zero_width import ZeroWidthDetector, ZeroWidthFlag

# ── Strictness ────────────────────────────────────────────────────────────


class SafetyStrictness(str, Enum):
    """Safety strictness level controlling auto-sanitize behaviour."""

    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── Report ────────────────────────────────────────────────────────────────


@dataclass
class SafetyReport:
    """Unified safety report from all detectors."""

    sanitized: bool = False
    hidden_text_count: int = 0
    hidden_text_flags: list[HiddenTextFlag] = field(default_factory=list)
    zero_width_count: int = 0
    zero_width_flags: list[ZeroWidthFlag] = field(default_factory=list)
    injection_risk: float = 0.0
    injection_matched_patterns: list[str] = field(default_factory=list)
    injection_result: InjectionResult | None = None
    strictness_applied: str = "off"
    blocks_removed: int = 0
    chars_removed: int = 0

    @property
    def has_findings(self) -> bool:
        """Returns ``True`` if any detector found suspicious content."""
        return self.hidden_text_count > 0 or self.zero_width_count > 0 or self.injection_risk > 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialise report to a plain dict for evidence-ledger use."""
        return {
            "sanitized": self.sanitized,
            "hidden_text_found": self.hidden_text_count > 0,
            "hidden_text_blocks": self.hidden_text_count,
            "zero_width_chars_found": self.zero_width_count > 0,
            "zero_width_chars": [f.char_name for f in self.zero_width_flags],
            "injection_risk_score": self.injection_risk,
            "injection_patterns_matched": self.injection_matched_patterns,
            "strictness_applied": self.strictness_applied,
            "blocks_removed": self.blocks_removed,
            "chars_removed": self.chars_removed,
        }


# ── Aggregator ────────────────────────────────────────────────────────────


class SafetyAggregator:
    """Orchestrate all safety detectors and produce a unified result.

    Usage::

        aggregator = SafetyAggregator()

        # Analyse without modifying
        report = aggregator.analyze(full_text, text_blocks=blocks)
        if report.has_findings:
            print(f"Injection risk: {report.injection_risk}")

        # Sanitise at a given strictness
        safe_text = aggregator.sanitize(full_text, strictness="medium")
    """

    def __init__(
        self,
        hidden_text_detector: HiddenTextDetector | None = None,
        zero_width_detector: ZeroWidthDetector | None = None,
        injection_detector: InjectionDetector | None = None,
    ):
        self.hidden_text = hidden_text_detector or HiddenTextDetector()
        self.zero_width = zero_width_detector or ZeroWidthDetector()
        self.injection = injection_detector or InjectionDetector()

    def analyze(
        self,
        text: str,
        *,
        text_blocks: list[dict[str, Any]] | None = None,
    ) -> SafetyReport:
        """Run all detectors and return a unified safety report.

        This is a **read-only** analysis — no text is modified.

        Args:
            text: The full document text to analyse.
            text_blocks: Optional list of text block dicts (with ``bbox``,
                ``text_opacity``, etc.) for geometric hidden-text detection.

        Returns:
            ``SafetyReport`` with findings from all detectors.
        """
        # 1. Hidden text
        hidden_flags: list[HiddenTextFlag] = []
        if text_blocks is not None:
            hidden_flags = self.hidden_text.detect(text_blocks)

        # 2. Zero-width chars
        zw_flags = self.zero_width.detect(text)

        # 3. Injection patterns
        injection_result = self.injection.evaluate(text)

        return SafetyReport(
            sanitized=False,
            hidden_text_count=len(hidden_flags),
            hidden_text_flags=hidden_flags,
            zero_width_count=len(zw_flags),
            zero_width_flags=zw_flags,
            injection_risk=injection_result.risk_score,
            injection_matched_patterns=injection_result.matched_patterns,
            injection_result=injection_result,
            strictness_applied="off",
            blocks_removed=0,
            chars_removed=0,
        )

    def sanitize(
        self,
        text: str,
        *,
        strictness: str = "medium",
        text_blocks: list[dict[str, Any]] | None = None,
    ) -> str:
        """Sanitise document text at the given strictness level.

        Args:
            text: The full document text to sanitise.
            strictness: One of ``"off"``, ``"low"``, ``"medium"``,
                ``"high"``.
            text_blocks: Optional text block dicts for geometric hidden-text
                detection.

        Returns:
            Sanitised (or original) text string.
        """
        strictness_enum = SafetyStrictness(strictness)

        if strictness_enum == SafetyStrictness.OFF:
            return text  # pass-through

        safe_text = text

        # Low: detection only — no modifications
        if strictness_enum == SafetyStrictness.LOW:
            return text

        # Medium: remove zero-width chars
        if strictness_enum in (SafetyStrictness.MEDIUM, SafetyStrictness.HIGH):
            safe_text = self.zero_width.sanitize(safe_text, mode="remove")

        # High: also remove hidden text blocks
        if strictness_enum == SafetyStrictness.HIGH and text_blocks is not None:
            visible_blocks = self.hidden_text.sanitize(text_blocks)
            # Reconstruct text from visible blocks only
            safe_text = "\n".join(b.get("content", "") for b in visible_blocks)

        return safe_text

    def analyze_and_sanitize(
        self,
        text: str,
        *,
        strictness: str = "medium",
        text_blocks: list[dict[str, Any]] | None = None,
    ) -> tuple[SafetyReport, str]:
        """Analyse and sanitise in one call.

        Args:
            Same as ``sanitize()``.

        Returns:
            ``(SafetyReport, sanitized_text)``.
        """
        report = self.analyze(text, text_blocks=text_blocks)
        safe_text = self.sanitize(text, strictness=strictness, text_blocks=text_blocks)

        # Update report with sanitisation metadata
        report.sanitized = safe_text != text
        report.strictness_applied = strictness
        report.blocks_removed = len(text_blocks) - len(text.split("\n")) if text_blocks and strictness == "high" else 0
        original_len = len(text)
        safe_len = len(safe_text)
        report.chars_removed = max(0, original_len - safe_len)

        return report, safe_text


__all__ = [
    "SafetyAggregator",
    "SafetyReport",
    "SafetyStrictness",
]
