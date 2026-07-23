# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Input Acceptance Report models — serialisable IAC contract."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docmirror.configs.format.models import FormatCapability


@dataclass
class InputProbeReport:
    """File-level probe: identity, integrity, basic metadata."""

    file_name: str = ""
    extension: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    checksum: str = ""
    exists: bool = False
    readable: bool = False


@dataclass
class ResourceGateReport:
    """Resource budget check result."""

    status: str = "pass"  # pass | fail
    limits: dict[str, Any] = field(default_factory=dict)
    actual: dict[str, Any] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)


@dataclass
class SafetyGateReport:
    """Safety probe result."""

    status: str = "pass"  # pass | fail | warn
    checks: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CapabilityReport:
    """FCR / Support Matrix routing result."""

    id: str = ""
    transport: str = ""
    support_status: str = ""
    requires_converter: str | None = None
    requires_dependency: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class InputDecisionReport:
    """Final acceptance decision."""

    accepted: bool = False
    outcome: str = "reject"  # parse | partial | reject
    reason: str = ""
    suggestion: str = ""


@dataclass
class InputAcceptanceReport:
    """Complete Input Acceptance Contract report — serialisable into parser_info."""

    version: int = 1
    input: InputProbeReport = field(default_factory=InputProbeReport)
    capability: CapabilityReport = field(default_factory=CapabilityReport)
    resource_gate: ResourceGateReport = field(default_factory=ResourceGateReport)
    safety_gate: SafetyGateReport = field(default_factory=SafetyGateReport)
    decision: InputDecisionReport = field(default_factory=InputDecisionReport)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "input": {
                "file_name": self.input.file_name,
                "extension": self.input.extension,
                "mime_type": self.input.mime_type,
                "size_bytes": self.input.size_bytes,
                "checksum": self.input.checksum,
                "exists": self.input.exists,
                "readable": self.input.readable,
            },
            "capability": {
                "id": self.capability.id,
                "transport": self.capability.transport,
                "support_status": self.capability.support_status,
                "requires_converter": self.capability.requires_converter,
                "requires_dependency": self.capability.requires_dependency,
                "limitations": self.capability.limitations,
            },
            "resource_gate": {
                "status": self.resource_gate.status,
                "limits": dict(self.resource_gate.limits),
                "actual": dict(self.resource_gate.actual),
                "violations": list(self.resource_gate.violations),
            },
            "safety_gate": {
                "status": self.safety_gate.status,
                "checks": dict(self.safety_gate.checks),
                "warnings": list(self.safety_gate.warnings),
            },
            "decision": {
                "accepted": self.decision.accepted,
                "outcome": self.decision.outcome,
                "reason": self.decision.reason,
                "suggestion": self.decision.suggestion,
            },
        }


@dataclass(frozen=True)
class AcceptedSource:
    """Immutable, fully-probed and content-bound input for parser dispatch.

    ``path`` points at the private accepted snapshot when ``owns_snapshot`` is
    true. ``source_path`` preserves the caller-visible identity for provenance.
    """

    path: Path
    original_name: str
    size_bytes: int
    detected_mime: str
    sha256: str
    capability: FormatCapability
    acceptance: InputAcceptanceReport
    declared_mime: str = ""
    is_forged: bool | None = None
    forgery_reasons: tuple[str, ...] = ()
    source_path: Path | None = None
    owns_snapshot: bool = False

    @property
    def display_path(self) -> Path:
        return self.source_path or self.path

    def verify_content_identity(self) -> bool:
        """Verify that the adapter input bytes still match the accepted hash."""
        digest = hashlib.sha256()
        try:
            with self.path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            return False
        return digest.hexdigest() == self.sha256

    def cleanup(self) -> None:
        """Remove an owned private snapshot. Safe to call more than once."""
        if not self.owns_snapshot:
            return
        try:
            self.path.unlink(missing_ok=True)
        finally:
            shutil.rmtree(self.path.parent, ignore_errors=True)


class InputRejectedError(ValueError):
    """Raised when an input cannot be converted into an AcceptedSource."""

    def __init__(self, report: InputAcceptanceReport):
        self.report = report
        self.code = str(report.decision.reason or "INPUT_REJECTED").split(":", 1)[0]
        super().__init__(str(report.decision.reason or "Input rejected"))


__all__ = [
    "AcceptedSource",
    "CapabilityReport",
    "InputAcceptanceReport",
    "InputDecisionReport",
    "InputProbeReport",
    "InputRejectedError",
    "ResourceGateReport",
    "SafetyGateReport",
]
