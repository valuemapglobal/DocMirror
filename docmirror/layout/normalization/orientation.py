"""Orientation candidate scoring helpers."""

from __future__ import annotations

from typing import Any

from docmirror.layout.normalization.models import NormalizationCandidate


def candidate_from_metadata(metadata: dict[str, Any]) -> NormalizationCandidate:
    rotation = int(metadata.get("selected_rotation", metadata.get("ocr_rotation", 0)) or 0) % 360
    score = float(metadata.get("orientation_score", metadata.get("ocr_orientation_score", 1.0)) or 0.0)
    return NormalizationCandidate(
        rotation=rotation,
        deskew_angle=float(metadata.get("deskew_angle", 0.0) or 0.0),
        score=score,
        signals=orientation_comparison_signals(metadata),
    )


def orientation_comparison_signals(metadata: dict[str, Any]) -> dict[str, Any]:
    """Normalize orientation probe diagnostics without changing selection."""
    signal_keys = {
        "text_chars",
        "cjk_ratio",
        "keyword_hits",
        "numeric_tokens",
        "garbage_tokens",
        "early_keywords",
        "ocr_rotation",
        "ocr_orientation_score",
        "orientation_score",
        "normalized_page_width",
        "normalized_page_height",
    }
    signals = {key: value for key, value in metadata.items() if key in signal_keys}
    if "comparison_signals" in metadata and isinstance(metadata["comparison_signals"], dict):
        signals.update(metadata["comparison_signals"])
    if "orientation_candidates" in metadata and isinstance(metadata["orientation_candidates"], list):
        signals["orientation_candidates"] = [
            candidate for candidate in metadata["orientation_candidates"] if isinstance(candidate, dict)
        ]
    return signals
