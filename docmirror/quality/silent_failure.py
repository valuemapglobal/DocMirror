"""Silent Failure Detector — W5-01 of the Failure & Degradation Contract.

Detects when a failure, degradation, fallback, low-confidence result, or
artifact anomaly occurred WITHOUT a visible outcome event or warning in the
public output. This is the core GA gate — silent_failure must be 0.

Usage::

    from docmirror.quality.silent_failure import SilentFailureDetector

    detector = SilentFailureDetector()
    findings = detector.detect(manifest=manifest_data, outcome_ledger=ledger_data,
                                artifacts_dir="/tmp/output")
    if findings:
        for f in findings:
            print(f"FAIL: {f.id} — {f.description}")
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SilentFailureFinding:
    """A single silent-failure detection result."""

    id: str
    description: str
    severity: str = "fatal"   # fatal / warning
    details: dict[str, Any] = field(default_factory=dict)


class SilentFailureDetector:
    """Checks parse/task outputs for silent failures.

    A silent failure is defined as: the system experienced a failure,
    degradation, fallback, low confidence, or artifact anomaly, but the
    public output did NOT inform the user with a stable code, warning,
    partial status, or quality report entry.
    """

    def detect(
        self,
        *,
        manifest: dict[str, Any] | None = None,
        outcome_ledger: dict[str, Any] | None = None,
        artifacts_dir: str = "",
        quality_report: dict[str, Any] | None = None,
    ) -> list[SilentFailureFinding]:
        findings: list[SilentFailureFinding] = []

        findings.extend(self._check_non_empty_mirror(manifest, artifacts_dir, outcome_ledger))
        findings.extend(self._check_artifact_consistency(manifest, artifacts_dir))
        findings.extend(self._check_fallback_lineage(outcome_ledger, quality_report))
        findings.extend(self._check_error_visibility(manifest, outcome_ledger))
        findings.extend(self._check_license_degradation(quality_report or {}, outcome_ledger))
        findings.extend(self._check_ocr_quality_visibility(outcome_ledger, quality_report))
        findings.extend(self._check_page_outcome_completeness(outcome_ledger, manifest))
        findings.extend(self._check_table_quarantine_visibility(outcome_ledger, quality_report))

        return findings

    # ── individual checks ─────────────────────────────────────────

    def _check_non_empty_mirror(
        self, manifest: dict[str, Any] | None, artifacts_dir: str, ledger: dict[str, Any] | None
    ) -> list[SilentFailureFinding]:
        findings: list[SilentFailureFinding] = []
        if not manifest or not artifacts_dir:
            return findings
        mirror_file = manifest.get("artifacts", {}).get("mirror", "")
        if not mirror_file:
            return findings
        mirror_path = os.path.join(artifacts_dir, mirror_file)
        if not os.path.exists(mirror_path):
            return findings

        try:
            with open(mirror_path, encoding="utf-8") as f:
                mirror_data = json.load(f)
        except Exception:
            return findings

        # Empty mirror is only OK if status is explicitly "failed"
        pages = mirror_data.get("data", {}).get("document", {}).get("pages", [])
        status = (ledger or {}).get("status", "success") if ledger else "success"
        if not pages and status != "failed":
            findings.append(SilentFailureFinding(
                id="silent_failure_detected",
                description="Mirror output is empty but status is not 'failed'.",
                details={"mirror_pages": 0, "status": status},
            ))
        return findings

    def _check_artifact_consistency(
        self, manifest: dict[str, Any] | None, artifacts_dir: str
    ) -> list[SilentFailureFinding]:
        findings: list[SilentFailureFinding] = []
        if not manifest or not artifacts_dir:
            return findings
        for name, artifact_path in (manifest.get("artifacts") or {}).items():
            full = os.path.join(artifacts_dir, artifact_path)
            if not os.path.exists(full):
                findings.append(SilentFailureFinding(
                    id="artifact_missing",
                    description=f"Manifest claims artifact '{name}' but file does not exist: {artifact_path}",
                    severity="warning",
                    details={"artifact_name": name, "expected_path": artifact_path},
                ))
        return findings

    def _check_fallback_lineage(
        self, ledger: dict[str, Any] | None, quality_report: dict[str, Any] | None
    ) -> list[SilentFailureFinding]:
        findings: list[SilentFailureFinding] = []
        if not ledger:
            return findings
        for event in ledger.get("events", []):
            fallback = event.get("fallback")
            if fallback and not fallback.get("reason"):
                findings.append(SilentFailureFinding(
                    id="silent_fallback_detected",
                    description=f"Fallback event {event.get('event_id')} has no 'reason'.",
                    details={"event_id": event.get("event_id"), "code": event.get("code")},
                ))
                break
        return findings

    def _check_error_visibility(
        self, manifest: dict[str, Any] | None, ledger: dict[str, Any] | None
    ) -> list[SilentFailureFinding]:
        findings: list[SilentFailureFinding] = []
        if not ledger:
            return findings
        has_error_event = any(
            e.get("status") == "failure" or e.get("severity") in ("error", "fatal")
            for e in ledger.get("events", [])
        )
        summary = ledger.get("summary", {})
        if summary.get("has_errors") and not has_error_event:
            findings.append(SilentFailureFinding(
                id="silent_failure_detected",
                description="Summary indicates errors but no error-level outcome event found.",
                details={"summary": summary},
            ))
        return findings

    def _check_license_degradation(
        self, quality_report: dict[str, Any], ledger: dict[str, Any] | None
    ) -> list[SilentFailureFinding]:
        findings: list[SilentFailureFinding] = []
        if not ledger:
            return findings
        degraded_editions = [
            e for e in ledger.get("edition_outcomes", [])
            if e.get("status") == "degraded"
        ]
        has_degradation_warning = any(
            e.get("status") == "degraded" and e.get("code", "").startswith("license")
            for e in ledger.get("events", [])
        )
        if degraded_editions and not has_degradation_warning:
            findings.append(SilentFailureFinding(
                id="silent_degradation_detected",
                description="Edition degradation without visible license warning.",
                details={"degraded_editions": [e.get("scope", {}).get("edition") for e in degraded_editions]},
            ))
        return findings

    def _check_ocr_quality_visibility(
        self, ledger: dict[str, Any] | None, quality_report: dict[str, Any] | None
    ) -> list[SilentFailureFinding]:
        findings: list[SilentFailureFinding] = []
        if not ledger:
            return findings
        low_ocr_events = [
            e for e in ledger.get("events", [])
            if e.get("code") in ("low_ocr_confidence", "low_quality_image")
        ]
        # Check if quality_report acknowledges low quality
        if low_ocr_events and quality_report and not quality_report.get("needs_review"):
            findings.append(SilentFailureFinding(
                id="silent_quality_failure_detected",
                description="Low OCR confidence events exist but quality_report has no needs_review.",
                severity="warning",
                details={"low_ocr_events": len(low_ocr_events)},
            ))
        return findings

    def _check_page_outcome_completeness(
        self, ledger: dict[str, Any] | None, manifest: dict[str, Any] | None
    ) -> list[SilentFailureFinding]:
        findings: list[SilentFailureFinding] = []
        if not ledger:
            return findings
        page_outcomes = ledger.get("page_outcomes", [])
        failed_pages = [p for p in page_outcomes if p.get("status") == "failure"]
        if failed_pages and not any(
            e.get("code") == "partial_page_failure" for e in ledger.get("events", [])
        ):
            findings.append(SilentFailureFinding(
                id="silent_page_failure_detected",
                description="Page failures present but no partial_page_failure event.",
                details={"failed_pages": [p.get("page") for p in failed_pages]},
            ))
        return findings

    def _check_table_quarantine_visibility(
        self, ledger: dict[str, Any] | None, quality_report: dict[str, Any] | None
    ) -> list[SilentFailureFinding]:
        findings: list[SilentFailureFinding] = []
        if not ledger:
            return findings
        quarantine_events = [
            e for e in ledger.get("events", [])
            if e.get("code") == "table_merge_quarantined"
        ]
        if quarantine_events:
            # Check each quarantine has a reason
            for qe in quarantine_events:
                det = qe.get("details", {})
                if not det.get("reason"):
                    findings.append(SilentFailureFinding(
                        id="silent_table_degradation_detected",
                        description=f"Table quarantine event {qe.get('event_id')} has no reason.",
                        details={"event_id": qe.get("event_id")},
                    ))
                    break
        return findings

    # ── aggregate ─────────────────────────────────────────────────

    @property
    def has_findings(self) -> bool:
        """Must be called after detect(). Returns True if any silent failures found."""
        return len(self._last_findings) > 0

    _last_findings: list[SilentFailureFinding] = []

    def detect_and_summarize(
        self,
        *,
        manifest: dict[str, Any] | None = None,
        outcome_ledger: dict[str, Any] | None = None,
        artifacts_dir: str = "",
        quality_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Detect silent failures and return a quality_report v2 summary block."""
        findings = self.detect(
            manifest=manifest,
            outcome_ledger=outcome_ledger,
            artifacts_dir=artifacts_dir,
            quality_report=quality_report,
        )
        self._last_findings = findings

        checks = [
            {"check": "non_empty_mirror", "status": "pass"},
            {"check": "artifact_manifest_consistency", "status": "pass"},
            {"check": "fallback_has_reason", "status": "pass"},
            {"check": "warnings_are_user_visible", "status": "pass"},
            {"check": "license_degradation_visible", "status": "pass"},
            {"check": "ocr_quality_visible", "status": "pass"},
            {"check": "page_outcome_complete", "status": "pass"},
            {"check": "table_quarantine_visible", "status": "pass"},
        ]

        for finding in findings:
            for check in checks:
                if finding.id.replace("_detected", "") in check["check"].replace("_", ""):
                    check["status"] = "fail"
                    check["detail"] = finding.description

        has_silent = any(f.severity == "fatal" for f in findings)

        return {
            "version": 2,
            "silent_failure": has_silent,
            "silent_failure_checks": checks,
            "silent_failure_findings": [
                {"id": f.id, "description": f.description, "severity": f.severity, "details": f.details}
                for f in findings
            ],
            "outcome_summary": (outcome_ledger or {}).get("summary", {}),
            "needs_review": self._build_needs_review(outcome_ledger or {}),
        }

    def _build_needs_review(self, ledger: dict[str, Any]) -> list[dict[str, Any]]:
        """Aggregate events that require human review."""
        needs: list[dict[str, Any]] = []
        for event in ledger.get("events", []):
            if event.get("severity") in ("degraded", "partial"):
                needs.append({
                    "event_id": event.get("event_id"),
                    "code": event.get("code"),
                    "message": event.get("message"),
                    "suggestion": event.get("suggestion"),
                })
        return needs
