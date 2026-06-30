# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Safety Service — bridges the SafetyAggregator into the document pipeline.

This service is the integration point between the core perception pipeline
and the AI safety layer (GA1.0-ODL-04). It:

1. Extracts ``full_text`` and ``text_blocks`` from a ``ParseResult``.
2. Runs the ``SafetyAggregator`` with the configured strictness.
3. Returns a safety report and optionally sanitised text.
4. Integrates with the evidence ledger for auditability.

Usage::

    from docmirror.security.safety.service import run_safety_pipeline

    report, safe_text = run_safety_pipeline(parse_result, mode="medium")
    if report.has_findings:
        logger.warning("Safety findings: %d hidden, %d zero-width, injection risk %.2f",
                       report.hidden_text_count, report.zero_width_count, report.injection_risk)
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.security.safety import SafetyAggregator, SafetyReport

logger = logging.getLogger(__name__)


def _extract_text_blocks(result: ParseResult) -> list[dict[str, Any]]:
    """Extract text blocks from a ParseResult as plain dicts.

    Converts Pydantic TextBlock models into the plain-dict format
    the HiddenTextDetector expects (keys: ``content``, ``bbox``).

    Args:
        result: The parse result to extract blocks from.

    Returns:
        List of dicts with at least ``content`` and optionally ``bbox``.
    """
    blocks: list[dict[str, Any]] = []
    for page in result.pages:
        for text_block in page.texts:
            block: dict[str, Any] = {
                "content": text_block.content,
            }
            if text_block.bbox is not None:
                block["bbox"] = text_block.bbox
            blocks.append(block)
    return blocks


def run_safety_pipeline(
    result: ParseResult,
    mode: str = "medium",
) -> tuple[SafetyReport, str]:
    """Run the full safety pipeline on a ParseResult.

    Args:
        result: The parsed document result.
        mode: Safety strictness — ``"off"``, ``"low"``, ``"medium"``, or ``"high"``.

    Returns:
        ``(SafetyReport, sanitized_text)``.
    """
    if mode == "off":
        return SafetyReport(strictness_applied="off"), getattr(result, "full_text", "") or ""

    full_text = getattr(result, "full_text", "") or ""
    text_blocks = _extract_text_blocks(result)

    aggregator = SafetyAggregator()
    report, safe_text = aggregator.analyze_and_sanitize(
        full_text,
        strictness=mode,
        text_blocks=text_blocks,
    )
    return report, safe_text


def build_safety_evidence(
    report: SafetyReport,
) -> dict[str, Any]:
    """Build the safety section for the evidence ledger from a SafetyReport.

    Args:
        report: The safety report from the pipeline.

    Returns:
        Dict suitable for inclusion in the evidence ledger.
    """
    return {
        "safety": {
            "sanitized": report.sanitized,
            "hidden_text_found": report.hidden_text_count > 0,
            "hidden_text_blocks": report.hidden_text_count,
            "zero_width_chars_found": report.zero_width_count > 0,
            "zero_width_chars": [f.char_name for f in report.zero_width_flags],
            "injection_risk_score": round(report.injection_risk, 4),
            "injection_patterns_matched": report.injection_matched_patterns,
            "strictness_applied": report.strictness_applied,
            "blocks_removed": report.blocks_removed,
            "chars_removed": report.chars_removed,
        }
    }


build_safety_ledger = build_safety_evidence


__all__ = [
    "build_safety_evidence",
    "build_safety_ledger",
    "run_safety_pipeline",
]
