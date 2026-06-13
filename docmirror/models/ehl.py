# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""EHL helpers — map classification evidence to ParseResult annex (design 09 §4.5)."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from docmirror.models.entities.evidence import EvidenceSummary
from docmirror.models.entities.hypothesis import ParseHypothesis
from docmirror.models.entities.parse_result import MirrorAnnex, ParseResult


def spans_to_evidence_summary(spans: Iterable[Any]) -> EvidenceSummary:
    """Build ``EvidenceSummary`` from layout/OCR ``EvidenceSpan`` objects."""
    items = list(spans)
    by_source: Counter[str] = Counter()
    by_page: Counter[int] = Counter()
    span_ids: list[str] = []
    for span in items:
        span_ids.append(str(getattr(span, "id", "") or (span.get("id") if isinstance(span, dict) else "")))
        source = getattr(span, "source", None) or (span.get("source") if isinstance(span, dict) else "unknown")
        page = getattr(span, "page", None) or (span.get("page") if isinstance(span, dict) else 0)
        by_source[str(source)] += 1
        if page:
            by_page[int(page)] += 1
    return EvidenceSummary(
        total_spans=len(items),
        span_ids=[s for s in span_ids if s],
        by_source=dict(by_source),
        by_page=dict(by_page),
    )


def attach_spans_annex(result: ParseResult, spans: Iterable[Any]) -> None:
    """Merge crop/layout evidence spans into ``ParseResult.annex.evidence_summary``."""
    items = list(spans)
    if not items:
        return
    if result.annex is None:
        result.annex = MirrorAnnex()
    crop_summary = spans_to_evidence_summary(items)
    if result.annex.evidence_summary is None:
        result.annex.evidence_summary = crop_summary
    else:
        existing = result.annex.evidence_summary
        merged_ids = list(dict.fromkeys([*(existing.span_ids or []), *(crop_summary.span_ids or [])]))
        merged_by_source = dict(existing.by_source or {})
        for k, v in (crop_summary.by_source or {}).items():
            merged_by_source[k] = merged_by_source.get(k, 0) + v
        merged_by_page = dict(existing.by_page or {})
        for k, v in (crop_summary.by_page or {}).items():
            merged_by_page[k] = merged_by_page.get(k, 0) + v
        result.annex.evidence_summary = EvidenceSummary(
            total_spans=max(existing.total_spans, crop_summary.total_spans),
            span_ids=merged_ids,
            by_source=merged_by_source,
            by_page=merged_by_page,
        )


def attach_pipeline_debug(result: ParseResult, key: str, value: Any) -> None:
    """Store middleware/orchestrator debug payloads on ``ParseResult.annex``."""
    if result.annex is None:
        result.annex = MirrorAnnex()
    result.annex.pipeline_debug[key] = value


def attach_quality_report_annex(result: ParseResult, report: Any) -> None:
    """Attach eval ``ParseQualityReport`` to ``ParseResult.annex`` (benchmark CLI)."""
    if result.annex is None:
        result.annex = MirrorAnnex()
    result.annex.quality_report = report


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
