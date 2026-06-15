# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
TQG gate report model with structured failure attribution.

Defines the ``GateReport`` dataclass used across TQG tracks to record pass/fail
status, individual check results, failure messages, and ``FailureClass`` labels
for downstream CI annotations and HTML/JSON report generation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from docmirror.eval.gates import FailureClass


@dataclass
class GateReport:
    case_id: str
    track: str = ""
    tier: str = ""
    passed: bool = True
    checks: dict[str, bool] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    failure_class: FailureClass | None = None

    def merge(self, other: GateReport) -> None:
        self.checks.update(other.checks)
        self.failures.extend(other.failures)
        self.metrics.update(other.metrics)
        if other.failure_class and not self.failure_class:
            self.failure_class = other.failure_class
        if not other.passed:
            self.passed = False
        if other.failures:
            self.passed = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "track": self.track,
            "tier": self.tier,
            "passed": self.passed,
            "checks": self.checks,
            "failures": self.failures,
            "metrics": self.metrics,
            "failure_class": self.failure_class.value if self.failure_class else None,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
