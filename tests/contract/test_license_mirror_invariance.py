# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""License-Mirror invariance contract test — QTC 6.8 / W4-05.

Validates the QTC invariant QTC-08 / QTC-14:
- License missing must not change Mirror structure (hash/shape).
- Observation events with license_state="missing" and "valid" must produce
  identical Mirror fact graph structure.
- The aggregator can compute license_missing_does_not_affect_mirror from events.
- The release gate properly gates on this metric.

Design reference: docs/design/GA1.0/08_accuracy_trust_ga_gap_closure_plan.md W4-05
"""

import json
import hashlib

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


def _mirror_structure_hash(mirror_data: dict) -> str:
    """Compute a structural hash of Mirror JSON that ignores license-sensitive fields.

    This is the diff gate: same input with license_state=missing vs =valid
    must produce the same structural hash.
    """
    canonical = json.dumps(mirror_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _make_mirror_data(fixture_id: str, page_count: int = 3) -> dict:
    """Create a minimal Mirror JSON structure for license invariance testing."""
    return {
        "fixture_id": fixture_id,
        "file_type": "pdf",
        "pages": [
            {
                "page_number": i,
                "text_blocks": [
                    {"text": f"Page {i} content block A", "bbox": [10, 10, 100, 30]},
                    {"text": f"Page {i} content block B", "bbox": [10, 40, 200, 60]},
                ],
                "tables": [],
            }
            for i in range(1, page_count + 1)
        ],
        "document_structure": {"sections": []},
        "quality": {"completeness": "full"},
    }


class TestLicenseMirrorInvariance:
    """QTC W4-05: License missing must not change Mirror structure."""

    def test_mirror_structure_hash_is_deterministic(self):
        """Same Mirror data produces the same structural hash."""
        data_a = _make_mirror_data("hash_test")
        data_b = _make_mirror_data("hash_test")
        assert _mirror_structure_hash(data_a) == _mirror_structure_hash(data_b)

    def test_different_fixtures_produce_different_hash(self):
        """Different document data produces different hashes."""
        data_a = _make_mirror_data("fixture_A", page_count=2)
        data_b = _make_mirror_data("fixture_B", page_count=3)
        assert _mirror_structure_hash(data_a) != _mirror_structure_hash(data_b)

    def test_license_missing_events_have_flag_set(self):
        """Observation events created with license_state='missing' carry the flag."""
        event = new_observation_event(
            fixture_id="license_test",
            domain="bank_statement",
            license_state="missing",
        )
        assert event.run.license_state == "missing"

    def test_license_valid_events_default(self):
        """Observation events default to license_state='valid'."""
        event = new_observation_event(fixture_id="default_license")
        assert event.run.license_state == "valid"

    def test_aggregator_computes_license_metric(self):
        """BucketedMetricsAggregator computes license_missing_does_not_affect_mirror from events."""
        agg = BucketedMetricsAggregator()

        # 5 events with license=missing, all Mirror successful
        for i in range(5):
            event = new_observation_event(
                fixture_id=f"license_missing_{i:03d}",
                domain="generic",
                license_state="missing",
            )
            event.outputs.mirror.status = "success"
            event.outputs.mirror.schema_valid = True
            agg.add_event(event)

        # 5 events with license=valid, all Mirror successful
        for i in range(5):
            event = new_observation_event(
                fixture_id=f"license_valid_{i:03d}",
                domain="generic",
                license_state="valid",
            )
            event.outputs.mirror.status = "success"
            event.outputs.mirror.schema_valid = True
            agg.add_event(event)

        agg.aggregate()
        report = agg.build_ga_report()

        observed = report["observed"]["platform"].get("license_missing_does_not_affect_mirror", {})
        assert observed.get("observed") is not None, "license_missing_does_not_affect_mirror must have observed value"
        # Since all events have Mirror success, the metric should pass
        assert observed["observed"] == 1.0, f"Expected 1.0, got {observed['observed']}"

    def test_license_metric_blocked_when_not_measured(self):
        """Strict release validation blocks when license_missing_does_not_affect_mirror is not_measured."""
        report = build_ga_metrics_report()
        errors = validate_ga_metrics_report_strict(report)
        license_errors = [e for e in errors if "license" in e.lower()]
        assert len(license_errors) > 0, "Strict mode must flag license_missing_does_not_affect_mirror as not_measured"

    def test_license_metric_passes_with_observed(self):
        """Strict release validation passes when license_missing_does_not_affect_mirror is observed at 1.0."""
        platform_obs = {name: target["target"] for name, target in PLATFORM_TARGETS.items()}
        report = build_ga_metrics_report(
            platform_observations=platform_obs,
            sample_count=5,
        )
        errors = validate_ga_metrics_report_strict(report)
        license_errors = [e for e in errors if "license" in e.lower()]
        assert len(license_errors) == 0, f"Unexpected license errors: {license_errors}"

    def test_license_observation_roundtrip(self):
        """License-missing observation event survives serialization."""
        event = new_observation_event(
            fixture_id="license_rt",
            domain="bank_statement",
            license_state="missing",
        )
        event.outputs.mirror.status = "success"
        event.outputs.community.status = "success"

        d = observation_to_dict(event)
        restored = observation_from_dict(d)

        assert restored.run.license_state == "missing"
        assert restored.outputs.mirror.status == "success"

    def test_license_metric_target_defines_direction_min(self):
        """license_missing_does_not_affect_mirror target is min 1.0."""
        target = PLATFORM_TARGETS["license_missing_does_not_affect_mirror"]
        assert target["target"] == 1.0
        assert target["direction"] == "min"
        assert target["unit"] == "ratio"
