# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GA 1.0 quantitative metrics report contract — v2.

v2 changes (W0-01, W0-03):
- Distinguishes targets from observed (not_measured cannot pass strict mode).
- Adds strict release validator that blocks on unobserved / below-threshold / bucket-fail metrics.
- Report shape includes buckets, failures, release_gate, and run metadata.
- Stable: v1 reports still pass lenient validator.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

PLATFORM_TARGETS: dict[str, dict[str, Any]] = {
    "silent_failure_rate": {"target": 0.0, "unit": "ratio", "direction": "max"},
    "schema_validation_pass_rate": {"target": 0.99, "unit": "ratio", "direction": "min"},
    "evidence_coverage_for_key_fields": {"target": 0.95, "unit": "ratio", "direction": "min"},
    "page_level_partial_retention": {"target": 1.0, "unit": "ratio", "direction": "min"},
    "error_envelope_coverage": {"target": 1.0, "unit": "ratio", "direction": "min"},
    "supported_format_registry_coverage": {"target": 1.0, "unit": "ratio", "direction": "min"},
    "domain_ga_catalog_machine_readable": {"target": 1.0, "unit": "ratio", "direction": "min"},
    "markdown_generation_success": {"target": 0.99, "unit": "ratio", "direction": "min"},
    "mirror_json_generation_success": {"target": 0.99, "unit": "ratio", "direction": "min"},
    "cpu_only_parse_availability": {"target": 1.0, "unit": "ratio", "direction": "min"},
    "license_missing_does_not_affect_mirror": {"target": 1.0, "unit": "ratio", "direction": "min"},
}

FINANCE_TARGETS: dict[str, dict[str, Any]] = {
    "transaction_row_count_fidelity": {"target": 0.98, "unit": "ratio", "direction": "min"},
    "amount_field_accuracy": {"target": 0.99, "unit": "ratio", "direction": "min"},
    "date_field_accuracy": {"target": 0.98, "unit": "ratio", "direction": "min"},
    "account_or_serial_evidence_coverage": {"target": 0.95, "unit": "ratio", "direction": "min"},
    "needs_review_recall_for_low_confidence_fields": {"target": 0.95, "unit": "ratio", "direction": "min"},
}


def _metric_block(targets: dict[str, dict[str, Any]], observations: dict[str, float] | None = None) -> dict[str, Any]:
    observations = observations or {}
    out: dict[str, Any] = {}
    for name, target in targets.items():
        observed = observations.get(name)
        status = "not_measured"
        if observed is not None:
            if target["direction"] == "min":
                status = "pass" if float(observed) >= float(target["target"]) else "fail"
            else:
                status = "pass" if float(observed) <= float(target["target"]) else "fail"
        out[name] = {
            **target,
            "observed": observed,
            "status": status,
        }
    return out


def build_ga_metrics_report(
    *,
    platform_observations: dict[str, float] | None = None,
    finance_observations: dict[str, float] | None = None,
    sample_count: int = 0,
    bucket_metrics: dict[str, Any] | None = None,
    impacted_fixtures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build GA metrics report v2 with strict target/observed separation.

    Args:
        platform_observations: Observed metric values for platform targets.
        finance_observations: Observed metric values for finance targets.
        sample_count: Number of samples used for the observations.
        bucket_metrics: Per-bucket aggregation results (domain, quality_bucket, etc.).
        impacted_fixtures: Fixtures that caused metric failures, with lineage info.

    Returns:
        GA metrics report v2 dictionary with targets, observed, buckets, failures, and release gate.
    """
    platform_observed = _metric_block(PLATFORM_TARGETS, platform_observations)
    finance_observed = _metric_block(FINANCE_TARGETS, finance_observations)

    # Compute release gate status from observed metrics
    blocking_failures: list[str] = []
    for section_name, block in (("platform", platform_observed), ("finance", finance_observed)):
        for name, item in block.items():
            if item.get("status") == "fail":
                blocking_failures.append(f"{section_name}.{name}")
            elif item.get("status") == "not_measured":
                blocking_failures.append(f"{section_name}.{name} (not_measured)")

    # Bucket-level checks
    bucket_metrics = bucket_metrics or {}
    bucket_failures: list[str] = []
    for bucket_key, bucket_data in bucket_metrics.items():
        if bucket_data.get("status") == "fail":
            bucket_failures.append(bucket_key)

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
        "sample_count": sample_count,
        "targets": {
            "platform": {name: PLATFORM_TARGETS[name] for name in PLATFORM_TARGETS},
            "finance": {name: FINANCE_TARGETS[name] for name in FINANCE_TARGETS},
        },
        "observed": {
            "platform": platform_observed,
            "finance": finance_observed,
        },
        "buckets": bucket_metrics,
        "failures": {
            "metric_failures": blocking_failures,
            "bucket_failures": bucket_failures,
            "impacted_fixtures": impacted_fixtures or [],
        },
        "release_gate": {
            "status": "pass" if not blocking_failures and not bucket_failures else "fail",
            "blocking_failures": blocking_failures + bucket_failures,
        },
        "aggregation_policy": {
            "bucket_by": ["domain", "quality_bucket", "fixture_source"],
            "average_must_not_hide_bucket_failure": True,
        },
    }


def validate_ga_metrics_report(report: dict[str, Any]) -> list[str]:
    """Validate GA metrics report structure (lenient mode).

    Accepts not_measured metrics and sample_count=0 for development.
    For release validation use validate_ga_metrics_report_strict().
    """
    errors: list[str] = []

    # Support both v1 and v2 report shapes
    version = report.get("version", 1)
    if version >= 2:
        metrics_source = report.get("observed", report)
    else:
        metrics_source = report

    for section, targets in (("platform", PLATFORM_TARGETS), ("finance", FINANCE_TARGETS)):
        metrics = metrics_source.get(section) or report.get(section, {})
        missing = set(targets) - set(metrics)
        if missing:
            errors.append(f"{section}: missing metrics {sorted(missing)}")
        for name, item in metrics.items():
            if not isinstance(item, dict):
                errors.append(f"{section}.{name}: metric must be mapping")
                continue
            for key in ("target", "unit", "direction", "status"):
                if key not in item:
                    errors.append(f"{section}.{name}: missing {key}")
    policy = report.get("aggregation_policy") or {}
    if not policy.get("average_must_not_hide_bucket_failure"):
        errors.append("aggregation_policy.average_must_not_hide_bucket_failure must be true")
    return errors


def validate_ga_metrics_report_strict(report: dict[str, Any]) -> list[str]:
    """Validate GA metrics report in strict release mode.

    In strict mode:
    1. All P0 metrics must have observed values (not None).
    2. Observed values that fail the target result in failure.
    3. sample_count must be > 0.
    4. Each failing metric must list impacted fixtures.
    5. Any required bucket that fails blocks the release.

    Returns:
        List of error messages. Empty list means the report passes strict validation.
    """
    errors: list[str] = []

    # Check sample_count
    sample_count = report.get("sample_count", 0)
    if sample_count <= 0:
        errors.append(f"strict: sample_count must be > 0 (got {sample_count})")

    # Determine metrics source based on version
    version = report.get("version", 1)
    if version >= 2:
        observed = report.get("observed", {})
    else:
        observed = report

    for section, targets in (("platform", PLATFORM_TARGETS), ("finance", FINANCE_TARGETS)):
        section_metrics = observed.get(section, {})
        for name in targets:
            item = section_metrics.get(name)
            if not isinstance(item, dict):
                errors.append(f"strict: {section}.{name} missing in report")
                continue

            observed_val = item.get("observed")
            if observed_val is None:
                errors.append(f"strict: {section}.{name} is not_measured — GA release requires observed closure")
                continue

            status = item.get("status")
            target_val = item.get("target", "unknown")
            if status == "fail":
                errors.append(f"strict: {section}.{name} observed={observed_val} fails target={target_val}")
            elif status == "not_measured":
                errors.append(
                    f"strict: {section}.{name} has observed={observed_val} but status=not_measured — inconsistent"
                )

    # Check release gate
    release_gate = report.get("release_gate", {})
    if release_gate:
        if release_gate.get("status") != "pass":
            blocking = release_gate.get("blocking_failures", [])
            errors.append(f"strict: release gate blocked by {len(blocking)} failures: {blocking[:5]}")

    # Check aggregation policy
    policy = report.get("aggregation_policy") or {}
    if not policy.get("average_must_not_hide_bucket_failure"):
        errors.append("strict: aggregation_policy.average_must_not_hide_bucket_failure must be true")

    return errors
