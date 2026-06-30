"""Needs Review Aggregation — QTC W3-04.

Aggregates needs_review items across observations and domains.
Groups by confidence bucket, domain, quality bucket, and fixture source.
Provides recall computation when golden low-confidence labels are available.

Design reference: docs/design/GA1.0/08_accuracy_trust_ga_gap_closure_plan.md W3-04
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from docmirror.quality.field_details import FieldDetail
from docmirror.quality.observation import QualityObservationEvent

# ── Needs Review Registry ───────────────────────────────────────────────────


@dataclass
class NeedsReviewItem:
    """A single needs_review item from a field or evidence entry."""

    field_path: str
    domain: str
    confidence: float
    review_status: str  # auto_accepted | manual_optional | needs_review | needs_evidence
    has_evidence: bool
    fixture_id: str = ""
    quality_bucket: str = ""
    observation_id: str = ""
    reason: str = ""  # Why it needs review (low confidence, no evidence, fallback, etc.)


@dataclass
class NeedsReviewRegistry:
    """Collects all needs_review items from observations.

    Provides grouping, filtering, and recall computation capabilities.
    """

    items: list[NeedsReviewItem] = field(default_factory=list)

    def add_from_field_detail(
        self,
        field_path: str,
        detail: FieldDetail,
        domain: str = "generic",
        fixture_id: str = "",
        quality_bucket: str = "",
        observation_id: str = "",
    ) -> None:
        """Add an item from a FieldDetail instance."""
        reason = _classify_reason(detail)
        self.items.append(
            NeedsReviewItem(
                field_path=field_path,
                domain=domain,
                confidence=detail.confidence,
                review_status=detail.review,
                has_evidence=len(detail.source_refs) > 0,
                fixture_id=fixture_id,
                quality_bucket=quality_bucket,
                observation_id=observation_id,
                reason=reason,
            )
        )

    def add_from_observation(
        self,
        event: QualityObservationEvent,
        field_details: dict[str, FieldDetail],
    ) -> None:
        """Add all fields from an observation event."""
        for field_path, detail in field_details.items():
            self.add_from_field_detail(
                field_path=field_path,
                detail=detail,
                domain=event.input.domain,
                fixture_id=event.input.fixture_id,
                quality_bucket=event.input.quality_bucket,
                observation_id=event.observation_id,
            )

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def needs_review_items(self) -> list[NeedsReviewItem]:
        """Items that require review (needs_review or needs_evidence)."""
        return [it for it in self.items if it.review_status in ("needs_review", "needs_evidence")]

    @property
    def auto_accepted_items(self) -> list[NeedsReviewItem]:
        """Items that were automatically accepted."""
        return [it for it in self.items if it.review_status == "auto_accepted"]

    @property
    def no_evidence_items(self) -> list[NeedsReviewItem]:
        """Items that have no evidence."""
        return [it for it in self.items if not it.has_evidence]

    @property
    def low_confidence_items(self) -> list[NeedsReviewItem]:
        """Items with low confidence (< 0.5)."""
        return [it for it in self.items if it.confidence < 0.5]

    def group_by_domain(self) -> dict[str, list[NeedsReviewItem]]:
        """Group items by domain."""
        grouped: dict[str, list[NeedsReviewItem]] = defaultdict(list)
        for it in self.items:
            grouped[it.domain].append(it)
        return dict(grouped)

    def group_by_quality_bucket(self) -> dict[str, list[NeedsReviewItem]]:
        """Group items by quality bucket."""
        grouped: dict[str, list[NeedsReviewItem]] = defaultdict(list)
        for it in self.items:
            grouped[it.quality_bucket or "unknown"].append(it)
        return dict(grouped)

    def group_by_confidence_bucket(self) -> dict[str, list[NeedsReviewItem]]:
        """Group items by confidence level."""
        groups: dict[str, list[NeedsReviewItem]] = defaultdict(list)
        for it in self.items:
            if it.confidence >= 0.90:
                groups["high_confidence"].append(it)
            elif it.confidence >= 0.70:
                groups["medium_confidence"].append(it)
            elif it.confidence > 0:
                groups["low_confidence"].append(it)
            else:
                groups["no_confidence"].append(it)
        return dict(groups)


# ── Recall computation ─────────────────────────────────────────────────────


def compute_needs_review_recall(
    registry: NeedsReviewRegistry,
    golden_low_confidence_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Compute needs_review recall metrics.

    Recall = |fields correctly flagged for review| / |fields that should be flagged|

    When golden_low_confidence_fields is provided, those fields are treated as
    the authoritative set that should be flagged for review.

    Args:
        registry: The needs_review registry.
        golden_low_confidence_fields: Set of field paths known to be low-confidence.

    Returns:
        Dict with recall metrics.
    """
    # Items that were flagged for review
    flagged_paths = {it.field_path for it in registry.needs_review_items}
    flagged_and_low_conf = {it.field_path for it in registry.needs_review_items if it.confidence < 0.7}

    if golden_low_confidence_fields:
        should_flag = golden_low_confidence_fields
        correctly_flagged = should_flag & flagged_paths
        missed = should_flag - flagged_paths
        recall = len(correctly_flagged) / len(should_flag) if should_flag else 0.0
        return {
            "recall": recall,
            "total_should_flag": len(should_flag),
            "correctly_flagged": len(correctly_flagged),
            "missed": len(missed),
            "missed_fields": sorted(missed),
            "precision": len(correctly_flagged) / len(flagged_paths) if flagged_paths else 0.0,
        }
    else:
        # When no golden labels, return summary stats
        return {
            "recall": None,  # Cannot compute without golden labels
            "total_needs_review": len(registry.needs_review_items),
            "low_confidence_flagged": len(flagged_and_low_conf),
            "total_fields": registry.total,
            "needs_review_rate": len(registry.needs_review_items) / registry.total if registry.total > 0 else 0.0,
        }


def compute_no_evidence_auto_accept_rate(registry: NeedsReviewRegistry) -> float:
    """Compute the rate at which fields without evidence are auto-accepted.

    This should ideally be 0 — no evidence should mean needs_evidence, not auto_accepted.
    """
    no_evidence = registry.no_evidence_items
    if not no_evidence:
        return 0.0
    auto_accepted_no_evidence = sum(1 for it in no_evidence if it.review_status == "auto_accepted")
    return auto_accepted_no_evidence / len(no_evidence)


# ── Summary builder ────────────────────────────────────────────────────────


def build_needs_review_summary(
    registry: NeedsReviewRegistry,
    golden_low_confidence_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Build a comprehensive needs_review summary.

    Returns a dict suitable for inclusion in quality reports and GA metrics reports.
    """
    recall = compute_needs_review_recall(registry, golden_low_confidence_fields)

    domain_groups = registry.group_by_domain()
    domain_summaries: dict[str, dict[str, Any]] = {}
    for domain, items in domain_groups.items():
        needs_review = [it for it in items if it.review_status in ("needs_review", "needs_evidence")]
        domain_summaries[domain] = {
            "total_fields": len(items),
            "needs_review_count": len(needs_review),
            "auto_accepted_count": len([it for it in items if it.review_status == "auto_accepted"]),
            "no_evidence_count": len([it for it in items if not it.has_evidence]),
            "low_confidence_count": len([it for it in items if it.confidence < 0.5]),
            "needs_review_rate": len(needs_review) / len(items) if items else 0.0,
        }

    bucket_groups = registry.group_by_quality_bucket()
    bucket_summaries: dict[str, dict[str, Any]] = {}
    for bucket, items in bucket_groups.items():
        needs_review = [it for it in items if it.review_status in ("needs_review", "needs_evidence")]
        bucket_summaries[bucket] = {
            "total_fields": len(items),
            "needs_review_count": len(needs_review),
            "needs_review_rate": len(needs_review) / len(items) if items else 0.0,
        }

    return {
        "total_fields": registry.total,
        "needs_review_count": len(registry.needs_review_items),
        "auto_accepted_count": len(registry.auto_accepted_items),
        "no_evidence_count": len(registry.no_evidence_items),
        "low_confidence_count": len(registry.low_confidence_items),
        "no_evidence_auto_accept_rate": compute_no_evidence_auto_accept_rate(registry),
        "needs_review_rate": (len(registry.needs_review_items) / registry.total if registry.total > 0 else 0.0),
        "recall": recall,
        "by_domain": domain_summaries,
        "by_quality_bucket": bucket_summaries,
        "needs_review_items": [
            {
                "field_path": it.field_path,
                "domain": it.domain,
                "confidence": it.confidence,
                "review_status": it.review_status,
                "reason": it.reason,
                "fixture_id": it.fixture_id,
            }
            for it in registry.needs_review_items
        ],
    }


# ── Reason classifier ─────────────────────────────────────────────────────


def _classify_reason(detail: FieldDetail) -> str:
    """Classify why a field needs review."""
    reasons: list[str] = []
    if not detail.source_refs:
        reasons.append("no_source_refs")
    if detail.confidence < 0.7:
        reasons.append("low_confidence")
    if detail.confidence == 0.0:
        reasons.append("no_confidence")
    if detail.review in ("needs_evidence",):
        reasons.append("needs_evidence_per_policy")
    if detail.review == "needs_review":
        reasons.append("needs_review_per_policy")
    return ",".join(reasons) if reasons else "unknown"
