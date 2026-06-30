# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for the QTC (Quality & Trust Contract) foundation modules.

Covers:
- QualityObservationEvent model creation, serialization, round-trip
- BucketedMetricsAggregator with multiple events
- Confidence policy YAML loading
- Strict GA metrics validation
- Error envelope matrix completeness
"""

import json
from pathlib import Path

import yaml

from docmirror.quality.aggregator import BucketedMetricsAggregator
from docmirror.quality.ga_metrics import (
    build_ga_metrics_report,
    validate_ga_metrics_report,
    validate_ga_metrics_report_strict,
)
from docmirror.quality.observation import (
    FidelityLayer,
    PageOutcome,
    QualityObservationEvent,
    new_observation_event,
    observation_from_dict,
    observation_to_dict,
)


def test_observation_event_creation():
    """QualityObservationEvent can be created with defaults."""
    event = new_observation_event(fixture_id="test_001")
    assert event.observation_id.startswith("qobs_")
    assert event.version == 1
    assert event.input.fixture_id == "test_001"


def test_observation_event_roundtrip():
    """QualityObservationEvent survives serialization round-trip."""
    event = new_observation_event(
        fixture_id="roundtrip_test",
        domain="bank_statement",
        quality_bucket="hard",
    )
    d = observation_to_dict(event)
    restored = observation_from_dict(d)
    assert restored.observation_id == event.observation_id
    assert restored.input.domain == "bank_statement"


def test_observation_event_with_fidelity():
    """QualityObservationEvent supports four-layer fidelity metrics."""
    event = new_observation_event(fixture_id="fidelity_test")
    event.fidelity.text.score = 0.95
    event.fidelity.text.status = "pass"
    event.fidelity.text.metrics["cer"] = 0.02
    event.fidelity.business.metrics["amount_accuracy"] = 0.99

    d = observation_to_dict(event)
    assert d["fidelity"]["text"]["score"] == 0.95
    assert d["fidelity"]["text"]["metrics"]["cer"] == 0.02
    assert d["fidelity"]["business"]["metrics"]["amount_accuracy"] == 0.99


def test_observation_event_with_page_outcomes():
    """QualityObservationEvent supports page-level outcome tracking."""
    event = new_observation_event(fixture_id="page_test")
    event.failure.partial_pages = [
        PageOutcome(page=1, status="success"),
        PageOutcome(page=2, status="partial", error_code="LOW_QUALITY_INPUT"),
        PageOutcome(page=3, status="success"),
    ]
    d = observation_to_dict(event)
    assert len(d["failure"]["partial_pages"]) == 3
    assert d["failure"]["partial_pages"][1]["error_code"] == "LOW_QUALITY_INPUT"


def test_aggregator_empty():
    """BucketedMetricsAggregator handles empty input gracefully."""
    agg = BucketedMetricsAggregator()
    agg.aggregate()
    report = agg.build_ga_report()
    assert report["sample_count"] == 0
    assert report["version"] == 2


def test_aggregator_with_events():
    """BucketedMetricsAggregator correctly aggregates events."""
    agg = BucketedMetricsAggregator()

    for i in range(10):
        event = new_observation_event(
            fixture_id=f"agg_test_{i:03d}",
            domain="bank_statement" if i < 5 else "generic",
            quality_bucket="hard" if i < 3 else "medium",
            fixture_source="desensitized_real" if i < 6 else "synthetic",
        )
        event.outputs.mirror.status = "success"
        event.outputs.mirror.schema_valid = True
        event.outputs.markdown.status = "success"
        event.failure.silent_failure = False
        event.fidelity.audit.metrics["evidence_coverage"] = 0.96
        agg.add_event(event)

    agg.aggregate()
    report = agg.build_ga_report()
    assert report["sample_count"] == 10
    assert "buckets" in report
    assert "release_gate" in report
    assert len(report["buckets"]) > 0


def test_ga_metrics_v2_shape():
    """GA metrics report v2 has the correct shape."""
    report = build_ga_metrics_report()
    assert report["version"] == 2
    assert "targets" in report
    assert "observed" in report
    assert "buckets" in report
    assert "failures" in report
    assert "release_gate" in report
    assert "run" in report


def test_strict_validator_rejects_not_measured():
    """Strict validator rejects reports with not_measured metrics."""
    report = build_ga_metrics_report()
    errors = validate_ga_metrics_report_strict(report)
    assert len(errors) > 0
    assert any("not_measured" in e for e in errors)
    assert any("sample_count must be > 0" in e for e in errors)


def test_strict_validator_accepts_valid_report():
    """Strict validator accepts reports with all metrics observed and passing."""
    platform_obs = {name: target["target"] for name, target in {
        "silent_failure_rate": {"target": 0.0},
        "schema_validation_pass_rate": {"target": 0.99},
        "evidence_coverage_for_key_fields": {"target": 0.95},
        "page_level_partial_retention": {"target": 1.0},
        "error_envelope_coverage": {"target": 1.0},
        "supported_format_registry_coverage": {"target": 1.0},
        "domain_ga_catalog_machine_readable": {"target": 1.0},
        "markdown_generation_success": {"target": 0.99},
        "mirror_json_generation_success": {"target": 0.99},
        "cpu_only_parse_availability": {"target": 1.0},
        "license_missing_does_not_affect_mirror": {"target": 1.0},
    }.items()}
    finance_obs = {name: target["target"] for name, target in {
        "transaction_row_count_fidelity": {"target": 0.98},
        "amount_field_accuracy": {"target": 0.99},
        "date_field_accuracy": {"target": 0.98},
        "account_or_serial_evidence_coverage": {"target": 0.95},
        "needs_review_recall_for_low_confidence_fields": {"target": 0.95},
    }.items()}
    report = build_ga_metrics_report(
        platform_observations=platform_obs,
        finance_observations=finance_obs,
        sample_count=100,
    )
    errors = validate_ga_metrics_report_strict(report)
    assert errors == [], f"Unexpected strict errors: {errors}"


def test_confidence_policy_yaml_loads():
    """Confidence policy YAML is valid and has expected keys."""
    policy_path = Path("docmirror/configs/yaml/quality/confidence_policy.yaml")
    assert policy_path.is_file()
    with open(policy_path) as f:
        policy = yaml.safe_load(f)
    assert policy["version"] == 1
    assert "default" in policy
    assert "actions" in policy
    assert policy["actions"]["high"]["output"] == "auto_accept"
    assert policy["actions"]["low"]["output"] == "needs_review"
    assert policy["actions"]["no_evidence"]["auto_accept"] is False


def test_error_envelope_matrix_complete():
    """All required P0 error codes are defined."""
    from docmirror.models.errors import DocMirrorErrorCode
    existing = {e.value for e in DocMirrorErrorCode}
    required = [
        "UNSUPPORTED_FORMAT", "TIMEOUT", "LOW_QUALITY_INPUT",
        "RESOURCE_LIMIT_EXCEEDED", "PARTIAL_PAGE_FAILURE", "EMPTY_RESULT",
        "FILE_NOT_FOUND", "FILE_EMPTY", "FILE_TOO_LARGE",
        "EXTRACTION_FAILED", "PARSER_ERROR",
    ]
    for code in required:
        assert code in existing, f"Missing P0 error code: {code}"


def test_lenient_validator_accepts_skeleton():
    """Lenient validator accepts the skeleton report (contract stability)."""
    report = build_ga_metrics_report()
    errors = validate_ga_metrics_report(report)
    assert errors == []
