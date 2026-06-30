# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Visual Drilldown contract test — QTC W5-04.

Validates the drilldown pipeline:
- DrilldownSession collects targets from observation events
- Targets are correctly classified by layer, domain, severity
- Overlay dict is suitable for visual_debug.html consumption
- Page-level failures are included as drilldown targets

Internal GA 1.0 trust design reference: W5-04.
"""

from docmirror.quality.observation import (
    new_observation_event,
    PageOutcome,
)
from docmirror.quality.visual_drilldown import (
    DrilldownSession,
    DrilldownTarget,
)


class TestDrilldownSession:
    """QTC W5-04: Visual debug drilldown from metric to page/field/bbox."""

    def test_empty_session(self):
        """Empty session has no targets."""
        session = DrilldownSession()
        assert len(session.targets) == 0
        assert session.pages_with_issues() == set()

    def test_session_collects_failing_metrics(self):
        """Failing metrics produce drilldown targets."""
        session = DrilldownSession()
        event = new_observation_event(fixture_id="drill_001", domain="bank_statement")
        event.fidelity.layout.metrics["reading_order_accuracy"] = 0.85
        event.fidelity.layout.evidence_refs = ["page:1"]
        session.add_from_observation(event)
        assert len(session.targets) >= 1

    def test_page_outcome_becomes_target(self):
        """Page partial/failure outcomes produce drilldown targets."""
        session = DrilldownSession()
        event = new_observation_event(fixture_id="page_fail", domain="generic")
        event.failure.partial_pages = [
            PageOutcome(page=3, status="partial", error_code="LOW_QUALITY_INPUT")
        ]
        session.add_from_observation(event)
        page_targets = [t for t in session.targets if t.metric_name == "page_outcome"]
        assert len(page_targets) == 1
        assert page_targets[0].page_number == 3

    def test_by_domain_filter(self):
        """DrilldownSession.by_domain() filters correctly."""
        session = DrilldownSession()

        e1 = new_observation_event(fixture_id="d1", domain="bank_statement")
        e1.fidelity.layout.metrics["reading_order_accuracy"] = 0.85
        session.add_from_observation(e1)

        e2 = new_observation_event(fixture_id="d2", domain="vat_invoice")
        e2.fidelity.business.metrics["amount_accuracy"] = 0.94
        session.add_from_observation(e2)

        bank = session.by_domain("bank_statement")
        vat = session.by_domain("vat_invoice")
        assert len(bank) == 1
        assert len(vat) == 1

    def test_by_layer_filter(self):
        """DrilldownSession.by_layer() filters correctly."""
        session = DrilldownSession()

        e1 = new_observation_event(fixture_id="l1", domain="generic")
        e1.fidelity.layout.metrics["reading_order_accuracy"] = 0.85
        session.add_from_observation(e1)

        e2 = new_observation_event(fixture_id="l2", domain="generic")
        e2.fidelity.business.metrics["amount_accuracy"] = 0.94
        session.add_from_observation(e2)

        assert len(session.by_layer("layout")) >= 1
        assert len(session.by_layer("business")) >= 1

    def test_by_severity_filter(self):
        """DrilldownSession.by_severity() filters correctly."""
        session = DrilldownSession()

        e1 = new_observation_event(fixture_id="s1", domain="generic")
        e1.fidelity.layout.metrics["reading_order_accuracy"] = 0.85  # large gap -> error or critical
        session.add_from_observation(e1)

        e2 = new_observation_event(fixture_id="s2", domain="generic")
        e2.fidelity.layout.metrics["bbox_coverage"] = 0.94  # small gap -> warning
        session.add_from_observation(e2)

        errors = session.by_severity("error")
        warnings = session.by_severity("warning")
        assert len(errors) + len(warnings) >= 2

    def test_overlay_dict_structure(self):
        """to_overlay_dict() produces the expected structure."""
        session = DrilldownSession()

        e1 = new_observation_event(fixture_id="ov1", domain="bank_statement")
        e1.fidelity.layout.metrics["reading_order_accuracy"] = 0.85
        e1.fidelity.layout.evidence_refs = ["page:1", "bbox:10:20:200:50"]
        session.add_from_observation(e1)

        overlay = session.to_overlay_dict()
        assert "drilldown_version" in overlay
        assert overlay["drilldown_version"] == 1
        assert "total_targets" in overlay
        assert "pages_with_issues" in overlay
        assert "by_page" in overlay
        assert "by_layer" in overlay
        assert "1" in overlay["by_page"]

    def test_summary_dict_structure(self):
        """to_summary_dict() produces the expected structure."""
        session = DrilldownSession()

        e1 = new_observation_event(fixture_id="sum1", domain="bank_statement")
        e1.fidelity.layout.metrics["reading_order_accuracy"] = 0.85
        session.add_from_observation(e1)

        summary = session.to_summary_dict()
        assert "total_drilldown_targets" in summary
        assert "pages_with_issues" in summary
        assert "targets_by_layer" in summary
        assert "targets_by_severity" in summary
        assert "top_failing_metrics" in summary

    def test_events_with_all_passing_metrics_produce_no_targets(self):
        """Events where all metrics pass produce zero drilldown targets."""
        session = DrilldownSession()
        event = new_observation_event(fixture_id="all_pass", domain="generic")
        # No failing metrics
        event.fidelity.text.metrics["cer"] = 0.01  # below 5% max target
        event.fidelity.text.metrics["char_preservation_rate"] = 0.99  # above 95% min target
        session.add_from_observation(event)
        # CER has max direction at 5%, 1% is pass
        # char_preservation has min direction at 95%, 99% is pass
        assert len(session.targets) == 0

    def test_event_with_multiple_layer_failures(self):
        """A single event with failures across multiple layers produces multiple targets."""
        session = DrilldownSession()
        event = new_observation_event(fixture_id="multi_fail", domain="bank_statement")
        event.fidelity.text.metrics["cer"] = 0.10  # fails: > 5%
        event.fidelity.layout.metrics["reading_order_accuracy"] = 0.80  # fails: < 98%
        event.fidelity.business.metrics["amount_accuracy"] = 0.90  # fails: < 99%
        session.add_from_observation(event)
        assert len(session.targets) >= 3
