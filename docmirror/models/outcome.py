"""OutcomeEvent and OutcomeLedger — unified failure/degradation accounting.

Every DocMirror operation emits an Outcome Ledger. Every non-perfect outcome
has a typed event with scope, code, severity, recoverability, evidence,
retained_output, and suggestion. This module provides the canonical data model
so CLI / SDK / REST / Task / Manifest / Quality Report share the same facts.

Usage::

    from docmirror.models.outcome import OutcomeEvent, OutcomeLedger

    ledger = OutcomeLedger(request_id="req_...")
    ledger.add_event(OutcomeEvent(
        status="partial",
        code="low_ocr_confidence",
        canonical_code="LOW_OCR_CONFIDENCE",
        category="ocr",
        severity="partial",
        scope={"type": "page", "pages": [2, 5]},
        message="OCR confidence below threshold on pages 2, 5.",
        suggestion="Retry with profile=forensic or rescan at 300 DPI.",
    ))
    print(ledger.to_dict())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ── helpers ────────────────────────────────────────────────────────


def _now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _event_counter() -> int:
    _event_counter._count += 1  # type: ignore[attr-defined]
    return _event_counter._count  # type: ignore[attr-defined]


_event_counter._count = 0  # type: ignore[attr-defined]


# ── OutcomeEvent ───────────────────────────────────────────────────


@dataclass
class OutcomeEvent:
    """One success / partial / warning / failure / fallback / degradation event.

    Every outcome event is a typed fact that carries enough context for any
    surface (CLI, REST, SDK, manifest, quality report) to display or act on it
    without consulting internal logs.
    """

    # ── identity ──
    event_id: str = field(default_factory=lambda: f"outcome_{_event_counter():05d}")
    status: Literal["success", "warning", "degraded", "partial", "failure"] = "success"
    code: str = ""  # user_code, e.g. "low_ocr_confidence"
    canonical_code: str = ""  # e.g. "LOW_OCR_CONFIDENCE"
    category: str = "parse"  # input / parse / ocr / table / license / domain / runtime / artifact

    # ── severity & recoverability ──
    severity: Literal["info", "warning", "degraded", "partial", "error", "fatal"] = "info"
    recoverable: bool = False
    retryable: bool = False

    # ── scope ──
    scope: dict[str, Any] = field(default_factory=dict)
    # Typed keys: type (document/page/table/field/edition/task),
    #             pages (list[int]), tables (list[str]),
    #             fields (list[str]), edition (str), domain (str)

    # ── human-readable ──
    message: str = ""
    suggestion: str = ""
    docs_anchor: str = ""

    # ── detail & evidence ──
    details: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)

    # ── fallback lineage ──
    fallback: dict[str, Any] | None = None
    # e.g. {"from_domain": "audit_report", "to_domain": "generic",
    #       "reason": "domain_not_ga", "support_level": "L0"}

    # ── retained output ──
    retained_output: dict[str, Any] = field(default_factory=dict)
    # e.g. {"mirror": True, "markdown": True, "edition": "partial"}

    # ── provenance ──
    source: dict[str, Any] = field(default_factory=dict)
    # e.g. {"plane": "Parse Plane", "component": "ocr_quality_gate", "version": "1"}
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "status": self.status,
            "code": self.code,
            "canonical_code": self.canonical_code,
            "category": self.category,
            "severity": self.severity,
            "scope": self.scope,
            "message": self.message,
            "details": self.details,
            "evidence_refs": self.evidence_refs,
            "retained_output": self.retained_output,
            "fallback": self.fallback,
            "recoverable": self.recoverable,
            "retryable": self.retryable,
            "suggestion": self.suggestion,
            "docs_anchor": self.docs_anchor,
            "source": self.source,
            "timestamp": self.timestamp,
        }


# ── PageOutcome ─────────────────────────────────────────────────────


@dataclass
class PageOutcome:
    """Per-page outcome entry in the OutcomeLedger."""

    page: int
    status: Literal["success", "partial", "failure"] = "success"
    events: list[OutcomeEvent] = field(default_factory=list)
    retained: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "status": self.status,
            "events": [e.to_dict() for e in self.events],
            "retained": self.retained,
            "metadata": self.metadata,
        }


# ── OutcomeLedger ───────────────────────────────────────────────────


@dataclass
class OutcomeLedger:
    """The single source of truth for all outcomes of one parse/task.

    Every CLI / SDK / REST / Task / Manifest surface reads from this ledger
    to produce consistent status, warnings, errors, and suggestions.
    """

    version: int = 1
    request_id: str = ""
    task_id: str = ""
    document_id: str = ""

    status: Literal["success", "partial", "degraded", "failed"] = "success"
    events: list[OutcomeEvent] = field(default_factory=list)
    page_outcomes: list[PageOutcome] = field(default_factory=list)
    artifact_outcomes: list[OutcomeEvent] = field(default_factory=list)
    edition_outcomes: list[OutcomeEvent] = field(default_factory=list)

    # ── event management ──

    def add_event(self, event: OutcomeEvent) -> None:
        self.events.append(event)
        self._recompute_status()

    def add_page_outcome(self, po: PageOutcome) -> None:
        self.page_outcomes.append(po)
        self._recompute_status()

    def add_artifact_outcome(self, event: OutcomeEvent) -> None:
        self.artifact_outcomes.append(event)
        self._recompute_status()

    def add_edition_outcome(self, event: OutcomeEvent) -> None:
        self.edition_outcomes.append(event)
        self._recompute_status()

    def _recompute_status(self) -> None:
        """Derive aggregate status from all events and page outcomes."""
        all_ev = self.events + self.artifact_outcomes + self.edition_outcomes

        has_failure = any(e.status == "failure" or e.severity in ("error", "fatal") for e in all_ev)
        has_partial = any(e.status == "partial" or e.severity == "partial" for e in all_ev)
        has_degraded = any(e.status == "degraded" or e.severity == "degraded" for e in all_ev)
        any_page_failure = any(po.status == "failure" for po in self.page_outcomes)
        any_page_success = any(po.status in ("success", "partial") for po in self.page_outcomes)

        if self.page_outcomes and not any_page_success:
            self.status = "failed"
        elif has_failure and any_page_success:
            self.status = "partial"
        elif has_failure:
            self.status = "failed"
        elif has_partial or any_page_failure:
            self.status = "partial"
        elif has_degraded:
            self.status = "degraded"
        else:
            self.status = "success"

    # ── summary ──

    @property
    def summary(self) -> dict[str, Any]:
        """Compute summary suitable for manifest, quality_report, REST response."""
        all_ev = self.events + self.artifact_outcomes + self.edition_outcomes
        has_errors = any(e.status == "failure" or e.severity in ("error", "fatal") for e in all_ev)
        has_warnings = any(e.status == "warning" or e.severity == "warning" for e in all_ev)
        has_degradations = any(e.status == "degraded" or e.severity == "degraded" for e in all_ev)
        any_retainable = any(e.retryable or e.recoverable for e in all_ev if e.status != "success")
        retained_pages = all(po.retained for po in self.page_outcomes if po.status != "failure")

        return {
            "has_errors": has_errors,
            "has_warnings": has_warnings,
            "has_degradations": has_degradations,
            "events_count": len(self.events),
            "errors_count": sum(1 for e in all_ev if e.status == "failure" or e.severity in ("error", "fatal")),
            "warnings_count": sum(1 for e in all_ev if e.status == "warning" or e.severity == "warning"),
            "degradations_count": sum(1 for e in all_ev if e.status == "degraded" or e.severity == "degraded"),
            "retained_success_pages": retained_pages,
            "retryable": any_retainable,
        }

    # ── serialization ──

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "document_id": self.document_id,
            "status": self.status,
            "events": [e.to_dict() for e in self.events],
            "page_outcomes": [p.to_dict() for p in self.page_outcomes],
            "artifact_outcomes": [a.to_dict() for a in self.artifact_outcomes],
            "edition_outcomes": [a.to_dict() for a in self.edition_outcomes],
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutcomeLedger:
        """Reconstruct from serialized form."""
        ledger = cls(
            version=data.get("version", 1),
            request_id=data.get("request_id", ""),
            task_id=data.get("task_id", ""),
            document_id=data.get("document_id", ""),
            status=data.get("status", "success"),
        )
        for e in data.get("events", []):
            ledger.events.append(OutcomeEvent(**{k: v for k, v in e.items() if k in OutcomeEvent.__dataclass_fields__}))
        for p in data.get("page_outcomes", []):
            po = PageOutcome(
                page=p.get("page", 0),
                status=p.get("status", "success"),
                retained=p.get("retained", True),
                metadata=p.get("metadata", {}),
            )
            po.events = [
                OutcomeEvent(**{k: v for k, v in ev.items() if k in OutcomeEvent.__dataclass_fields__})
                for ev in p.get("events", [])
            ]
            ledger.page_outcomes.append(po)
        for a in data.get("artifact_outcomes", []):
            ledger.artifact_outcomes.append(
                OutcomeEvent(**{k: v for k, v in a.items() if k in OutcomeEvent.__dataclass_fields__})
            )
        for ed in data.get("edition_outcomes", []):
            ledger.edition_outcomes.append(
                OutcomeEvent(**{k: v for k, v in ed.items() if k in OutcomeEvent.__dataclass_fields__})
            )
        return ledger
