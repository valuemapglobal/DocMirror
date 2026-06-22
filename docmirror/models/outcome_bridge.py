"""Bridge helpers — connect existing error paths to OutcomeEvent / OutcomeLedger.

This module provides lightweight adapters so dispatcher, pipeline, task executor,
and other existing code paths can emit OutcomeEvents and flush OutcomeLedgers
without importing heavy dependencies or rewriting core logic.

Usage (from dispatcher / pipeline)::

    from docmirror.models.outcome_bridge import emit_format_failure
    emit_format_failure("UNSUPPORTED_FORMAT", file_path="/tmp/doc.wps",
                        output_dir="/tmp/output", request_id="req_001")
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from docmirror.configs.failure_codes import registry
from docmirror.models.outcome import OutcomeEvent, OutcomeLedger, PageOutcome


def _make_outcome_event(
    canonical_code: str,
    *,
    status: str = "failure",
    message: str = "",
    details: dict[str, Any] | None = None,
    scope_override: dict[str, Any] | None = None,
    fallback: dict[str, Any] | None = None,
    suggestion_override: str = "",
    evidence_refs: list[str] | None = None,
    source_component: str = "unknown",
) -> OutcomeEvent:
    """Build an OutcomeEvent from a registered canonical code."""
    entry = registry.lookup_canonical(canonical_code)
    if not entry:
        entry = registry.lookup("unknown")
    if not entry:
        return OutcomeEvent(
            status=status,
            code=canonical_code.lower(),
            canonical_code=canonical_code,
            category="parse",
            severity="error",
            message=message or canonical_code,
        )

    return OutcomeEvent(
        status=status,
        code=entry.user_code,
        canonical_code=entry.canonical_code,
        category=entry.category,
        severity=entry.severity,
        scope=scope_override or {"type": entry.default_scope},
        message=message or entry.default_message,
        suggestion=suggestion_override or entry.default_suggestion,
        docs_anchor=entry.docs_anchor,
        details=details or {},
        recoverable=entry.recoverable,
        retryable=entry.retryable,
        evidence_refs=evidence_refs or [],
        fallback=fallback,
        source={"plane": "Integration Plane", "component": source_component, "version": "1"},
    )


def emit_format_failure(
    canonical_code: str,
    *,
    file_path: str = "",
    output_dir: str = "",
    request_id: str = "",
    details: dict[str, Any] | None = None,
) -> OutcomeEvent:
    """Emit an outcome event for format/input failures (dispatcher, FCR).

    Returns the event so callers can attach it to the result or ledger.
    If ``output_dir`` is provided, also writes a minimal ``outcome_ledger.json``.
    """
    event = _make_outcome_event(
        canonical_code,
        status="failure",
        scope_override={"type": "document", "format": Path(file_path).suffix if file_path else "unknown"},
        details=details or {},
        source_component="dispatcher.fcr",
        evidence_refs=[f"file:{file_path}"] if file_path else [],
    )

    if output_dir:
        _write_minimal_ledger(output_dir, request_id=request_id, events=[event], status="failed")

    return event


def emit_page_outcome(
    page: int,
    status: str,
    *,
    events: list[OutcomeEvent] | None = None,
    retained: bool = True,
    metadata: dict[str, Any] | None = None,
) -> PageOutcome:
    """Create a single PageOutcome entry for the OutcomeLedger."""
    return PageOutcome(
        page=page,
        status=status,  # type: ignore[arg-type]
        events=events or [],
        retained=retained,
        metadata=metadata or {},
    )


def emit_table_quarantine_outcome(
    *,
    table_ref: str = "",
    page: int = 0,
    reason: str = "",
    action: str = "standalone_physical_table",
    source_refs: list[str] | None = None,
) -> OutcomeEvent:
    """Emit a table_merge_quarantined outcome event."""
    return _make_outcome_event(
        "TABLE_MERGE_QUARANTINED",
        status="degraded",
        scope_override={"type": "table", "pages": [page] if page else [], "tables": [table_ref] if table_ref else []},
        details={"reason": reason, "action": action},
        source_component="table.merger",
        evidence_refs=source_refs or [],
    )


def emit_license_degradation(
    *,
    edition: str = "enterprise",
    reason: str = "license_missing",
    suggestion_override: str = "",
) -> OutcomeEvent:
    """Emit a license_missing_degraded or license_invalid outcome event."""
    canonical = "LICENSE_MISSING_DEGRADED" if reason == "license_missing" else "LICENSE_INVALID"
    return _make_outcome_event(
        canonical,
        status="degraded",
        scope_override={"type": "edition", "edition": edition},
        fallback={"from": edition, "to": "community", "reason": reason},
        suggestion_override=suggestion_override,
        source_component="edition.availability",
        details={"mirror_unaffected": True},
    )


def emit_domain_fallback(
    *,
    from_domain: str = "",
    to_domain: str = "generic",
    reason: str = "domain_not_ga",
    support_level: str = "L0",
    dgc_status: str = "candidate",
) -> OutcomeEvent:
    """Emit a domain fallback outcome event."""
    code_map = {
        "domain_not_ga": "DOMAIN_NOT_GA_FALLBACK",
        "domain_low_confidence": "DOMAIN_LOW_CONFIDENCE_FALLBACK",
        "domain_extraction_failed": "DOMAIN_EXTRACTION_FAILED_FALLBACK",
    }
    canonical = code_map.get(reason, "DOMAIN_NOT_GA_FALLBACK")
    return _make_outcome_event(
        canonical,
        status="degraded",
        scope_override={"type": "document", "domain": from_domain},
        fallback={
            "from_domain": from_domain,
            "to_domain": to_domain,
            "reason": reason,
            "support_level": support_level,
            "dgc_status": dgc_status,
        },
        source_component="domain.router",
    )


def emit_runtime_outcome(
    canonical_code: str,
    *,
    message: str = "",
    details: dict[str, Any] | None = None,
    scope_override: dict[str, Any] | None = None,
    suggestion_override: str = "",
) -> OutcomeEvent:
    """Emit a runtime/resource outcome event (timeout, resource limit, etc.)."""
    return _make_outcome_event(
        canonical_code,
        status="failure" if canonical_code != "STAGE_TIMEOUT" else "partial",
        message=message,
        details=details or {},
        scope_override=scope_override,
        suggestion_override=suggestion_override,
        source_component="runtime.controller",
    )


# ── ledger persistence ─────────────────────────────────────────────

def _write_minimal_ledger(
    output_dir: str,
    *,
    request_id: str = "",
    task_id: str = "",
    events: list[OutcomeEvent] | None = None,
    page_outcomes: list[PageOutcome] | None = None,
    status: str = "success",
) -> str:
    """Write a minimal outcome_ledger.json to disk. Returns the file path."""
    os.makedirs(output_dir, exist_ok=True)
    ledger = OutcomeLedger(
        request_id=request_id,
        task_id=task_id,
        status=status,  # type: ignore[arg-type]
        events=events or [],
        page_outcomes=page_outcomes or [],
    )
    path = os.path.join(output_dir, "outcome_ledger.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ledger.to_dict(), f, indent=2, ensure_ascii=False, default=str)
    return path


def flush_ledger(
    ledger: OutcomeLedger,
    output_dir: str,
) -> str:
    """Persist a full OutcomeLedger to ``outcome_ledger.json``."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "outcome_ledger.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ledger.to_dict(), f, indent=2, ensure_ascii=False, default=str)
    return path
