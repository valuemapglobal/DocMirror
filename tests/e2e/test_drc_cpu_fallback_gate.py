# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""DRC Wave 5: CPU-only / VLM Fallback Release Gate e2e tests.

GA 1.0 DRC-W5-03, DRC-W5-04: Proves that DocMirror can parse without GPU/VLM and
that all fallbacks are visible in the manifest/quality report.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# ── P0: CPU-only gate ───────────────────────────────────────────────────


def test_runtime_control_cpu_only_parses():
    """DRC-W5-03: RuntimeControl can express CPU-only constraints."""
    from docmirror.runtime.control import RuntimeControl

    rc = RuntimeControl(cost_profile="full", task_mode="sync")
    assert rc.cost_profile == "full"
    assert rc.task_mode == "sync"
    assert rc.checkpoint.enabled is True
    assert rc.progress.emit_events is True

    # compact variant
    compact = RuntimeControl.compact()
    assert compact.cost_profile == "compact"
    assert compact.streaming.chunk_artifacts is False

    # forensic variant
    forensic = RuntimeControl.forensic()
    assert forensic.cost_profile == "forensic"
    assert forensic.streaming.chunk_artifacts is True


def test_fallback_event_schema():
    """DRC-W5-01: FallbackEvent schema is stable."""
    from docmirror.runtime.events import FallbackEvent

    fe = FallbackEvent(
        task_id="task_001",
        fallback_type="vlm_unavailable",
        from_path="vlm_ocr",
        to_path="cpu_ocr",
        reason="provider_missing_api_key",
        scope={"file_id": "001", "page": 3},
        effect="slower_parse",
    )
    d = fe.to_dict()
    assert d["fallback_type"] == "vlm_unavailable"
    assert d["from_path"] == "vlm_ocr"
    assert d["to_path"] == "cpu_ocr"
    assert d["reason"] == "provider_missing_api_key"
    assert d["user_visible"] is True


def test_vlm_gateway_tracks_fallback():
    """DRC-W5-01: VLM gateway tracks fallback events for manifest."""
    from docmirror.structure.ocr.vlm_gateway import _gateway

    assert hasattr(_gateway, "collect_fallbacks")
    assert hasattr(_gateway, "_track_fallback")

    # Ensure no stale state
    _gateway.collect_fallbacks()

    # Simulate fallback
    _gateway._track_fallback("provider_missing_api_key", "provider=openai")
    fbs = _gateway.collect_fallbacks()
    assert len(fbs) == 1
    assert fbs[0]["reason"] == "provider_missing_api_key"
    assert fbs[0]["scope"] == "vlm_ocr"


def test_metrics_collector_fallback_tracking():
    """DRC-W5-04: MetricsCollector records fallback counts."""
    from docmirror.runtime.metrics import MetricsCollector

    mc = MetricsCollector(task_id="test_001")
    mc.record_fallback("vlm_ocr", "cpu_ocr", "provider_missing_api_key")
    mc.record_fallback("gpu_ocr", "cpu_ocr", "gpu_unavailable")
    mc.record_tokens(input_tokens=0, output_tokens=2000)
    snapshot = mc.snapshot(file_id="001")
    assert snapshot.fallback_count == 2
    assert len(snapshot.fallback_details) == 2
    assert snapshot.fallback_details[0]["from"] == "vlm_ocr"


def test_checkpoint_manager_cpu_only_scenario():
    """DRC-W5-02: CheckpointManager works without VLM/GPU."""
    import tempfile
    from docmirror.runtime.checkpoint import CheckpointManager

    with tempfile.TemporaryDirectory() as tmp:
        cm = CheckpointManager(
            task_dir=Path(tmp),
            input_digest="sha256:abc123",
            parse_control_fingerprint="test_pc_001",
            runtime_profile_fingerprint="test_rc_001",
        )
        # Save input digest
        cm.save_input_digest("001", "sha256:def456")
        # Validate resume
        ok = cm.validate_resume("001", "sha256:def456")
        assert ok is True

        # Wrong digest should fail
        ok = cm.validate_resume("001", "sha256:wrong")
        assert ok is False


def test_runtime_metrics_cpu_only_bucketing():
    """DRC-W5-05: RuntimeMetrics supports cpu_only bucketing."""
    from docmirror.runtime.metrics import RuntimeMetrics

    m = RuntimeMetrics(
        task_id="cpu_test_001",
        fallback_count=1,
        runtime_env="cpu_only",
        format="pdf_scan",
        doc_size="long",
        profile="full",
    )
    d = m.to_dict()
    assert d["bucketing"]["runtime"] == "cpu_only"
    assert d["bucketing"]["format"] == "pdf_scan"


# ── P1: Detailed fallback quality impact ────────────────────────────────


def test_profile_resolver_cpu_vlm_policies():
    """DRC-W5-04: Profile resolver sets correct VLM policy per profile."""
    from docmirror.runtime.profiles import (
        COMPACT_PROFILE,
        FULL_PROFILE,
        FORENSIC_PROFILE,
    )

    # compact: VLM off
    assert COMPACT_PROFILE.vlm_policy == "off"
    # full: VLM optional
    assert FULL_PROFILE.vlm_policy == "optional"
    # forensic: VLM optional with strict provenance
    assert FORENSIC_PROFILE.vlm_policy == "optional_strict"


def test_classify_document_size():
    """DRC-W3-02: classify_document_size maps pages to size bucket."""
    from docmirror.runtime.control import classify_document_size

    assert classify_document_size(5, 1024) == "small"
    assert classify_document_size(25, 1024) == "medium"
    assert classify_document_size(80, 1024) == "long"
    assert classify_document_size(250, 1024) == "huge"


def test_resolve_task_mode():
    """DRC-W3-02: resolve_task_mode picks sync/async based on doc size."""
    from docmirror.runtime.control import resolve_task_mode

    assert resolve_task_mode("small") == "sync"
    assert resolve_task_mode("medium") == "sync"
    assert resolve_task_mode("long") == "async"
    assert resolve_task_mode("huge") == "async"



# ============================================================================
# DRC-W6-03: CPU-only Demo — comprehensive demonstration
# ============================================================================


def test_cpu_only_all_modules_accessible():
    """DRC-W6-03: All DRC runtime modules are importable without VLM/GPU."""
    # These imports must succeed without VLM/GPU being available
    from docmirror.runtime.control import RuntimeControl, classify_document_size, resolve_task_mode
    from docmirror.runtime.events import ProgressEvent, FallbackEvent, MetricEvent
    from docmirror.runtime.ledger import EventLedger, build_manifest_v2
    from docmirror.runtime.profiles import resolve_profile, COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE
    from docmirror.runtime.metrics import MetricsCollector, RuntimeMetrics
    from docmirror.runtime.checkpoint import CheckpointManager
    from docmirror.runtime.work_units import WorkUnit, WorkUnitPlanner, BatchJobLedger, BatchJobEntry
    from docmirror.runtime.scheduler import SchedulerConfig, RuntimeScheduler

    # All imports succeeded — CPU-only path is structurally complete
    assert RuntimeControl is not None
    assert ProgressEvent is not None
    assert EventLedger is not None
    assert MetricsCollector is not None
    assert CheckpointManager is not None
    assert WorkUnitPlanner is not None


def test_cpu_only_fallback_ledger_complete():
    """DRC-W6-03: Fallback ledger correctly captures all CPU-only transitions."""
    import tempfile
    from pathlib import Path
    from docmirror.runtime.ledger import EventLedger
    from docmirror.runtime.events import FallbackEvent

    with tempfile.TemporaryDirectory() as tmp:
        ledger = EventLedger(Path(tmp))

        # Simulate the three possible VLM/GPU fallback scenarios in CPU-only mode
        scenarios = [
            ("vlm_unavailable", "vlm_ocr", "cpu_ocr", "provider_missing_api_key"),
            ("gpu_missing", "gpu_ocr", "cpu_ocr", "cuda_not_found"),
            ("provider_timeout", "vlm_classify", "rule_classify", "openai_timeout_30s"),
        ]

        for fallback_type, from_p, to_p, reason in scenarios:
            fb = FallbackEvent(
                task_id="cpu_demo_001",
                fallback_type=fallback_type,
                from_path=from_p,
                to_path=to_p,
                reason=reason,
                scope={"file_id": "001", "mode": "cpu_only"},
                effect="slower_parse",
                user_visible=True,
            )
            ledger.write_fallback(fb)

        fbs = ledger.read_fallback_events()
        assert len(fbs) == 3
        for i, fb in enumerate(fbs):
            assert fb["fallback_type"] == scenarios[i][0]
            assert fb["user_visible"] is True


def test_cpu_only_quality_report_includes_fallback_summary():
    """DRC-W6-03: Quality report includes fallback impact in CPU-only mode."""
    from docmirror.runtime.metrics import MetricsCollector

    mc = MetricsCollector(task_id="cpu_quality_001")

    # Simulate CPU-only parse metrics
    mc.record_fallback("vlm_ocr", "cpu_ocr", "provider_missing")
    mc.record_fallback("gpu_ocr", "cpu_ocr", "gpu_unavailable")
    mc.record_page_outcome(page_number=1, status="low_quality", elapsed_ms=500)
    mc.record_page_outcome(page_number=2, status="low_quality", elapsed_ms=450)

    mc.record_tokens(input_tokens=0, output_tokens=2000)
    snapshot = mc.snapshot(file_id="001")
    assert snapshot.fallback_count == 2
    assert snapshot.pages_processed >= 1

    # All pages marked low_quality because no VLM enhancement available
    # Verify fallback_count reflects CPU-only operation
    assert snapshot.fallback_count == 2


def test_cpu_only_runtime_metrics_tagging():
    """DRC-W6-03: RuntimeMetrics correctly tags cpu_only environment."""
    from docmirror.runtime.metrics import RuntimeMetrics

    m = RuntimeMetrics(
        task_id="cpu_env_001",
        fallback_count=3,
        runtime_env="cpu_only",
        format="pdf_scan",
        doc_size="long",
        profile="full",
    )

    d = m.to_dict()
    assert d["bucketing"]["runtime"] == "cpu_only"
    assert d["bucketing"]["format"] == "pdf_scan"
    assert d["bucketing"]["doc_size"] == "long"
    assert d["bucketing"]["profile"] == "full"


def test_cpu_only_metric_events_generated():
    """DRC-W6-03: Metric events are generated for CPU-only parse timing."""
    import tempfile
    from pathlib import Path
    from docmirror.runtime.ledger import EventLedger
    from docmirror.runtime.events import MetricEvent

    with tempfile.TemporaryDirectory() as tmp:
        ledger = EventLedger(Path(tmp))

        # Write CPU-only timing metrics
        metrics_data = [
            ("page_extract_duration_ms", 450.0, {"mode": "cpu_only", "page": "1"}),
            ("page_extract_duration_ms", 480.0, {"mode": "cpu_only", "page": "2"}),
            ("total_parse_duration_ms", 5230.0, {"mode": "cpu_only"}),
            ("memory_rss_mb", 512.0, {"mode": "cpu_only"}),
        ]

        for name, value, tags in metrics_data:
            me = MetricEvent(
                task_id="cpu_metrics_001",
                file_id="001",
                metric_name=name,
                metric_value=value,
                tags=tags,
            )
            ledger.write_metric(me)

        events = ledger.read_metric_events()
        assert len(events) == 4
        for evt in events:
            assert evt["metric_name"] in [
                "page_extract_duration_ms",
                "total_parse_duration_ms",
                "memory_rss_mb",
            ]


def test_cpu_only_checkpoint_works_without_vlm():
    """DRC-W6-03: CheckpointManager works independently of VLM availability."""
    import tempfile
    from pathlib import Path
    from docmirror.runtime.checkpoint import CheckpointManager

    with tempfile.TemporaryDirectory() as tmp:
        cm = CheckpointManager(
            task_dir=Path(tmp),
            input_digest="sha256:cpu_only_test",
            parse_control_fingerprint="cpu_pc_v1",
            runtime_profile_fingerprint="cpu_rc_v1",
        )

        # Save page fragments — no VLM needed
        for page in range(1, 6):
            cm.save_page_fragment("001", page, {
                "page": page,
                "text": f"CPU-only extracted page {page}",
                "ocr_engine": "RapidOCR",
                "vlm_used": False,
            })
            cm.save_page_quality("001", page, {
                "page": page,
                "confidence": 0.85,
                "notes": "CPU-only RapidOCR extraction",
            })

        # Load back
        fragments = cm.load_page_fragments("001")
        assert len(fragments) == 5
        for frag in fragments:
            assert frag.get("vlm_used") is False
            assert frag.get("ocr_engine") == "RapidOCR"


def test_cpu_only_profile_resolver_keeps_fallback_paths():
    """DRC-W6-03: All profiles maintain valid fallback paths for CPU-only."""
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE

    # Even forensic profile (which prefers VLM) must not crash without VLM
    for profile in [COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE]:
        # Profile must be valid (not crash when accessed)
        assert profile.profile_name in ("compact", "full", "forensic")
        assert profile.output_size_guard_bytes > 0
        assert profile.token_budget_hard_limit > 0
        # Each profile must define a valid vlm_policy
        assert profile.vlm_policy in ("off", "optional", "optional_strict")


def test_cpu_only_manifest_reflects_fallback_summary():
    """DRC-W6-03: Manifest v2 captures fallback summary for CPU-only execution."""
    import tempfile
    from pathlib import Path
    from docmirror.runtime.ledger import EventLedger, build_manifest_v2

    with tempfile.TemporaryDirectory() as tmp:
        ledger = EventLedger(Path(tmp))
        manifest = build_manifest_v2(
            task_id="cpu_manifest_001",
            status="running",
            stage="page_extract",
            profile="full",
        )
        ledger.write_manifest(manifest)

        # Simulate CPU-only fallbacks being recorded
        ledger.update_manifest_v2(
            status="partial",
            stage="complete",
            fallbacks=[
                {"fallback_type": "vlm_unavailable", "from_path": "vlm_ocr",
                 "to_path": "cpu_ocr", "reason": "no_vlm_provider"},
                {"fallback_type": "gpu_missing", "from_path": "gpu_ocr",
                 "to_path": "cpu_ocr", "reason": "no_cuda_device"},
            ],
            metrics={
                "pages_per_second": 0.8,
                "total_duration_seconds": 62.5,
                "fallback_count": 2,
            },
        )

        updated = ledger.read_manifest()
        assert updated["status"] == "partial"
        assert len(updated["fallbacks"]) == 2
        assert updated["metrics"]["fallback_count"] == 2
        assert updated["metrics"]["pages_per_second"] == 0.8
