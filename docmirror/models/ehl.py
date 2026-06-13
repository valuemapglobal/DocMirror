# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""EHL helpers — map classification evidence to ParseResult annex (design 09 §4.5)."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from docmirror.models.entities.evidence import EvidenceSummary
from docmirror.models.entities.hypothesis import ParseHypothesis
from docmirror.models.entities.parse_result import MirrorAnnex, ParseResult


def evidence_items_to_hypotheses(
    evidence: Iterable[Any],
    *,
    selected_category: str,
    max_items: int = 100,
) -> list[ParseHypothesis]:
    """Map EvidenceEngine ``Evidence`` objects to ``ParseHypothesis`` annex entries."""
    hypotheses: list[ParseHypothesis] = []
    for i, ev in enumerate(evidence):
        if i >= max_items:
            break
        category = getattr(ev, "category", "")
        source = getattr(ev, "source", "unknown")
        weight = float(getattr(ev, "weight", 0.0) or 0.0)
        direction = int(getattr(ev, "direction", 1) or 1)
        detail = getattr(ev, "detail", "")
        hypotheses.append(
            ParseHypothesis(
                id=f"evidence_{i}",
                kind="document_type",
                payload={"category": category, "detail": detail, "direction": direction},
                confidence=weight if direction > 0 else max(0.0, 1.0 - weight),
                evidence_ids=[],
                method=source,
                selected=(category == selected_category),
            )
        )
    return hypotheses


def build_evidence_summary(evidence: Iterable[Any]) -> EvidenceSummary:
    by_source: Counter[str] = Counter()
    items = list(evidence)
    for ev in items:
        by_source[getattr(ev, "source", "unknown")] += 1
    return EvidenceSummary(
        total_spans=len(items),
        by_source=dict(by_source),
    )


def attach_classification_annex(
    result: ParseResult,
    evidence: Iterable[Any],
    *,
    selected_category: str,
) -> None:
    """Populate ``ParseResult.annex`` with EHL data (debug/eval; excluded from mirror.json)."""
    items = list(evidence)
    if result.annex is None:
        result.annex = MirrorAnnex()
    result.annex.hypotheses = evidence_items_to_hypotheses(
        items, selected_category=selected_category
    )
    result.annex.evidence_summary = build_evidence_summary(items)
