# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for unified quality gate (hygiene + release profiles)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Add scripts/validate to sys.path so audit_core_imports can be imported

from scripts.release_gate.config import PROFILES, steps_for_profile
from scripts.release_gate.models import GateReport, StepResult
from scripts.release_gate.report import format_markdown
from scripts.release_gate.runner import _run_hygiene
from scripts.validate.audit_core_imports import audit_failures, run_audit


def test_gate_profiles_have_steps():
    for profile in PROFILES:
        steps = steps_for_profile(profile)
        assert steps, f"profile {profile} has no steps"


def test_quick_is_faster_subset():
    quick = steps_for_profile("quick")
    standard = steps_for_profile("standard")
    assert len(quick) < len(standard)
    quick_phases = {s.phase for s in quick}
    assert quick_phases <= {s.phase for s in standard}


def test_gate_report_passed_property():
    report = GateReport(
        profile="quick",
        results=[
            StepResult("a", "A", "style", passed=True, duration_ms=1),
            StepResult("b", "B", "style", passed=True, skipped=True, duration_ms=0),
        ],
    )
    assert report.passed
    report.results.append(StepResult("c", "C", "tests", passed=False, duration_ms=2))
    assert not report.passed
    assert report.failed_steps[0].step_id == "c"


def test_markdown_report_includes_profile():
    report = GateReport(profile="standard", results=[])
    md = format_markdown(report)
    assert "standard" in md


def test_audit_failures_empty_on_clean_repo():
    data = run_audit()
    assert audit_failures(data) == []


def test_hygiene_fast_step_passes():
    from scripts.release_gate.config import STEPS

    step = next(s for s in STEPS if s.step_id == "hygiene_fast")
    result = _run_hygiene(step)
    assert result.passed, result.detail


def test_overall_percent():
    from scripts.release_gate.progress import ProgressRow, QualityGateProgress

    progress = QualityGateProgress(
        profile="quick",
        rows=[
            ProgressRow("a", "A", "style", state="pass", duration_ms=10),
            ProgressRow("b", "B", "style", state="running"),
            ProgressRow("c", "C", "tests"),
        ],
        enabled=False,
    )
    assert progress.completed_count == 1
    assert progress.overall_percent == 33


def test_format_duration_ms():
    from scripts.release_gate.progress import _format_duration_ms

    assert _format_duration_ms(500) == "500ms"
    assert _format_duration_ms(2500) == "2.5s"
    assert _format_duration_ms(125000) == "2m 5s"


def test_quality_gate_cli_hygiene_profile():
    from scripts.run_quality_gate import main

    assert main.__module__ == "scripts.run_quality_gate"
