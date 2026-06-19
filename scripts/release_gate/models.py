# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Data models for the pre-release gate orchestrator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StepResult:
    """Outcome of a single gate step."""

    step_id: str
    title: str
    phase: str
    passed: bool
    duration_ms: int = 0
    skipped: bool = False
    skip_reason: str = ""
    exit_code: int | None = None
    detail: str = ""
    log_tail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GateReport:
    """Aggregated release-gate report."""

    profile: str
    results: list[StepResult] = field(default_factory=list)
    version: str = "1.0"

    @property
    def passed(self) -> bool:
        return all(r.passed or r.skipped for r in self.results)

    @property
    def failed_steps(self) -> list[StepResult]:
        return [r for r in self.results if not r.passed and not r.skipped]

    @property
    def total_ms(self) -> int:
        return sum(r.duration_ms for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile": self.profile,
            "passed": self.passed,
            "total_ms": self.total_ms,
            "failed": [r.step_id for r in self.failed_steps],
            "results": [r.to_dict() for r in self.results],
        }
