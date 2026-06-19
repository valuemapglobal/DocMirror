# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Reasoning layer — read-only conflict explanation and audit narration.

Today DocMirror separates:
- EvidenceEngine → document type classification
- Validator → mirror parsing fidelity

This module is the extension point for cross-signal reasoning without
overloading Mirror facts or Edition projections. Reasoners must not mutate
``ParseResult`` or edition payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from docmirror.models.entities.parse_result import ParseResult


@dataclass
class ReasoningContext:
    """Inputs for a reasoning pass over Core ParseResult."""

    parse_result: ParseResult
    edition: str = "community"
    signals: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningOutcome:
    """Non-destructive reasoning output (applied to edition or domain_specific)."""

    revisions: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    confidence_adjustments: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ReasoningReport:
    """Read-only explanation report derived from Mirror + Edition payloads."""

    summary: str = ""
    conflicts: tuple[dict[str, Any], ...] = ()
    evidence_refs: tuple[str, ...] = ()
    review_actions: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "conflicts": list(self.conflicts),
            "evidence_refs": list(self.evidence_refs),
            "review_actions": list(self.review_actions),
            "risk_flags": list(self.risk_flags),
        }


class Reasoner(Protocol):
    def explain(self, mirror: ParseResult, editions: dict[str, Any] | None = None) -> ReasoningReport: ...

    def reason(self, ctx: ReasoningContext) -> ReasoningOutcome: ...


class NoOpReasoner:
    """Default reasoner until semantic conflict products are enabled."""

    def explain(self, _mirror: ParseResult, _editions: dict[str, Any] | None = None) -> ReasoningReport:
        return ReasoningReport()

    def reason(self, _ctx: ReasoningContext) -> ReasoningOutcome:
        return ReasoningOutcome()


_default_reasoner: Reasoner = NoOpReasoner()


def get_reasoner() -> Reasoner:
    return _default_reasoner


def set_reasoner(reasoner: Reasoner) -> None:
    global _default_reasoner
    _default_reasoner = reasoner


__all__ = [
    "NoOpReasoner",
    "Reasoner",
    "ReasoningContext",
    "ReasoningOutcome",
    "ReasoningReport",
    "get_reasoner",
    "set_reasoner",
]
