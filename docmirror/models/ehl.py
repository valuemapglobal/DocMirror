# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Evidence and Hypothesis Layer (EHL) helpers — classification annex for ``ParseResult``.

Bridges EvidenceEngine outputs (``EvidenceSpan``, ``Evidence`` objects) into the
``ParseResult.annex`` field for debug, evaluation, and audit. Annex data is
excluded from ``mirror.json`` serialization.

Functions::

    spans_to_evidence_summary()      Aggregate layout/OCR spans into ``EvidenceSummary``
    attach_spans_annex()             Merge crop/layout evidence into annex
    attach_pipeline_debug()          Store middleware debug payloads by key
    attach_quality_report_annex()    Attach eval ``ParseQualityReport``
    evidence_items_to_hypotheses()   Map EvidenceEngine items → ``ParseHypothesis`` list
    build_evidence_summary()         Lightweight summary from evidence iterables
    attach_classification_annex()  Populate hypotheses + evidence_summary on annex

See design 09 §4.5 for the EHL annex contract.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from docmirror.models.entities.evidence import EvidenceSummary
from docmirror.models.entities.hypothesis import MergeHypothesis, ParseHypothesis, TableHypothesis
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
    result.annex.hypotheses = evidence_items_to_hypotheses(items, selected_category=selected_category)
    result.annex.evidence_summary = build_evidence_summary(items)


def summarize_parse_result_evidence(result: ParseResult) -> EvidenceSummary:
    """Build a lightweight physical evidence summary from committed Mirror blocks."""
    by_source: Counter[str] = Counter()
    by_page: Counter[int] = Counter()
    span_ids: list[str] = []

    def _source_from_ids(ids: list[str], default: str) -> str:
        if any(str(s).startswith("ocr_") for s in ids):
            return "ocr"
        if any(str(s).startswith("text_") for s in ids):
            return "pdf_text"
        if any(str(s).startswith("kv_") for s in ids):
            return "derived"
        return default

    def _record(ids: list[str], *, page_no: int, source: str) -> None:
        count = max(1, len(ids))
        by_source[source] += count
        if page_no:
            by_page[page_no] += count
        span_ids.extend(ids)

    for page in result.pages:
        page_no = int(getattr(page, "page_number", 0) or 0)
        for idx, text in enumerate(page.texts):
            ids = list(getattr(text, "evidence_ids", None) or [])
            ids = ids or [f"text_p{page_no}_{idx}"]
            _record(ids, page_no=page_no, source=_source_from_ids(ids, "pdf_text"))
        for idx, table in enumerate(page.tables):
            source = getattr(table, "extraction_layer", "") or "mirror_table"
            ids = list(getattr(table, "evidence_ids", None) or [])
            ids = ids or [getattr(table, "table_id", "") or f"table_p{page_no}_{idx}"]
            _record(ids, page_no=page_no, source=str(source))
        for idx, kv in enumerate(page.key_values):
            ids = list(getattr(kv, "evidence_ids", None) or [])
            ids = ids or [f"kv_p{page_no}_{idx}"]
            _record(ids, page_no=page_no, source=_source_from_ids(ids, "derived"))

    unique_ids = list(dict.fromkeys([s for s in span_ids if s]))

    return EvidenceSummary(
        total_spans=len(unique_ids),
        span_ids=unique_ids,
        by_source=dict(by_source),
        by_page=dict(by_page),
    )


def attach_parse_result_evidence_summary(result: ParseResult) -> None:
    """Attach a lightweight evidence summary derived from current Mirror blocks."""
    summary = summarize_parse_result_evidence(result)
    if summary.total_spans <= 0:
        return
    if result.annex is None:
        result.annex = MirrorAnnex()
    if result.annex.evidence_summary is None:
        result.annex.evidence_summary = summary
        return
    existing = result.annex.evidence_summary
    merged_ids = list(dict.fromkeys([*(existing.span_ids or []), *(summary.span_ids or [])]))
    by_source = dict(existing.by_source or {})
    for key, value in (summary.by_source or {}).items():
        by_source[key] = int(by_source.get(key, 0)) + int(value)
    by_page = dict(existing.by_page or {})
    for key, value in (summary.by_page or {}).items():
        by_page[int(key)] = int(by_page.get(key, 0)) + int(value)
    result.annex.evidence_summary = EvidenceSummary(
        total_spans=max(int(existing.total_spans or 0), int(summary.total_spans or 0)),
        span_ids=merged_ids,
        by_source=by_source,
        by_page=by_page,
    )


def build_mirror_hypotheses(result: ParseResult, *, max_items: int = 100) -> list[ParseHypothesis]:
    """Derive production EHL hypotheses from SPE, physical tables, and merge audit."""
    hypotheses: list[ParseHypothesis] = []
    structure = getattr(getattr(result, "parser_info", None), "structure", None) or {}
    competitors = structure.get("competitors") if isinstance(structure, dict) else None
    primary = structure.get("primary") if isinstance(structure, dict) else None

    if isinstance(competitors, dict):
        for idx, (name, score) in enumerate(sorted(competitors.items())):
            if len(hypotheses) >= max_items:
                return hypotheses
            kind = "table" if "pipe" in str(name).lower() or "table" in str(name).lower() else "section"
            hypotheses.append(
                ParseHypothesis(
                    id=f"sso_{idx}_{name}",
                    kind=kind,
                    payload={"competitor": name, "primary": primary},
                    confidence=float(score or 0.0),
                    method="sso",
                    selected=bool(primary and str(primary) in str(name)),
                )
            )

    annex = getattr(result, "annex", None)
    pipeline_debug = getattr(annex, "pipeline_debug", None) if annex else None
    extraction_audit = (pipeline_debug or {}).get("extraction_audit") if isinstance(pipeline_debug, dict) else None
    pages_audit = extraction_audit.get("pages") if isinstance(extraction_audit, dict) else None
    if isinstance(pages_audit, list):
        for page_idx, page_audit in enumerate(pages_audit):
            if not isinstance(page_audit, dict):
                continue
            picked = str(page_audit.get("picked") or "")
            picked_score = float(page_audit.get("score") or 0.0)
            page_no = int(page_audit.get("page") or page_idx + 1)
            candidates = page_audit.get("candidates") or []
            for cand_idx, cand in enumerate(candidates):
                if len(hypotheses) >= max_items:
                    return hypotheses
                if not isinstance(cand, dict):
                    continue
                layer = str(cand.get("layer") or "unknown")
                selected = bool(layer == picked)
                hypotheses.append(
                    TableHypothesis(
                        id=f"bcs_p{page_no}_{cand_idx}_{layer}",
                        payload={
                            "page": page_no,
                            "layer": layer,
                            "picked": picked,
                            "score": picked_score if selected else None,
                            "source": "extraction_audit",
                        },
                        confidence=float(cand.get("conf") or (picked_score if selected else 0.0) or 0.0),
                        method="bcs",
                        selected=selected,
                        structure_score=picked_score if selected else 0.0,
                        layer=layer,
                        row_count=int(cand.get("rows") or 0),
                        col_count=int(cand.get("cols") or 0),
                    )
                )

    for page in result.pages:
        for idx, table in enumerate(page.tables):
            if len(hypotheses) >= max_items:
                return hypotheses
            table_id = table.table_id or f"pt_{page.page_number}_{idx}"
            hypotheses.append(
                TableHypothesis(
                    id=f"table_{table_id}",
                    payload={
                        "table_id": table_id,
                        "page": table.page or page.page_number,
                        "bbox": table.bbox,
                    },
                    confidence=float(
                        table.extraction_confidence if table.extraction_confidence is not None else table.confidence
                    ),
                    evidence_ids=list(table.evidence_ids or []),
                    method=table.extraction_layer or "mirror_physical_table",
                    selected=True,
                    structure_score=float(table.confidence or 0.0),
                    layer=table.extraction_layer or "",
                    row_count=int(table.row_count or 0),
                    col_count=len(table.headers or []),
                )
            )

    for idx, op in enumerate(result.table_operations):
        if len(hypotheses) >= max_items:
            return hypotheses
        logical_id = getattr(op, "logical_id", "") or f"merge_{idx}"
        hypotheses.append(
            MergeHypothesis(
                id=f"merge_{logical_id}",
                payload={
                    "logical_id": logical_id,
                    "merge_method": getattr(op, "merge_method", ""),
                    "quality_passed": getattr(op, "quality_passed", True),
                    "quality_skip_reason": getattr(op, "quality_skip_reason", None),
                },
                confidence=float(getattr(op, "merge_confidence", 0.0) or 0.0),
                method=getattr(op, "merge_method", "") or "table_composer",
                selected=bool(getattr(op, "quality_passed", True)),
                source_table_ids=list(getattr(op, "source_physical_ids", None) or []),
                target_page_span=list(getattr(op, "source_pages", None) or []),
                continuity_score=float(getattr(op, "merge_confidence", 0.0) or 0.0),
            )
        )

    return hypotheses


def attach_mirror_hypotheses(result: ParseResult, *, max_items: int = 100) -> None:
    """Attach derived Mirror hypotheses without replacing existing annex entries."""
    hypotheses = build_mirror_hypotheses(result, max_items=max_items)
    if not hypotheses:
        return
    if result.annex is None:
        result.annex = MirrorAnnex()
    existing = list(result.annex.hypotheses or [])
    by_id = {h.id: h for h in existing}
    for hypothesis in hypotheses:
        by_id.setdefault(hypothesis.id, hypothesis)
    result.annex.hypotheses = list(by_id.values())[:max_items]


def attach_quarantine_annex(result: ParseResult) -> None:
    """Mirror SPE quarantine details into the unified EHL annex."""
    structure = getattr(getattr(result, "parser_info", None), "structure", None) or {}
    if not isinstance(structure, dict):
        return
    physical = structure.get("quarantined_physical_tables") or []
    logical = structure.get("quarantined_logical_tables_annex") or []
    if not physical and not logical:
        return
    if result.annex is None:
        result.annex = MirrorAnnex()
    result.annex.quarantine = {
        "physical_count": int(structure.get("quarantined_physical_count") or len(physical) or 0),
        "logical_count": int(structure.get("quarantined_logical_count") or len(logical) or 0),
        "physical": list(physical),
        "logical": list(logical),
    }


def ensure_mirror_annex(result: ParseResult) -> None:
    """Populate lightweight production EHL annex fields from current Mirror state."""
    attach_parse_result_evidence_summary(result)
    attach_mirror_hypotheses(result)
    attach_quarantine_annex(result)
