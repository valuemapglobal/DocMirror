# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Progress Signal Bus — push-based phase-aware progress reporting.

GA 1.0 §4 (IPB): The ProgressBus replaces time-based heuristic progress
with real phase-level and per-item progress emitted by each pipeline component.
Events are written to the EventLedger for persistence and forwarded to CLI /
REST / SDK consumers via an optional callback.

Key exports: ``ProgressSignal``, ``ProgressCallback``, ``ProgressBus``.

Dependencies: ``runtime.events.ProgressEvent``, ``runtime.ledger.EventLedger``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ProgressSignal:
    """A single progress datapoint emitted by a pipeline component.

    Attributes:
        phase: Canonical phase name (e.g. "load_document", "page_extraction").
        phase_pct: Progress within this phase (0.0–100.0).
        overall_pct: Estimated progress across the entire pipeline (0.0–100.0).
        message: Human-readable description shown in CLI progress bar.
        detail: Optional structured metadata for SDK / REST consumers.
        timestamp: Unix timestamp (seconds) when the signal was emitted.
    """

    phase: str
    phase_pct: float
    overall_pct: float
    message: str
    detail: dict[str, Any] | None = None
    timestamp: float = field(default_factory=time.time)


ProgressCallback = Callable[[ProgressSignal], None] | None
"""Optional callback receiving real-time ProgressSignal instances."""


@dataclass
class PhaseWeight:
    """Weight and display configuration for a single pipeline phase."""

    pct: float
    per_page: bool = False
    detail: str = ""
    sub_phases: list[dict[str, Any]] = field(default_factory=list)


_DEFAULT_PHASE_WEIGHTS: dict[str, PhaseWeight] = {
    "load_document": PhaseWeight(pct=5.0, detail="Loading document..."),
    "page_extraction": PhaseWeight(pct=70.0, per_page=True, detail="Extracting page {page}/{total}..."),
    "cross_page_merge": PhaseWeight(pct=1.0, detail="Merging cross-page tables..."),
    "middleware_pipeline": PhaseWeight(pct=2.0, detail="Running validation & enrichment middlewares..."),
    "community_plugin": PhaseWeight(pct=7.0, detail="Building community edition output..."),
    "extended_plugins": PhaseWeight(
        pct=15.0,
        detail="Building enterprise/finance edition outputs...",
        sub_phases=[
            {"name": "enterprise", "pct": 50.0, "detail": "Enterprise plugins..."},
            {"name": "finance", "pct": 50.0, "detail": "Finance plugins..."},
        ],
    ),
}

_DEFAULT_PHASE_ORDER: list[str] = [
    "load_document",
    "page_extraction",
    "cross_page_merge",
    "middleware_pipeline",
    "community_plugin",
    "extended_plugins",
]


@lru_cache(maxsize=1)
def _load_phase_weights() -> dict[str, PhaseWeight]:
    """Load phase weights from YAML config, falling back to built-in defaults."""
    try:
        from docmirror.configs.paths import PIPELINE_WEIGHTS_YAML

        if PIPELINE_WEIGHTS_YAML.is_file():
            import yaml
            with open(PIPELINE_WEIGHTS_YAML, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            phases = data.get("phases") or {}
            weights: dict[str, PhaseWeight] = {}
            for name, raw in phases.items():
                sub_phases = [
                    {"name": s.get("name", ""), "pct": s.get("pct", 100.0), "detail": s.get("detail", "")}
                    for s in (raw.get("sub_phases") or [])
                ]
                weights[name] = PhaseWeight(
                    pct=float(raw.get("pct", 0)),
                    per_page=bool(raw.get("per_page", False)),
                    detail=str(raw.get("detail", "")),
                    sub_phases=sub_phases,
                )
            return weights
    except Exception as exc:
        logger.debug("[ProgressBus] Failed to load weights from yaml: %s", exc)
    return dict(_DEFAULT_PHASE_WEIGHTS)


@lru_cache(maxsize=1)
def _load_phase_order() -> dict[str, int]:
    """Load canonical phase ordering from YAML config or built-in defaults."""
    try:
        from docmirror.configs.paths import PIPELINE_WEIGHTS_YAML

        if PIPELINE_WEIGHTS_YAML.is_file():
            import yaml
            with open(PIPELINE_WEIGHTS_YAML, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            phases = data.get("phases") or {}
            return {name: idx for idx, name in enumerate(phases.keys())}
    except Exception as exc:
        logger.debug("[ProgressBus] Failed to load phase order: %s", exc)
    return {name: idx for idx, name in enumerate(_DEFAULT_PHASE_ORDER)}


class ProgressBus:
    """Push-based progress bus with callback and EventLedger persistence.

    Usage::

        bus = ProgressBus(on_progress=my_cli_callback)
        bus.bind_ledger(EventLedger(task_dir))
        bus.emit("load_document", 50.0, "Loading half the document...")
    """

    def __init__(self, on_progress: ProgressCallback = None) -> None:
        self._callback = on_progress
        self._event_ledger: Any = None
        self._phase_weights = _load_phase_weights()
        self._phase_order = _load_phase_order()
        self._completed_before: dict[str, float] = {}
        self._total_weight: float = sum(w.pct for w in self._phase_weights.values())

    def emit(
        self,
        phase: str,
        phase_pct: float,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Emit a progress signal.

        Args:
            phase: Canonical phase name matching pipeline_weights.yaml.
            phase_pct: Progress within this phase (0.0–100.0).
            message: Human-readable description.
            detail: Optional structured metadata.
        """
        overall = self._to_overall(phase, phase_pct)
        signal = ProgressSignal(
            phase=phase,
            phase_pct=phase_pct,
            overall_pct=overall,
            message=message,
            detail=detail,
        )
        if self._callback is not None:
            try:
                self._callback(signal)
            except Exception as exc:
                logger.debug("[ProgressBus] Callback error: %s", exc)

        if self._event_ledger is not None:
            try:
                from docmirror.runtime.events import ProgressEvent

                self._event_ledger.write_progress(
                    ProgressEvent(
                        stage=phase,
                        progress={"phase_pct": phase_pct, "overall_pct": overall},
                        message=message,
                    )
                )
            except Exception as exc:
                logger.debug("[ProgressBus] Ledger write error: %s", exc)

    def bind_ledger(self, ledger: Any) -> None:
        """Attach an EventLedger instance for ndjson persistence."""
        self._event_ledger = ledger

    def _to_overall(self, phase: str, phase_pct: float) -> float:
        """Map phase-local progress to overall pipeline percentage.

        The overall percentage is the sum of all completed phases before this one,
        plus the current phase's weight scaled by its local progress.
        """
        weight = self._phase_weights.get(phase)
        if weight is None:
            return 0.0

        if phase not in self._completed_before:
            completed = sum(
                w.pct
                for p, w in self._phase_weights.items()
                if self._phase_order.get(p, 99) < self._phase_order.get(phase, 99)
            )
            self._completed_before[phase] = completed

        return self._completed_before[phase] + weight.pct * phase_pct / 100.0

    @property
    def total_weight(self) -> float:
        return self._total_weight


__all__ = [
    "ProgressBus",
    "ProgressCallback",
    "ProgressSignal",
    "PhaseWeight",
]
