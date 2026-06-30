# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Quality Decision Report v2 — auto-ingest / needs-review / reject engine.

GA 1.0 design SS5.6 / SS9 Wave 3: Consumes the Visual Evidence Graph,
Source Span Ledger, Outcome Ledger, and confidence policy to produce a
single machine-actionable decision with reasons, blocking issues, and
links back to visual evidence.

Usage::

    from docmirror.evidence.quality_decision import build_quality_decision
    decision = build_quality_decision(
        visual_graph=graph,
        source_span_ledger=ledger,
        outcome_ledger=outcomes,
        confidence_policy="ga_default_v1",
    )
    print(decision.to_dict())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Decision = Literal["auto_ingest", "needs_review", "reject"]


@dataclass
class ReviewItem:
    """A single item flagged for human review."""

    scope: str = "field"
    field_path: str = ""
    node_id: str = ""
    reason: str = ""
    confidence: float = 0.0
    page: int = 0
    bbox: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "field_path": self.field_path,
            "node_id": self.node_id,
            "reason": self.reason,
            "confidence": self.confidence,
            "page": self.page,
            "bbox": self.bbox,
        }


@dataclass
class QualityDecisionReport:
    """GA 1.0 Quality Decision Report v2.

    Replaces static quality claims with observed metrics, confidence
    policy evaluation, and an unambiguous machine-actionable decision.
    """

    version: int = 2
    document_id: str = ""
    task_id: str = ""

    decision: Decision = "needs_review"
    decision_reason: str = ""
    confidence_policy: str = "ga_default_v1"

    summary: dict[str, str] = field(
        default_factory=lambda: {
            "text_fidelity": "not_measured",
            "layout_fidelity": "not_measured",
            "business_fidelity": "not_measured",
            "audit_fidelity": "not_measured",
        }
    )

    blocking_issues: list[dict[str, Any]] = field(default_factory=list)
    needs_review: list[ReviewItem] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    links: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "document_id": self.document_id,
            "task_id": self.task_id,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "confidence_policy": self.confidence_policy,
            "summary": self.summary,
            "blocking_issues": self.blocking_issues,
            "needs_review": [r.to_dict() for r in self.needs_review],
            "metrics": self.metrics,
            "links": self.links,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QualityDecisionReport:
        report = cls(
            version=data.get("version", 2),
            document_id=data.get("document_id", ""),
            task_id=data.get("task_id", ""),
            decision=data.get("decision", "needs_review"),
            decision_reason=data.get("decision_reason", ""),
            confidence_policy=data.get("confidence_policy", "ga_default_v1"),
            summary=data.get("summary", {}),
            blocking_issues=data.get("blocking_issues", []),
            metrics=data.get("metrics", {}),
            links=data.get("links", {}),
        )
        for item in data.get("needs_review", []):
            report.needs_review.append(
                ReviewItem(
                    scope=item.get("scope", "field"),
                    field_path=item.get("field_path", ""),
                    node_id=item.get("node_id", ""),
                    reason=item.get("reason", ""),
                    confidence=float(item.get("confidence", 0.0) or 0.0),
                    page=int(item.get("page", 0) or 0),
                    bbox=item.get("bbox"),
                )
            )
        return report


def build_quality_decision(
    visual_graph: Any = None,
    source_span_ledger: Any = None,
    outcome_ledger: Any = None,
    editions: dict[str, Any] | None = None,
    *,
    document_id: str = "",
    task_id: str = "",
    confidence_policy: str = "ga_default_v1",
    threshold_auto_ingest: float = 0.85,
    threshold_needs_review: float = 0.50,
) -> QualityDecisionReport:
    """Build a Quality Decision Report v2 from evidence sources.

    Evaluates schema pass, key evidence coverage, outcome status, and
    confidence thresholds to produce one of:
    - ``auto_ingest`` — usable without human intervention
    - ``needs_review`` — requires human review before ingestion
    - ``reject`` — cannot be used; blocking issues present

    Args:
        visual_graph: VisualEvidenceGraph or None.
        source_span_ledger: SourceSpanLedger or None.
        outcome_ledger: OutcomeLedger or None.
        editions: Edition payloads dict.
        document_id: Document identifier.
        task_id: Task identifier.
        confidence_policy: Policy name (default: ga_default_v1).
        threshold_auto_ingest: Minimum confidence for auto_ingest.
        threshold_needs_review: Confidence below this triggers needs_review.

    Returns:
        QualityDecisionReport with decision, reasons, blocking issues, and
        review items.
    """
    report = QualityDecisionReport(
        document_id=document_id,
        task_id=task_id,
        confidence_policy=confidence_policy,
    )

    blocking: list[dict[str, Any]] = []
    review_items: list[ReviewItem] = []
    observed: dict[str, Any] = {}

    # ── 1. Schema validation pass ──
    schema_pass = True
    if outcome_ledger is not None:
        events = getattr(outcome_ledger, "events", []) or []
        for ev in events:
            ev_dict = ev.to_dict() if hasattr(ev, "to_dict") else ev
            if ev_dict.get("category") == "schema" and ev_dict.get("status") in ("failure", "fatal"):
                schema_pass = False
                blocking.append(
                    {
                        "scope": "schema",
                        "reason": ev_dict.get("message", "schema validation failed"),
                        "event_id": ev_dict.get("event_id", ""),
                    }
                )
    # Check edition availability for schema failures
    for ed_name, payload in (editions or {}).items():
        if isinstance(payload, dict):
            status_info = payload.get("status") or payload.get("availability") or {}
            status_str = str(status_info.get("status", status_info.get("state", "")))
            if status_str in ("schema_fail", "invalid"):
                schema_pass = False
                blocking.append(
                    {
                        "scope": f"edition:{ed_name}",
                        "reason": f"Schema validation failed for {ed_name}",
                    }
                )

    # ── 2. Outcome ledger evaluation ──
    silent_failure_count = 0
    fatal_outcome_count = 0
    if outcome_ledger is not None:
        events = getattr(outcome_ledger, "events", []) or []
        for ev in events:
            ev_dict = ev.to_dict() if hasattr(ev, "to_dict") else ev
            status = ev_dict.get("status", "")
            severity = ev_dict.get("severity", "")
            if status in ("failure", "fatal") or severity in ("error", "fatal"):
                fatal_outcome_count += 1
                blocking.append(
                    {
                        "scope": "outcome",
                        "reason": ev_dict.get("message", f"outcome event: {ev_dict.get('code', '')}"),
                        "event_id": ev_dict.get("event_id", ""),
                        "category": ev_dict.get("category", ""),
                    }
                )
            if status in ("silent_failure",) and severity not in ("error", "fatal"):
                silent_failure_count += 1
    observed["fatal_outcome_count"] = fatal_outcome_count
    observed["silent_failure_count"] = silent_failure_count

    # ── 3. Source span coverage evaluation ──
    span_coverage = 0.0
    needs_evidence_fields: list[ReviewItem] = []
    low_confidence_fields: list[ReviewItem] = []
    if source_span_ledger is not None:
        span_coverage = getattr(source_span_ledger, "coverage_ratio", 0.0) or 0.0
        for span in getattr(source_span_ledger, "field_spans", []) or []:
            if span.review == "needs_evidence":
                needs_evidence_fields.append(
                    ReviewItem(
                        scope="field",
                        field_path=span.field_path,
                        node_id=f"field:{span.field_path}",
                        reason="no_evidence",
                        confidence=span.confidence,
                        page=span.page,
                        bbox=span.bbox,
                    )
                )
            elif span.review == "needs_review":
                low_confidence_fields.append(
                    ReviewItem(
                        scope="field",
                        field_path=span.field_path,
                        node_id=f"field:{span.field_path}",
                        reason="low_confidence",
                        confidence=span.confidence,
                        page=span.page,
                        bbox=span.bbox,
                    )
                )
        for uf in getattr(source_span_ledger, "unresolved_fields", []) or []:
            needs_evidence_fields.append(
                ReviewItem(
                    scope="unresolved_field",
                    field_path=uf.field_path,
                    reason=uf.reason,
                    confidence=0.0,
                )
            )
    observed["span_coverage"] = round(span_coverage, 4)
    observed["needs_evidence_count"] = len(needs_evidence_fields)
    observed["low_confidence_count"] = len(low_confidence_fields)

    # ── 4. Visual graph quality evaluation ──
    if visual_graph is not None:
        needs_review_nodes = (
            visual_graph.nodes_needing_review() if hasattr(visual_graph, "nodes_needing_review") else []
        )
        for node in needs_review_nodes:
            if node.review == "needs_evidence":
                review_items.append(
                    ReviewItem(
                        scope="visual_node",
                        field_path=node.field_path,
                        node_id=node.id,
                        reason="no_evidence_in_visual_graph",
                        confidence=node.confidence,
                        page=node.page,
                        bbox=node.bbox,
                    )
                )
            elif node.confidence < threshold_needs_review:
                review_items.append(
                    ReviewItem(
                        scope="visual_node",
                        field_path=node.field_path,
                        node_id=node.id,
                        reason="low_confidence_in_visual_graph",
                        confidence=node.confidence,
                        page=node.page,
                        bbox=node.bbox,
                    )
                )

    # ── 5. Edition confidence evaluation ──
    for ed_name, payload in (editions or {}).items():
        if not isinstance(payload, dict):
            continue
        quality = payload.get("quality") or {}
        conf = float(quality.get("confidence", 0.0) or 0.0)
        meta = payload.get("metadata") or {}
        fallback = meta.get("fallback_reason")
        if conf < threshold_needs_review:
            review_items.append(
                ReviewItem(
                    scope="edition",
                    field_path=f"{ed_name}.data",
                    node_id=f"edition:{ed_name}",
                    reason="low_edition_confidence",
                    confidence=conf,
                )
            )
        if fallback:
            review_items.append(
                ReviewItem(
                    scope="edition",
                    field_path=f"{ed_name}.data",
                    node_id=f"edition:{ed_name}",
                    reason=f"fallback: {fallback}",
                    confidence=conf,
                )
            )

    # ── 6. Compute decision ──
    review_items.extend(needs_evidence_fields)
    review_items.extend(low_confidence_fields)

    if fatal_outcome_count > 0:
        report.decision = "reject"
        report.decision_reason = f"{fatal_outcome_count} fatal outcome(s) detected"
    elif not schema_pass:
        report.decision = "reject"
        report.decision_reason = "schema validation failed"
    elif needs_evidence_fields or span_coverage < 0.80:
        report.decision = "needs_review"
        report.decision_reason = (
            f"{len(needs_evidence_fields)} field(s) missing evidence"
            if needs_evidence_fields
            else f"span coverage {span_coverage:.1%} below threshold"
        )
    elif low_confidence_fields or review_items:
        report.decision = "needs_review"
        report.decision_reason = (
            f"{len(low_confidence_fields)} low-confidence field(s) + {len(review_items)} visual node(s) needing review"
        )
    else:
        report.decision = "auto_ingest"
        report.decision_reason = "key_fields_have_evidence_and_confidence_above_threshold"

    # ── Fidelity summary ──
    report.summary = {
        "text_fidelity": "pass" if span_coverage >= 0.95 else "warning" if span_coverage >= 0.80 else "fail",
        "layout_fidelity": "pass" if (visual_graph is not None and len(visual_graph.nodes) > 0) else "not_measured",
        "business_fidelity": "pass" if not (needs_evidence_fields or low_confidence_fields) else "warning",
        "audit_fidelity": "pass"
        if span_coverage >= 0.95 and not needs_evidence_fields
        else "warning"
        if span_coverage >= 0.80
        else "fail",
    }

    report.blocking_issues = blocking
    report.needs_review = review_items
    report.metrics = observed
    report.links = {
        "visual_debug": "visual_debug.html",
        "visual_graph": "visual_evidence_graph.json",
        "source_span_ledger": "source_span_ledger.json",
        "support_bundle": "support_bundle.zip",
    }

    return report


__all__ = [
    "ReviewItem",
    "QualityDecisionReport",
    "build_quality_decision",
]
