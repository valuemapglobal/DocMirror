# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Resolver base — shared scoring weights and decision types.

Purpose: Defines ``BaseResolver``, ``ResolverDecision``, and score weighting
used by all document-type candidate collectors.

Main components: ``BaseResolver``, ``ResolverScoreWeights``, ``compute_final_score``.

Upstream: Candidate evidence lists.

Downstream: ``resolution.document_type_resolver``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from docmirror.models.entities.hypothesis import ParseHypothesis


class ResolverScoreWeights(BaseModel):
    """Configurable resolver weights (defaults per execution plan)."""

    evidence_coverage: float = 0.30
    structure_consistency: float = 0.25
    semantic_plausibility: float = 0.15
    domain_fit: float = 0.15
    preservation_score: float = 0.10
    conflict_penalty: float = 0.20

    def apply_overrides(self, overrides: dict[str, float]) -> ResolverScoreWeights:
        data = self.model_dump()
        data.update({k: v for k, v in overrides.items() if k in data})
        return ResolverScoreWeights(**data)


class ResolverDecision(BaseModel):
    """Record of why a candidate was selected or rejected."""

    hypothesis_id: str
    kind: str
    selected: bool
    final_score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    reason: str = ""


def compute_final_score(
    scores: dict[str, float],
    weights: ResolverScoreWeights | None = None,
) -> float:
    """Compute weighted final score from dimension scores."""
    w = weights or ResolverScoreWeights()
    return (
        w.evidence_coverage * scores.get("evidence_coverage", 0)
        + w.structure_consistency * scores.get("structure_consistency", 0)
        + w.semantic_plausibility * scores.get("semantic_plausibility", 0)
        + w.domain_fit * scores.get("domain_fit", 0)
        + w.preservation_score * scores.get("preservation_score", 0)
        - w.conflict_penalty * scores.get("conflict_penalty", 0)
    )


class BaseResolver:
    """Shared resolver utilities."""

    def __init__(self, weights: ResolverScoreWeights | None = None):
        self.weights = weights or ResolverScoreWeights()

    def rank(
        self,
        candidates: list[ParseHypothesis],
        score_fn,
    ) -> tuple[list[ParseHypothesis], list[ResolverDecision]]:
        """Rank candidates by score_fn; mark winner as selected."""
        if not candidates:
            return [], []

        scored: list[tuple[ParseHypothesis, float, dict[str, float]]] = []
        for c in candidates:
            breakdown = score_fn(c)
            final = compute_final_score(breakdown, self.weights)
            scored.append((c, final, breakdown))

        scored.sort(key=lambda x: x[1], reverse=True)
        decisions: list[ResolverDecision] = []
        for i, (c, final, breakdown) in enumerate(scored):
            selected = i == 0
            c.selected = selected
            decisions.append(
                ResolverDecision(
                    hypothesis_id=c.id,
                    kind=c.kind,
                    selected=selected,
                    final_score=final,
                    score_breakdown=breakdown,
                    reason=f"rank={i + 1}/{len(scored)} method={c.method}",
                )
            )
        return [s[0] for s in scored], decisions
