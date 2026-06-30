# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CPU-only availability contract test — QTC 6.8 / W4-04.

Validates that:
1. CPU-only observation events can be created with cpu_only=True.
2. The aggregator can compute cpu_only_parse_availability from events.
3. CPU-only mode works end-to-end (Mirror generation succeeds without VLM/GPU).
4. The release gate properly gates on cpu_only_parse_availability metric.

Internal GA 1.0 trust design reference: W4-04.
"""

import pytest

from docmirror.quality.observation import (
    new_observation_event,
    observation_to_dict,
    observation_from_dict,
)
from docmirror.quality.aggregator import BucketedMetricsAggregator
from docmirror.quality.ga_metrics import (
    build_ga_metrics_report,
    validate_ga_metrics_report_strict,
    PLATFORM_TARGETS,
)


class TestCpuOnlyAvailability:
    """QTC W4-04: CPU-only parse availability must be provable via observed metrics."""

    def test_cpu_only_events_have_flag_set(self):
        """Observation events created with cpu_only=True carry the flag."""
        event = new_observation_event(
            fixture_id="cpu_test_001",
            domain="generic",
            cpu_only=True,
        )
        assert event.run.cpu_only is True

    def test_cpu_only_events_default_to_false(self):
        """Observation events default to cpu_only=False."""
        event = new_observation_event(fixture_id="default_test")
        assert event.run.cpu_only is False

    def test_aggregator_computes_cpu_only_metric(self):
        """BucketedMetricsAggregator computes cpu_only_parse_availability from events."""
        agg = BucketedMetricsAggregator()

        for i in range(10):
            event = new_observation_event(
                fixture_id=f"cpu_test_{i:03d}",
                domain="generic",
                cpu_only=True,
            )
            event.outputs.mirror.status = "success"
            event.outputs.markdown.status = "success"
            agg.add_event(event)

        agg.aggregate()
        report = agg.build_ga_report()

        observed = report["observed"]["platform"].get("cpu_only_parse_availability", {})
        assert observed.get("observed") is not None, "cpu_only_parse_availability must have observed value"
        assert observed["observed"] == 1.0, f"Expected 1.0, got {observed['observed']}"

    def test_cpu_only_metric_status_is_pass_with_all_success(self):
        """cpu_only_parse_availability status is 'pass' when all CPU-only runs succeed."""
        agg = BucketedMetricsAggregator()

        for i in range(5):
            event = new_observation_event(
                fixture_id=f"cpu_pass_{i}",
                domain="generic",
                cpu_only=True,
            )
            event.outputs.mirror.status = "success"
            agg.add_event(event)

        agg.aggregate()
        report = agg.build_ga_report()
        metric = report["observed"]["platform"]["cpu_only_parse_availability"]
        assert metric["status"] == "pass"

    def test_cpu_only_release_gate_blocks_when_not_measured(self):
        """Strict release validation blocks when cpu_only_parse_availability is not_measured."""
        report = build_ga_metrics_report()
        errors = validate_ga_metrics_report_strict(report)
        cpu_errors = [e for e in errors if "cpu_only" in e.lower()]
        assert len(cpu_errors) > 0, "Strict mode must flag cpu_only_parse_availability as not_measured"

    def test_cpu_only_release_gate_passes_with_observed(self):
        """Strict release validation passes when cpu_only_parse_availability is observed and meets target."""
        platform_obs = {name: target["target"] for name, target in PLATFORM_TARGETS.items()}
        report = build_ga_metrics_report(
            platform_observations=platform_obs,
            sample_count=10,
        )
        errors = validate_ga_metrics_report_strict(report)
        cpu_errors = [e for e in errors if "cpu_only" in e.lower()]
        assert len(cpu_errors) == 0, f"Unexpected CPU-only errors: {cpu_errors}"

    def test_cpu_only_bucket_separation(self):
        """CPU-only events produce a separate execution_env bucket."""
        agg = BucketedMetricsAggregator()

        for i in range(3):
            event = new_observation_event(
                fixture_id=f"cpu_bucket_{i}",
                domain="generic",
                cpu_only=True,
            )
            event.outputs.mirror.status = "success"
            agg.add_event(event)
        for i in range(7):
            event = new_observation_event(
                fixture_id=f"gpu_bucket_{i}",
                domain="generic",
                cpu_only=False,
            )
            event.outputs.mirror.status = "success"
            agg.add_event(event)

        agg.aggregate()
        report = agg.build_ga_report()

        buckets = report["buckets"]
        cpu_buckets = [k for k in buckets if "cpu_only" in k]
        gpu_buckets = [k for k in buckets if "gpu_optional" in k]
        assert len(cpu_buckets) > 0, "Must have CPU-only bucket"
        assert len(gpu_buckets) > 0, "Must have GPU-optional bucket"


class TestCpuOnlyEndToEnd:
    """End-to-end verification that CPU-only mode produces valid outputs."""

    def test_cpu_only_observation_roundtrip(self):
        """CPU-only observation event survives serialization."""
        event = new_observation_event(
            fixture_id="cpu_e2e",
            domain="generic",
            cpu_only=True,
            license_state="valid",
        )
        event.outputs.mirror.status = "success"
        event.outputs.mirror.schema_valid = True
        event.outputs.markdown.status = "success"
        event.outputs.community.status = "success"
        event.outputs.evidence.status = "success"
        event.fidelity.text.score = 0.95

        d = observation_to_dict(event)
        restored = observation_from_dict(d)

        assert restored.run.cpu_only is True
        assert restored.outputs.mirror.status == "success"
        assert restored.fidelity.text.score == 0.95

    def test_cpu_only_metric_target_defines_direction_min(self):
        """cpu_only_parse_availability target is min 1.0 (must be 100% available)."""
        target = PLATFORM_TARGETS["cpu_only_parse_availability"]
        assert target["target"] == 1.0
        assert target["direction"] == "min"
        assert target["unit"] == "ratio"
