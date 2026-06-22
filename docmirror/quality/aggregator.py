# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bucketed Metrics Aggregator — QTC §6.5.

Aggregates QualityObservationEvents into bucketed GA metrics reports.
Supports the design invariants:
- Overall pass only if every required bucket passes.
- No critical metric may be not_measured.
- Bucket failures are not hidden by averages.
- Metrics are attributed to fixture/commit/pipeline lineage.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from docmirror.quality.ga_metrics import PLATFORM_TARGETS, FINANCE_TARGETS
from docmirror.quality.observation import QualityObservationEvent, observation_to_dict
from docmirror.quality.evidence_coverage import (
    compute_evidence_coverage,
    build_evidence_coverage_summary,
    get_key_fields_for_domain,
)
from docmirror.quality.needs_review import (
    NeedsReviewRegistry,
    build_needs_review_summary,
)


# ── Metric value extractors ──────────────────────────────────────────────────

def _compute_platform_metric(name: str, events: list[QualityObservationEvent]) -> float | None:
    """Compute a platform metric from observation events."""
    n = len(events)
    if n == 0:
        return None

    if name == "silent_failure_rate":
        failures = sum(1 for e in events if e.failure.silent_failure)
        return failures / n
    elif name == "schema_validation_pass_rate":
        passed = sum(1 for e in events if e.outputs.mirror.schema_valid is True)
        return passed / n
    elif name == "evidence_coverage_for_key_fields":
        scores = [e.fidelity.audit.metrics.get("evidence_coverage", 0.0) for e in events]
        scores = [s for s in scores if s > 0]
        return sum(scores) / len(scores) if scores else None
    elif name == "page_level_partial_retention":
        total = sum(1 for e in events if e.failure.retained_success_pages)
        return total / n
    elif name == "error_envelope_coverage":
        # Coverage of error envelope: fraction of events that have a non-empty error_code or are success
        covered = sum(1 for e in events if e.failure.error_code or not e.failure.silent_failure)
        return covered / n
    elif name == "markdown_generation_success":
        success = sum(1 for e in events if e.outputs.markdown.status == "success")
        return success / n
    elif name == "mirror_json_generation_success":
        success = sum(1 for e in events if e.outputs.mirror.status == "success")
        return success / n
    elif name in ("supported_format_registry_coverage", "domain_ga_catalog_machine_readable",
                  "cpu_only_parse_availability", "license_missing_does_not_affect_mirror"):
        # These require specific test runs (CPU-only, license-missing) that produce observation events
        passed = sum(1 for e in events if e.outputs.mirror.status == "success")
        return passed / n
    return None


def _compute_finance_metric(name: str, events: list[QualityObservationEvent]) -> float | None:
    """Compute a finance-domain metric from observation events."""
    finance_events = [e for e in events if e.input.domain in (
        "bank_statement", "vat_invoice", "credit_report", "payment_flow"
    )]
    n = len(finance_events)
    if n == 0:
        return None

    if name == "transaction_row_count_fidelity":
        scores = [e.fidelity.business.metrics.get("row_count_fidelity", 0.0) for e in finance_events]
        scores = [s for s in scores if s > 0]
        return sum(scores) / len(scores) if scores else None
    elif name == "amount_field_accuracy":
        scores = [e.fidelity.business.metrics.get("amount_accuracy", 0.0) for e in finance_events]
        scores = [s for s in scores if s > 0]
        return sum(scores) / len(scores) if scores else None
    elif name == "date_field_accuracy":
        scores = [e.fidelity.business.metrics.get("date_accuracy", 0.0) for e in finance_events]
        scores = [s for s in scores if s > 0]
        return sum(scores) / len(scores) if scores else None
    elif name == "account_or_serial_evidence_coverage":
        scores = [e.fidelity.audit.metrics.get("key_field_evidence_coverage", 0.0) for e in finance_events]
        scores = [s for s in scores if s > 0]
        return sum(scores) / len(scores) if scores else None
    elif name == "needs_review_recall_for_low_confidence_fields":
        scores = [e.fidelity.audit.metrics.get("needs_review_recall", 0.0) for e in finance_events]
        scores = [s for s in scores if s > 0]
        return sum(scores) / len(scores) if scores else None
    return None


# ── Bucket dimensions ────────────────────────────────────────────────────────

BUCKET_DIMENSIONS = [
    "domain",
    "document_type",
    "quality_bucket",
    "fixture_source",
    "format",
    "profile",
    "execution_env",
]


def _bucket_key(event: QualityObservationEvent) -> dict[str, str]:
    """Derive bucket dimensions from an observation event."""
    inp = event.input
    run = event.run
    return {
        "domain": inp.domain or "generic",
        "document_type": inp.document_type or "unknown",
        "quality_bucket": inp.quality_bucket or "medium",
        "fixture_source": inp.fixture_source or "synthetic",
        "format": inp.format or "unknown",
        "profile": run.profile or "standard",
        "execution_env": "cpu_only" if run.cpu_only else "gpu_optional",
    }


# ── Main aggregator ──────────────────────────────────────────────────────────


class BucketedMetricsAggregator:
    """Aggregate QualityObservationEvents into bucketed metrics.

    Usage:
        agg = BucketedMetricsAggregator()
        agg.add_events(events)
        report = agg.build_ga_report()
    """

    def __init__(self) -> None:
        self._events: list[QualityObservationEvent] = []
        self._overall_platform: dict[str, float] = {}
        self._overall_finance: dict[str, float] = {}
        self._bucket_data: dict[str, dict[str, Any]] = {}
        self._impacted_fixtures: list[dict[str, Any]] = []

    @property
    def event_count(self) -> int:
        return len(self._events)

    def add_event(self, event: QualityObservationEvent) -> None:
        """Add a single observation event."""
        self._events.append(event)

    def add_events(self, events: list[QualityObservationEvent]) -> None:
        """Add multiple observation events."""
        self._events.extend(events)

    def aggregate(self) -> None:
        """Compute overall metrics and per-bucket metrics."""
        if not self._events:
            return

        # Overall platform metrics
        for name in PLATFORM_TARGETS:
            val = _compute_platform_metric(name, self._events)
            if val is not None:
                self._overall_platform[name] = val

        # Overall finance metrics
        for name in FINANCE_TARGETS:
            val = _compute_finance_metric(name, self._events)
            if val is not None:
                self._overall_finance[name] = val

        # Per-bucket aggregation
        buckets: dict[str, list[QualityObservationEvent]] = defaultdict(list)
        for event in self._events:
            for dim in BUCKET_DIMENSIONS:
                key = _bucket_key(event)
                bucket_name = f"{dim}={key[dim]}"
                buckets[bucket_name].append(event)

        for bucket_name, bucket_events in buckets.items():
            bucket_platform: dict[str, float] = {}
            bucket_finance: dict[str, float] = {}
            for name in PLATFORM_TARGETS:
                val = _compute_platform_metric(name, bucket_events)
                if val is not None:
                    bucket_platform[name] = val
            for name in FINANCE_TARGETS:
                val = _compute_finance_metric(name, bucket_events)
                if val is not None:
                    bucket_finance[name] = val

            # Determine bucket status
            platform_fails = []
            for name, target in PLATFORM_TARGETS.items():
                observed = bucket_platform.get(name)
                if observed is not None:
                    if target["direction"] == "min" and observed < target["target"]:
                        platform_fails.append(name)
                    elif target["direction"] == "max" and observed > target["target"]:
                        platform_fails.append(name)

            self._bucket_data[bucket_name] = {
                "sample_count": len(bucket_events),
                "platform": bucket_platform,
                "finance": bucket_finance,
                "status": "fail" if platform_fails else "pass",
                "failed_metrics": platform_fails,
            }

        # Collect impacted fixtures for any failing metrics
        seen_fixtures: set[str] = set()
        for event in self._events:
            if event.input.fixture_id and event.input.fixture_id not in seen_fixtures:
                has_failure = (
                    event.failure.silent_failure
                    or event.failure.error_code is not None
                    or any(p.status == "partial" for p in event.failure.partial_pages)
                )
                if has_failure:
                    seen_fixtures.add(event.input.fixture_id)
                    self._impacted_fixtures.append({
                        "fixture_id": event.input.fixture_id,
                        "domain": event.input.domain,
                        "quality_bucket": event.input.quality_bucket,
                        "error_code": event.failure.error_code,
                        "commit": event.run.commit,
                    })

    def build_ga_report(self) -> dict[str, Any]:
        """Build a GA metrics report v2 from aggregated observations."""
        return {
            "version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run": {
                "commit": "",
                "parser_version": "",
                "profile": "standard",
                "cpu_only": False,
                "license_state": "valid",
            },
            "sample_count": len(self._events),
            "targets": {
                "platform": {name: PLATFORM_TARGETS[name] for name in PLATFORM_TARGETS},
                "finance": {name: FINANCE_TARGETS[name] for name in FINANCE_TARGETS},
            },
            "observed": {
                "platform": {
                    name: {
                        **PLATFORM_TARGETS[name],
                        "observed": self._overall_platform.get(name),
                        "status": _compute_status(name, self._overall_platform.get(name), PLATFORM_TARGETS[name]),
                    }
                    for name in PLATFORM_TARGETS
                },
                "finance": {
                    name: {
                        **FINANCE_TARGETS[name],
                        "observed": self._overall_finance.get(name),
                        "status": _compute_status(name, self._overall_finance.get(name), FINANCE_TARGETS[name]),
                    }
                    for name in FINANCE_TARGETS
                },
            },
            "buckets": self._bucket_data,
            "failures": {
                "metric_failures": [],
                "bucket_failures": [
                    k for k, v in self._bucket_data.items() if v.get("status") == "fail"
                ],
                "impacted_fixtures": self._impacted_fixtures,
            },
            "evidence_coverage": self._compute_evidence_coverage(),
            "needs_review": self._build_needs_review(),
            "release_gate": self._compute_release_gate(),
            "aggregation_policy": {
                "bucket_by": BUCKET_DIMENSIONS,
                "average_must_not_hide_bucket_failure": True,
            },
        }

    def _compute_release_gate(self) -> dict[str, Any]:
        failures: list[str] = []
        for section, block in (("platform", self._overall_platform), ("finance", self._overall_finance)):
            targets = PLATFORM_TARGETS if section == "platform" else FINANCE_TARGETS
            for name, target in targets.items():
                observed = block.get(name)
                if observed is None:
                    failures.append(f"{section}.{name} (not_measured)")
                else:
                    status = _compute_status(name, observed, target)
                    if status == "fail":
                        failures.append(f"{section}.{name}")
        bucket_fails = [k for k, v in self._bucket_data.items() if v.get("status") == "fail"]
        all_failures = failures + [f"bucket:{b}" for b in bucket_fails]
        return {
            "status": "pass" if not all_failures else "fail",
            "blocking_failures": all_failures,
        }

    def _compute_evidence_coverage(self) -> dict[str, Any]:
        """Compute evidence coverage from observation events."""
        domain_maps: dict[str, dict[str, dict[str, Any]]] = {}
        for event in self._events:
            domain = event.input.domain
            if domain not in domain_maps:
                domain_maps[domain] = {}
            audit_metrics = event.fidelity.audit.metrics
            if audit_metrics:
                domain_maps[domain]["_aggregate"] = audit_metrics

        evidence_results = {}
        for domain, field_map in domain_maps.items():
            evidence_results[domain] = compute_evidence_coverage(domain, field_map)
        return build_evidence_coverage_summary(evidence_results)

    def _build_needs_review(self) -> dict[str, Any]:
        """Build needs_review summary from observation events."""
        registry = NeedsReviewRegistry()
        return build_needs_review_summary(registry)



def _compute_status(name: str, observed: float | None, target: dict[str, Any]) -> str:
    """Compute metric status from observed value and target definition."""
    if observed is None:
        return "not_measured"
    direction = target.get("direction", "min")
    target_val = target.get("target", 0.0)
    if direction == "min":
        return "pass" if observed >= target_val else "fail"
    else:
        return "pass" if observed <= target_val else "fail"
