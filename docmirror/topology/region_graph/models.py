"""Internal RegionGraph models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RegionCandidate:
    candidate_id: str
    page_id: str
    kind: str
    role_hint: str = ""
    bbox: list[float] | None = None
    evidence_ids: list[str] = field(default_factory=list)
    detector: str = ""
    confidence: float = 1.0
    features: dict[str, Any] = field(default_factory=dict)
    competing_candidate_ids: list[str] = field(default_factory=list)
    parent_candidate_ids: list[str] = field(default_factory=list)
    child_candidate_ids: list[str] = field(default_factory=list)
    selected_region_id: str = ""
    source_region_ids: list[str] = field(default_factory=list)
    merged_candidate_ids: list[str] = field(default_factory=list)
    merge_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "page_id": self.page_id,
            "kind": self.kind,
            "role_hint": self.role_hint,
            "bbox": self.bbox,
            "evidence_ids": list(self.evidence_ids),
            "detector": self.detector,
            "confidence": float(self.confidence),
            "features": dict(self.features),
            "competing_candidate_ids": list(self.competing_candidate_ids),
            "parent_candidate_ids": list(self.parent_candidate_ids),
            "child_candidate_ids": list(self.child_candidate_ids),
            "selected_region_id": self.selected_region_id,
            "source_region_ids": list(self.source_region_ids),
            "merged_candidate_ids": list(self.merged_candidate_ids),
            "merge_reason": self.merge_reason,
        }


@dataclass(frozen=True)
class OwnershipLedger:
    owned: dict[str, str] = field(default_factory=dict)
    nested: dict[str, list[str]] = field(default_factory=dict)
    overlay: dict[str, str] = field(default_factory=dict)
    suppressed_noise: list[str] = field(default_factory=list)
    residual: list[str] = field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "owned": dict(self.owned),
            "nested": {key: list(value) for key, value in self.nested.items()},
            "overlay": dict(self.overlay),
            "suppressed_noise": list(self.suppressed_noise),
            "residual": list(self.residual),
            "rejected_candidates": [dict(item) for item in self.rejected_candidates],
        }


@dataclass(frozen=True)
class RegionGraph:
    page_id: str
    candidates: list[RegionCandidate] = field(default_factory=list)
    ownership: OwnershipLedger = field(default_factory=OwnershipLedger)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_diagnostics(self) -> dict[str, Any]:
        kind_counts: dict[str, int] = {}
        detector_counts: dict[str, int] = {}
        for candidate in self.candidates:
            kind_counts[candidate.kind] = kind_counts.get(candidate.kind, 0) + 1
            detector_counts[candidate.detector] = detector_counts.get(candidate.detector, 0) + 1
        return {
            "type": "region_graph",
            "page_id": self.page_id,
            "candidate_count": len(self.candidates),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "candidate_kind_counts": kind_counts,
            "detector_counts": detector_counts,
            "ownership": self.ownership.to_dict(),
            **dict(self.diagnostics),
        }
