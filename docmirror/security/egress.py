# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Egress Gateway — unified network outbound gate for all external providers.

All network outbound calls (OCR, VLM, license activate) MUST pass through the
egress gateway. The gateway enforces:
  1. Privacy mode (local blocks all network)
  2. Provider allowlist
  3. Consent requirement
  4. Audit logging of every egress event
"""

from __future__ import annotations

from typing import Any, Callable
from docmirror.security.privacy_mode import PrivacyPolicy, is_provider_allowed
from docmirror.security.data_classification import DataClassification
from docmirror.security.security_ledger import EgressEvent


class EgressBlockedError(Exception):
    """Raised when an egress attempt is blocked by privacy policy."""
    def __init__(self, reason: str, provider: str = "", component: str = ""):
        self.reason = reason
        self.provider = provider
        self.component = component
        super().__init__(f"Egress blocked: {reason} (provider={provider}, component={component})")


class EgressGate:
    """Central egress gate for all network outbound access.

    Usage::

        gate = EgressGate(policy)
        if gate.allow("openai", "vlm", destination="https://api.openai.com/..."):
            response = requests.post(...)
            gate.record("openai", "vlm", destination, result="sent")
        else:
            gate.record("openai", "vlm", destination, result="blocked", reason="local mode")
    """

    def __init__(self, policy: PrivacyPolicy, request_id: str = ""):
        self._policy = policy
        self._request_id = request_id
        self._event_counter = 0
        self._events: list[EgressEvent] = []

    @property
    def events(self) -> list[EgressEvent]:
        return list(self._events)

    def allow(
        self,
        provider: str,
        component: str,
        *,
        destination: str = "",
        data_classification: DataClassification = DataClassification.RESTRICTED,
        payload_type: str = "unknown",
        page_refs: list[int] | None = None,
    ) -> bool:
        """Check whether a specific egress is allowed under current policy.

        Returns True if the egress should proceed, False if blocked.
        """
        if not self._policy.allow_network:
            return False

        if self._policy.require_provider_allowlist:
            provider_type = _infer_provider_type(component)
            if not is_provider_allowed(provider, provider_type, self._policy):
                return False

        return True

    def record(
        self,
        provider: str,
        component: str,
        destination: str,
        *,
        result: str = "blocked",
        reason: str = "",
        data_classification: DataClassification = DataClassification.RESTRICTED,
        payload_type: str = "unknown",
        page_refs: list[int] | None = None,
        redaction_applied: bool = False,
    ) -> EgressEvent:
        """Record an egress event for audit purposes."""
        self._event_counter += 1
        event = EgressEvent(
            event_id=f"egress_{self._event_counter:04d}",
            request_id=self._request_id,
            provider=provider,
            component=component,
            destination=destination,
            data_classification=data_classification,
            payload_type=payload_type,
            page_refs=page_refs or [],
            redaction_applied=redaction_applied,
            consent_mode=self._policy.mode,
            consent_source="env:DOCMIRROR_ALLOW_NETWORK" if self._policy.allow_network else "blocked_by_policy",
            result=result,
            reason=reason,
        )
        self._events.append(event)
        return event

    def require_allow(
        self,
        provider: str,
        component: str,
        **kwargs: Any,
    ) -> None:
        """Check allow and raise EgressBlockedError if blocked.

        Convenience method for callers that want to halt on block.
        """
        if not self.allow(provider, component, **kwargs):
            raise EgressBlockedError(
                reason=f"Egress not allowed in {self._policy.mode} mode",
                provider=provider,
                component=component,
            )


def _infer_provider_type(component: str) -> str:
    """Infer the provider type from the component name."""
    if "vlm" in component.lower():
        return "vlm"
    if "ocr" in component.lower():
        return "ocr"
    if "license" in component.lower():
        return "license"
    return "unknown"
