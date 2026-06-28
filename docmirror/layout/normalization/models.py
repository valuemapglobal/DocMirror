"""Data models for UDTR page normalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NormalizationCandidate:
    """A candidate page display orientation or transform."""

    rotation: int = 0
    deskew_angle: float = 0.0
    score: float = 1.0
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rotation": int(self.rotation) % 360,
            "deskew_angle": float(self.deskew_angle),
            "score": float(self.score),
            "signals": dict(self.signals),
        }


@dataclass(frozen=True)
class NormalizationTrace:
    """Canonical page-level coordinate normalization trace."""

    page_id: str
    source_width: float = 0.0
    source_height: float = 0.0
    display_width: float = 0.0
    display_height: float = 0.0
    source_rotation: int = 0
    selected_content_rotation: int = 0
    deskew_angle: float = 0.0
    scale: float = 1.0
    matrix: list[list[float]] = field(default_factory=list)
    inverse_matrix: list[list[float]] = field(default_factory=list)
    candidates: list[NormalizationCandidate] = field(default_factory=list)
    selected_reason: str = "identity"
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "source_width": float(self.source_width),
            "source_height": float(self.source_height),
            "display_width": float(self.display_width),
            "display_height": float(self.display_height),
            "source_rotation": int(self.source_rotation) % 360,
            "selected_content_rotation": int(self.selected_content_rotation) % 360,
            "deskew_angle": float(self.deskew_angle),
            "scale": float(self.scale),
            "matrix": self.matrix,
            "inverse_matrix": self.inverse_matrix,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "selected_reason": self.selected_reason,
            "confidence": float(self.confidence),
        }
