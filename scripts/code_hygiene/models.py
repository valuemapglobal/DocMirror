# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Shared data models for hygiene findings."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Category(str, Enum):
    UNUSED_IMPORT = "unused_import"
    UNUSED_VARIABLE = "unused_variable"
    UNUSED_ARGUMENT = "unused_argument"
    COMMENTED_CODE = "commented_code"
    DEAD_CODE = "dead_code"
    ORPHAN_MODULE = "orphan_module"
    ORPHAN_CONFIG = "orphan_config"
    ORPHAN_SCRIPT = "orphan_script"
    DEPRECATED_SYNTAX = "deprecated_syntax"
    ARCHITECTURE = "architecture"


@dataclass
class Finding:
    """Single hygiene issue."""

    category: Category
    severity: Severity
    message: str
    location: str = ""
    symbol: str = ""
    checker: str = ""
    hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CheckResult:
    """Outcome of one checker."""

    name: str
    findings: list[Finding] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    duration_ms: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)


@dataclass
class HygieneReport:
    """Full audit report."""

    results: list[CheckResult] = field(default_factory=list)
    version: str = "1.0"

    @property
    def findings(self) -> list[Finding]:
        out: list[Finding] = []
        for result in self.results:
            out.extend(result.findings)
        return out

    @property
    def total_errors(self) -> int:
        return sum(r.error_count for r in self.results)

    @property
    def total_warnings(self) -> int:
        return sum(r.warning_count for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "summary": {
                "errors": self.total_errors,
                "warnings": self.total_warnings,
                "findings": len(self.findings),
                "checks_run": sum(1 for r in self.results if not r.skipped),
                "checks_skipped": sum(1 for r in self.results if r.skipped),
            },
            "results": [
                {
                    "name": r.name,
                    "skipped": r.skipped,
                    "skip_reason": r.skip_reason,
                    "duration_ms": r.duration_ms,
                    "error_count": r.error_count,
                    "warning_count": r.warning_count,
                    "findings": [f.to_dict() for f in r.findings],
                }
                for r in self.results
            ],
        }
