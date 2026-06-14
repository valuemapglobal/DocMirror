# TQG extract audit oracle helpers

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.report import GateReport


def run_extraction_audit_oracle(
    meta: dict[str, Any],
    audit_spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "",
) -> GateReport:
    """Validate extraction_audit schema from CoreExtractor perf_breakdown."""
    report = GateReport(case_id=case_id, track=track, tier=tier)
    base = meta.get("base")
    if base is None:
        report.passed = False
        report.failures.append("audit oracle: missing base metadata")
        return report

    perf = base.metadata.get("perf_breakdown") or {}
    audit = perf.get("extraction_audit") or {}
    if not audit:
        report.passed = False
        report.failures.append("audit oracle: extraction_audit missing")
        return report

    profile_id = audit_spec.get("profile_id")
    if profile_id:
        ok = audit.get("profile_id") == profile_id
        report.checks["audit_profile_id"] = ok
        if not ok:
            report.passed = False
            report.failures.append(
                f"audit profile_id expected {profile_id!r}, got {audit.get('profile_id')!r}"
            )

    min_pages = audit_spec.get("min_audit_pages")
    if min_pages is not None:
        pages = audit.get("pages") or []
        ok = len(pages) >= int(min_pages)
        report.checks["audit_min_pages"] = ok
        report.metrics["audit_page_count"] = len(pages)
        if not ok:
            report.passed = False
            report.failures.append(f"audit pages {len(pages)} < {min_pages}")

    primary_rows = audit_spec.get("primary_logical_rows")
    if primary_rows is not None:
        ok = audit.get("primary_logical_rows") == int(primary_rows)
        report.checks["audit_primary_logical_rows"] = ok
        if not ok:
            report.passed = False
            report.failures.append(
                f"audit primary_logical_rows expected {primary_rows}, got {audit.get('primary_logical_rows')}"
            )

    quarantine_page = audit_spec.get("quarantine_page")
    if quarantine_page is not None:
        qpages = audit.get("quarantined_pages") or []
        match = next((q for q in qpages if q.get("page") == int(quarantine_page)), None)
        ok = match is not None
        report.checks["audit_quarantine_page"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"audit quarantine page {quarantine_page} not found")
        elif loss_reason := audit_spec.get("quarantine_loss_reason"):
            lr_ok = match.get("loss_reason") == loss_reason
            report.checks["audit_quarantine_loss_reason"] = lr_ok
            if not lr_ok:
                report.passed = False
                report.failures.append(
                    f"quarantine loss_reason expected {loss_reason!r}, got {match.get('loss_reason')!r}"
                )

    if audit_spec.get("require_bcs_candidates"):
        pages = audit.get("pages") or []
        bcs_pages = [p for p in pages if p.get("candidates")]
        ok = bool(bcs_pages)
        report.checks["audit_bcs_candidates"] = ok
        if not ok:
            report.passed = False
            report.failures.append("audit: no BCS candidate pages")
        elif bcs_pages:
            sample = bcs_pages[0]
            for key in ("picked", "score", "candidates"):
                if key not in sample:
                    report.passed = False
                    report.failures.append(f"audit BCS sample missing {key!r}")

    return report
