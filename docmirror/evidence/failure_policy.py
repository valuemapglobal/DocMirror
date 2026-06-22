# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Domain Failure Policy Resolver — W2-03 / W2-04.

Reads the failure taxonomy from ``domain_contracts/community_core.yaml`` and
resolves a domain extraction outcome into one of the standard failure statuses:
``success``, ``partial_low_confidence``, ``partial_missing_required``,
``unsupported_variant``, ``empty_input``, ``low_quality_input``,
``domain_mismatch``, ``plugin_error``, ``fallback_generic``.

Key exports: ``resolve_failure``, ``FailureDecision``, ``DOMAIN_FAILURE_TAXONOMY``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONTRACTS_PATH = (
    Path(__file__).resolve().parents[1] / "configs" / "yaml" / "domain_contracts" / "community_core.yaml"
)


@dataclass
class FailureDecision:
    status: str  # one of the failure taxonomy keys
    success: bool = False
    needs_review: bool = False
    fallback_from_domain: str | None = None
    fallback_reason: str | None = None
    missing_fields: list[str] = field(default_factory=list)
    unsupported_reason: str | None = None
    affected_pages: list[int] = field(default_factory=list)
    retry_suggestion: str | None = None
    error_code: str | None = None
    warnings: list[str] = field(default_factory=list)


DOMAIN_FAILURE_TAXONOMY = {
    "success": "P0 fields/records meet gate; domain contract passes",
    "partial_low_confidence": "Results exist but confidence is low; mark needs_review",
    "partial_missing_required": "P0 fields missing; output extracted results + missing_fields list",
    "unsupported_variant": "Belongs to domain but style unsupported; output Mirror/Evidence + unsupported_reason",
    "empty_input": "No parseable facts; stable error envelope, no empty-success JSON",
    "low_quality_input": "OCR/scan quality insufficient; affected_pages + retry suggestion + needs_review",
    "domain_mismatch": "Classification vs plugin mismatch; fallback to generic or mirror-only explicitly",
    "plugin_error": "Plugin exception; no traceback exposed; partial/mirror + error_code",
    "fallback_generic": "Core domain failed; enters generic fallback with fallback_from_domain + fallback_reason",
}


def _load_taxonomy() -> dict[str, str]:
    if not CONTRACTS_PATH.exists():
        return dict(DOMAIN_FAILURE_TAXONOMY)
    try:
        with open(CONTRACTS_PATH, encoding="utf-8") as fh:
            contracts = yaml.safe_load(fh) or {}
        taxonomy = contracts.get("failure_taxonomy") or {}
        return {k: v.get("description", "") for k, v in taxonomy.items()} if taxonomy else dict(DOMAIN_FAILURE_TAXONOMY)
    except Exception:
        return dict(DOMAIN_FAILURE_TAXONOMY)


def resolve_failure(
    *,
    domain: str,
    has_fields: bool = False,
    has_records: bool = False,
    confidence: float = 0.0,
    missing_fields: list[str] | None = None,
    is_empty: bool = False,
    is_low_quality: bool = False,
    is_unsupported: bool = False,
    plugin_exception: Exception | None = None,
    domain_mismatch: bool = False,
    fallback_to_generic: bool = False,
    fallback_from: str | None = None,
    fallback_reason: str | None = None,
) -> FailureDecision:
    """Resolve a domain extraction outcome into a standard failure status.

    Returns a ``FailureDecision`` with the canonical status and
    appropriate metadata for the edition envelope.
    """
    if plugin_exception is not None:
        return FailureDecision(
            status="plugin_error",
            success=False,
            needs_review=True,
            error_code="PLUGIN_ERROR",
            warnings=[f"{domain}: plugin error — {plugin_exception}"],
        )

    if domain_mismatch:
        return FailureDecision(
            status="domain_mismatch",
            success=False,
            needs_review=True,
            fallback_from_domain=domain,
            fallback_reason="classification_domain_mismatch",
        )

    if is_empty:
        return FailureDecision(
            status="empty_input",
            success=False,
            missing_fields=list(missing_fields or []),
        )

    if is_low_quality:
        return FailureDecision(
            status="low_quality_input",
            success=False,
            needs_review=True,
            retry_suggestion="Consider re-scanning or higher-resolution input",
        )

    if is_unsupported:
        return FailureDecision(
            status="unsupported_variant",
            success=False,
            needs_review=True,
            unsupported_reason=f"{domain}: document variant not supported",
        )

    if fallback_to_generic:
        return FailureDecision(
            status="fallback_generic",
            success=False,
            needs_review=True,
            fallback_from_domain=fallback_from or domain,
            fallback_reason=fallback_reason or "core_domain_fallback",
        )

    missing = list(missing_fields or [])
    if missing:
        return FailureDecision(
            status="partial_missing_required",
            success=False,
            needs_review=True,
            missing_fields=missing,
        )

    if confidence < 0.5 and (has_fields or has_records):
        return FailureDecision(
            status="partial_low_confidence",
            success=False,
            needs_review=True,
        )

    # Success
    return FailureDecision(
        status="success",
        success=True,
    )


def apply_failure_to_envelope(
    envelope: dict[str, Any],
    decision: FailureDecision,
) -> dict[str, Any]:
    """Apply a ``FailureDecision`` to an Edition JSON envelope in-place.

    Adds ``status``, ``metadata.domain_ga``, ``data.missing_fields``,
    and ``data.needs_review`` blocks as appropriate.
    """
    status_block = envelope.setdefault("status", {})
    status_block["success"] = decision.success
    status_block["status"] = decision.status
    if decision.warnings:
        status_block.setdefault("warnings", []).extend(decision.warnings)

    meta = envelope.setdefault("metadata", {})
    domain_ga = meta.setdefault("domain_ga", {})
    if decision.fallback_from_domain:
        domain_ga["fallback_from_domain"] = decision.fallback_from_domain
    if decision.fallback_reason:
        domain_ga["fallback_reason"] = decision.fallback_reason
    if decision.error_code:
        domain_ga["error_code"] = decision.error_code

    data = envelope.setdefault("data", {})
    if decision.missing_fields:
        data["missing_fields"] = decision.missing_fields
    if decision.needs_review:
        data["needs_review"] = data.get("needs_review") or True
    if decision.unsupported_reason:
        data["unsupported_reason"] = decision.unsupported_reason
    if decision.retry_suggestion:
        data["retry_suggestion"] = decision.retry_suggestion

    return envelope
