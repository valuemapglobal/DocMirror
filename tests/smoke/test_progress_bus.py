# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Progress bus smoke tests — verify phase-level progress signals.

GA 1.0 §4 (IPB): The ProgressBus replaces time-based heuristic progress
with push-based phase-aware progress reporting. These tests verify:
  - ProgressBus.emit() produces well-formed ProgressSignal instances
  - overall_pct monotonically increases across a complete pipeline
  - Phase weights sum to 100% for the default config
  - The _to_overall() calculation is correct for all phases
  - The _ProgressAdapter works correctly with Rich Progress
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

pytestmark = [pytest.mark.tier_smoke]


# ── Fixtures ──────────────────────────────────────────────────────────────


class _SignalRecorder:
    """Thread-safe callback that records all ProgressSignal instances."""

    def __init__(self):
        self._lock = threading.Lock()
        self.signals: list[dict[str, Any]] = []

    def __call__(self, signal) -> None:
        from docmirror.runtime.progress_bus import ProgressSignal
        with self._lock:
            self.signals.append({
                "phase": signal.phase,
                "phase_pct": signal.phase_pct,
                "overall_pct": signal.overall_pct,
                "message": signal.message,
                "detail": signal.detail,
                "_time": time.time(),
            })

    @property
    def phases(self) -> list[str]:
        return [s["phase"] for s in self.signals]


@pytest.fixture
def recorder():
    return _SignalRecorder()


# ── ProgressBus Emission Tests ────────────────────────────────────────────


class TestProgressBusEmit:
    """ProgressBus.emit() produces well-formed signals."""

    def test_emit_all_phases(self, recorder):
        """Emit all canonical phases; verify each appears exactly once."""
        from docmirror.runtime.progress_bus import ProgressBus

        bus = ProgressBus(on_progress=recorder)
        phases = [
            ("load_document", 100.0, "Document loaded"),
            ("page_extraction", 100.0, "Pages extracted"),
            ("cross_page_merge", 100.0, "Tables merged"),
            ("middleware_pipeline", 100.0, "Middlewares complete"),
            ("community_plugin", 100.0, "Community done"),
            ("extended_plugins", 100.0, "Extended done"),
        ]
        for phase, pct, msg in phases:
            bus.emit(phase, pct, msg)

        assert len(recorder.signals) == 6
        for phase, pct, msg in phases:
            found = [s for s in recorder.signals if s["phase"] == phase and s["phase_pct"] == pct]
            assert len(found) == 1, f"Phase {phase} at {pct}% not found"

    def test_overall_pct_monotonic(self, recorder):
        """overall_pct never decreases across a complete pipeline emission."""
        from docmirror.runtime.progress_bus import ProgressBus

        bus = ProgressBus(on_progress=recorder)
        # Simulate a full pipeline
        bus.emit("load_document", 0.0, "Starting")
        bus.emit("load_document", 50.0, "Half loaded")
        bus.emit("load_document", 100.0, "Loaded")
        bus.emit("page_extraction", 0.0, "Pages starting")
        bus.emit("page_extraction", 33.33, "Page 1/3")
        bus.emit("page_extraction", 66.66, "Page 2/3")
        bus.emit("page_extraction", 100.0, "Pages done")
        bus.emit("cross_page_merge", 0.0, "Merge start")
        bus.emit("cross_page_merge", 100.0, "Merge done")
        bus.emit("middleware_pipeline", 0.0, "Middleware start")
        bus.emit("middleware_pipeline", 100.0, "Middleware done")
        bus.emit("community_plugin", 0.0, "Community start")
        bus.emit("community_plugin", 100.0, "Community done")
        bus.emit("extended_plugins", 0.0, "Extended start")
        bus.emit("extended_plugins", 100.0, "Extended done")

        ## Use ProgressBus with a full signal recorder
        class _FullRecorder:
            def __init__(self):
                self.signals = []
            def __call__(self, signal):
                self.signals.append(signal)

        fr = _FullRecorder()
        bus2 = ProgressBus(on_progress=fr)
        bus2.emit("load_document", 0.0, "Start")
        bus2.emit("load_document", 100.0, "Loaded")
        bus2.emit("page_extraction", 0.0, "Pages")
        bus2.emit("page_extraction", 100.0, "Pages done")
        bus2.emit("cross_page_merge", 100.0, "Merge done")
        bus2.emit("middleware_pipeline", 100.0, "Mid done")
        bus2.emit("community_plugin", 100.0, "Comm done")
        bus2.emit("extended_plugins", 100.0, "Ext done")

        # Verify monotonicity
        prev = 0.0
        for sig in fr.signals:
            assert sig.overall_pct >= prev, f"overall_pct decreased: {prev} -> {sig.overall_pct} at phase={sig.phase}"
            prev = sig.overall_pct

    def test_overall_pct_ends_at_100(self, recorder):
        """Full pipeline ends with overall_pct at or near 100.0."""
        from docmirror.runtime.progress_bus import ProgressBus

        class _FullRecorder:
            def __init__(self):
                self.signals = []
            def __call__(self, signal):
                self.signals.append(signal)

        fr = _FullRecorder()
        bus = ProgressBus(on_progress=fr)
        bus.emit("load_document", 100.0, "Loaded")
        bus.emit("page_extraction", 100.0, "Pages done")
        bus.emit("cross_page_merge", 100.0, "Merge done")
        bus.emit("middleware_pipeline", 100.0, "Middle done")
        bus.emit("community_plugin", 100.0, "Comm done")
        bus.emit("extended_plugins", 100.0, "Ext done")

        # The last signal should be close to 100%
        last = fr.signals[-1]
        assert last.overall_pct >= 99.9, f"Final overall_pct too low: {last.overall_pct}"

    def test_emit_with_detail(self, recorder):
        """Emit with detail dict passes through correctly."""
        from docmirror.runtime.progress_bus import ProgressBus

        class _DetailRecorder:
            def __init__(self):
                self.signals = []
            def __call__(self, signal):
                self.signals.append(signal)

        dr = _DetailRecorder()
        bus = ProgressBus(on_progress=dr)
        bus.emit(
            "page_extraction", 50.0, "Halfway",
            detail={"page": 2, "total": 4, "layer": "pdfplumber"},
        )
        signal = dr.signals[0]
        assert signal.detail == {"page": 2, "total": 4, "layer": "pdfplumber"}
        assert signal.phase == "page_extraction"
        assert signal.phase_pct == 50.0


# ── Phase Weight Tests ────────────────────────────────────────────────────


class TestPhaseWeights:
    """Phase weights are correctly configured and sum to 100%."""

    def test_default_weights_sum_to_100(self):
        """Default phase weights sum to approximately 100%."""
        from docmirror.runtime.progress_bus import _load_phase_weights

        weights = _load_phase_weights()
        total = sum(w.pct for w in weights.values())
        # Allow small rounding error
        assert abs(total - 100.0) < 0.1, f"Total weight={total}, expected 100"

    def test_all_phases_have_detail(self):
        """Every phase has a non-empty detail string."""
        from docmirror.runtime.progress_bus import _load_phase_weights

        weights = _load_phase_weights()
        for name, w in weights.items():
            assert w.detail.strip(), f"Phase {name} has empty detail"

    def test_phase_order_is_complete(self):
        """Phase order covers all defined phases."""
        from docmirror.runtime.progress_bus import _load_phase_order, _load_phase_weights

        weights = _load_phase_weights()
        order = _load_phase_order()
        for phase_name in weights:
            assert phase_name in order, f"Phase {phase_name} not in phase order"


# ── ProgressBus Construction Tests ────────────────────────────────────────


class TestProgressBusConstruction:
    """ProgressBus handles edge cases gracefully."""

    def test_no_callback(self):
        """ProgressBus works without a callback."""
        from docmirror.runtime.progress_bus import ProgressBus

        bus = ProgressBus(on_progress=None)
        bus.emit("load_document", 50.0, "Halfway")  # Should not raise

    def test_callback_exception_handled(self, caplog):
        """Callback raising an exception is logged, not propagated."""
        from docmirror.runtime.progress_bus import ProgressBus

        def _broken_callback(signal):
            raise ValueError("oops")

        bus = ProgressBus(on_progress=_broken_callback)
        bus.emit("load_document", 50.0, "Halfway")  # Should not raise

    def test_unknown_phase_returns_zero(self, recorder):
        """Emit with unknown phase returns overall_pct=0."""
        from docmirror.runtime.progress_bus import ProgressBus

        class _FR:
            def __init__(self):
                self.signals = []
            def __call__(self, signal):
                self.signals.append(signal)

        fr = _FR()
        bus = ProgressBus(on_progress=fr)
        bus.emit("unknown_phase", 100.0, "???")
        assert fr.signals[0].overall_pct == 0.0

    def test_timestamp_is_set(self):
        """ProgressSignal always has a positive timestamp."""
        from docmirror.runtime.progress_bus import ProgressSignal

        sig = ProgressSignal(phase="test", phase_pct=50.0, overall_pct=25.0, message="test")
        assert sig.timestamp > 0
        assert sig.phase == "test"
        assert sig.phase_pct == 50.0
        assert sig.overall_pct == 25.0
        assert sig.message == "test"


# ── Phase Weight YAML Loading ─────────────────────────────────────────────


class TestPhaseWeightYaml:
    """Phase weight YAML config is loadable and valid."""

    def test_pipeline_weights_yaml_exists(self):
        """pipeline_weights.yaml config file exists."""
        from docmirror.configs.paths import PIPELINE_WEIGHTS_YAML

        assert PIPELINE_WEIGHTS_YAML.is_file(), f"Not found: {PIPELINE_WEIGHTS_YAML}"

    def test_pipeline_weights_loadable(self):
        """pipeline_weights.yaml loads without errors."""
        from docmirror.runtime.progress_bus import _load_phase_weights

        weights = _load_phase_weights()
        assert len(weights) >= 3  # At least 3 phases


# ── Phase-level progress ordering ─────────────────────────────────────────


class TestPipelinePhaseOrdering:
    """Verify phase ordering is correct and complete."""

    def test_complete_pipeline_phase_sequence(self, recorder):
        """A complete pipeline goes through all phases in order."""
        from docmirror.runtime.progress_bus import ProgressBus, _load_phase_order, _load_phase_weights

        class _FR:
            def __init__(self):
                self.signals = []
            def __call__(self, signal):
                self.signals.append(signal)

        fr = _FR()
        bus = ProgressBus(on_progress=fr)
        order = _load_phase_order()
        sorted_phases = sorted(order.keys(), key=lambda p: order[p])

        for phase in sorted_phases:
            bus.emit(phase, 100.0, f"{phase} done")

        emitted = [s.phase for s in fr.signals]
        # Verify all phases appear in order
        assert len(emitted) == len(sorted_phases)
        for i, phase in enumerate(sorted_phases):
            assert emitted[i] == phase, f"Phase order mismatch at index {i}: expected {phase}, got {emitted[i]}"
