# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Security Evidence Ledger — per-parse security audit trail.

Produces a lightweight security summary for each parse task. Tracks:
  - Privacy mode used
  - Egress events (network outbound)
  - Resource gate decisions
  - Redaction events
  - License boundary state
  - Support bundle redaction safety
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from docmirror.security.data_classification import DataClassification


@dataclass
class EgressEvent:
    """A single network outbound event."""
    event_id: str
    request_id: str
    provider: str
    component: str
    destination: str
    data_classification: DataClassification = DataClassification.RESTRICTED
    payload_type: str = "unknown"
    page_refs: list[int] = field(default_factory=list)
    redaction_applied: bool = False
    consent_mode: str = "unknown"
    consent_source: str = ""
    result: str = "blocked"
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "request_id": self.request_id,
            "provider": self.provider,
            "component": self.component,
            "destination": self.destination,
            "data_classification": self.data_classification.label,
            "payload_type": self.payload_type,
            "page_refs": self.page_refs,
            "redaction_applied": self.redaction_applied,
            "consent": {
                "mode": self.consent_mode,
                "source": self.consent_source,
            },
            "result": self.result,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass
class ResourceGateDecision:
    """Decision from a resource gate check."""
    component: str
    status: str  # pass / blocked / warning
    code: str
    input_metrics: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status,
            "code": self.code,
            "input": self.input_metrics,
            "limits": self.limits,
        }


@dataclass
class SecurityEvidenceLedger:
    """Per-parse security evidence record."""
    version: int = 1
    request_id: str = ""
    privacy_mode: str = "local"
    data_classification: DataClassification = DataClassification.CONFIDENTIAL
    egress_events: list[EgressEvent] = field(default_factory=list)
    resource_gate_decisions: list[ResourceGateDecision] = field(default_factory=list)
    redaction_events: list[dict[str, Any]] = field(default_factory=list)
    license_boundary: dict[str, Any] = field(default_factory=lambda: {
        "license_state_in_mirror": False,
        "edition_only": True,
    })
    support_bundle: dict[str, Any] = field(default_factory=lambda: {
        "profile": "redacted",
        "redaction_safe": True,
    })

    def add_egress(self, event: EgressEvent) -> None:
        self.egress_events.append(event)

    def add_resource_decision(self, decision: ResourceGateDecision) -> None:
        self.resource_gate_decisions.append(decision)

    def add_redaction_event(self, event: dict[str, Any]) -> None:
        self.redaction_events.append(event)

    @property
    def network_egress_allowed(self) -> bool:
        return any(e.result == "sent" for e in self.egress_events)

    @property
    def all_resource_gates_pass(self) -> bool:
        if not self.resource_gate_decisions:
            return True
        return all(d.status == "pass" for d in self.resource_gate_decisions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "request_id": self.request_id,
            "privacy_mode": self.privacy_mode,
            "data_classification": self.data_classification.label,
            "egress_events": [e.to_dict() for e in self.egress_events],
            "resource_gate_decisions": [d.to_dict() for d in self.resource_gate_decisions],
            "redaction_events": self.redaction_events,
            "license_boundary": self.license_boundary,
            "support_bundle": self.support_bundle,
        }


def build_security_summary(ledger: SecurityEvidenceLedger) -> dict[str, Any]:
    """Build a lightweight security summary for inclusion in parse result / manifest."""
    return {
        "privacy_mode": ledger.privacy_mode,
        "network_egress": "allowed" if ledger.network_egress_allowed else "blocked",
        "external_providers": list(
            set(e.provider for e in ledger.egress_events if e.result == "sent")
        ),
        "resource_gate": "pass" if ledger.all_resource_gates_pass else "fail",
        "redaction_profile": ledger.support_bundle.get("profile", "redacted"),
        "support_bundle_redaction_safe": ledger.support_bundle.get("redaction_safe", True),
    }
