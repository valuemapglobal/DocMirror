# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run release-gate steps for a profile."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from scripts.code_hygiene.runner import run_hygiene_audit
from scripts.release_gate.config import GateStepDef, steps_for_profile
from scripts.release_gate.models import GateReport, StepResult

ROOT = Path(__file__).resolve().parents[2]
_LOG_TAIL = 1200


def _tail(text: str, limit: int = _LOG_TAIL) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return "…\n" + text[-limit:]


def _run_shell(step: GateStepDef, *, cwd: Path) -> StepResult:
    t0 = time.perf_counter()
    argv = list(step.argv)
    if step.optional and argv and shutil.which(argv[0]) is None:
        return StepResult(
            step_id=step.step_id,
            title=step.title,
            phase=step.phase,
            passed=True,
            skipped=True,
            skip_reason=f"{argv[0]} not installed",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    ms = int((time.perf_counter() - t0) * 1000)
    combined = (proc.stdout or "") + (proc.stderr or "")
    return StepResult(
        step_id=step.step_id,
        title=step.title,
        phase=step.phase,
        passed=proc.returncode == 0,
        duration_ms=ms,
        exit_code=proc.returncode,
        detail=f"exit {proc.returncode}" if proc.returncode else "",
        log_tail=_tail(combined),
    )


def _run_hygiene(step: GateStepDef) -> StepResult:
    t0 = time.perf_counter()
    report = run_hygiene_audit(checks=step.hygiene_checks, console=False)
    ms = int((time.perf_counter() - t0) * 1000)
    passed = report.total_errors == 0
    if step.hygiene_fail_on_warnings and report.total_warnings > 0:
        passed = False
    detail = f"errors={report.total_errors} warnings={report.total_warnings}"
    if not passed:
        failed = [r.name for r in report.results if r.error_count or r.warning_count]
        detail += f"; failed checkers: {', '.join(failed)}"
    return StepResult(
        step_id=step.step_id,
        title=step.title,
        phase=step.phase,
        passed=passed,
        duration_ms=ms,
        detail=detail,
    )


def _run_core_imports(step: GateStepDef) -> StepResult:
    from scripts.audit_core_imports import audit_failures, run_audit

    t0 = time.perf_counter()
    data = run_audit()
    failures = audit_failures(data)
    ms = int((time.perf_counter() - t0) * 1000)
    passed = not failures
    return StepResult(
        step_id=step.step_id,
        title=step.title,
        phase=step.phase,
        passed=passed,
        duration_ms=ms,
        detail="; ".join(failures[:5]) if failures else "ok",
        log_tail=_tail("\n".join(failures)),
    )


def _run_step(step: GateStepDef, *, cwd: Path) -> StepResult:
    if step.kind == "shell":
        return _run_shell(step, cwd=cwd)
    if step.kind == "hygiene":
        return _run_hygiene(step)
    if step.kind == "core_imports":
        return _run_core_imports(step)
    return StepResult(
        step_id=step.step_id,
        title=step.title,
        phase=step.phase,
        passed=False,
        detail=f"unknown step kind: {step.kind}",
    )


def run_release_gate(
    profile: str,
    *,
    cwd: Path | None = None,
    stop_on_fail: bool = False,
) -> GateReport:
    """Execute all steps for *profile* and return aggregated report."""
    cwd = cwd or ROOT
    report = GateReport(profile=profile)
    for step in steps_for_profile(profile):
        result = _run_step(step, cwd=cwd)
        report.results.append(result)
        if stop_on_fail and not result.passed and not result.skipped:
            break
    return report
