# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evidence-gated local repair contracts.

These dataclasses describe repair intent and evidence.  They deliberately do
not decide domain truth: OCR produces candidates, while domain solvers decide
whether a candidate can be adopted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RepairStatus = Literal["adopted", "needs_review", "rejected", "not_applicable"]
RepairAction = Literal["auto_adopt", "manual_review", "reject", "none"]


@dataclass(frozen=True)
class RepairRequest:
    """A request to revisit a local source-image region."""

    request_id: str
    domain: str
    kind: str
    page_number: int | None = None
    page_id: str = ""
    bbox: tuple[float, float, float, float] | None = None
    expected_schema: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""

    @property
    def can_render(self) -> bool:
        return self.page_number is not None and self.bbox is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "domain": self.domain,
            "kind": self.kind,
            "page_number": self.page_number,
            "page_id": self.page_id,
            "bbox": list(self.bbox) if self.bbox else None,
            "expected_schema": list(self.expected_schema),
            "constraints": list(self.constraints),
            "context": dict(self.context),
            "evidence_ids": list(self.evidence_ids),
            "reason": self.reason,
            "can_render": self.can_render,
        }


@dataclass(frozen=True)
class RepairCandidate:
    """A local repair candidate produced from evidence."""

    candidate_id: str
    request_id: str
    text: str
    confidence: float
    source: str
    fields: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "request_id": self.request_id,
            "text": self.text,
            "confidence": self.confidence,
            "source": self.source,
            "fields": dict(self.fields),
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class RepairDecision:
    """Domain-level decision over repair candidates."""

    request_id: str
    status: RepairStatus
    action: RepairAction
    selected_candidate_id: str = ""
    score: float = 0.0
    reasons: tuple[str, ...] = ()
    candidates: tuple[RepairCandidate, ...] = ()

    @property
    def adopted(self) -> bool:
        return self.status == "adopted" and self.action == "auto_adopt"

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "action": self.action,
            "selected_candidate_id": self.selected_candidate_id,
            "score": self.score,
            "reasons": list(self.reasons),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


__all__ = [
    "RepairAction",
    "RepairCandidate",
    "RepairDecision",
    "RepairRequest",
    "RepairStatus",
]
