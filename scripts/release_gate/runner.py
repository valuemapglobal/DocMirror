# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run release-gate steps for a profile."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.code_hygiene.runner import ALL_CHECKS, run_hygiene_audit
from scripts.release_gate.config import GateStepDef, steps_for_profile
from scripts.release_gate.models import GateReport, StepResult

if TYPE_CHECKING:
    from scripts.release_gate.progress import QualityGateProgress

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


def _hygiene_check_names(step: GateStepDef) -> tuple[str, ...]:
    return step.hygiene_checks or tuple(ALL_CHECKS.keys())


def _run_hygiene(step: GateStepDef, *, progress: QualityGateProgress | None = None) -> StepResult:
    t0 = time.perf_counter()
    check_names = _hygiene_check_names(step)

    def _on_check_start(index: int, _name: str) -> None:
        if progress is None:
            return
        if index == 0:
            progress.set_substeps(list(check_names))
        else:
            progress.start_substep(index)

    def _on_check_done(index: int, result) -> None:
        if progress is None:
            return
        passed = result.error_count == 0 and not result.skipped
        detail = ""
        if result.skipped:
            detail = result.skip_reason
        elif result.error_count:
            detail = f"errors={result.error_count}"
        progress.finish_substep(
            index,
            passed=passed or result.skipped,
            duration_ms=result.duration_ms,
            detail=detail,
        )

    report = run_hygiene_audit(
        checks=step.hygiene_checks,
        console=False,
        on_check_start=_on_check_start if progress else None,
        on_check_done=_on_check_done if progress else None,
    )
    ms = int((time.perf_counter() - t0) * 1000)
    passed = True if not step.hygiene_strict else report.total_errors == 0
    if step.hygiene_fail_on_warnings and report.total_warnings > 0:
        passed = False
    detail = f"errors={report.total_errors} warnings={report.total_warnings}"
    if not passed:
        failed = [r.name for r in report.results if r.error_count or r.warning_count]
        detail += f"; failed: {', '.join(failed)}"
    return StepResult(
        step_id=step.step_id,
        title=step.title,
        phase=step.phase,
        passed=passed,
        duration_ms=ms,
        detail=detail,
    )


def _run_core_imports(step: GateStepDef) -> StepResult:
    from scripts.validate.audit_core_imports import audit_failures, run_audit

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


def _run_step(
    step: GateStepDef,
    *,
    cwd: Path,
    progress: QualityGateProgress | None = None,
) -> StepResult:
    if step.kind == "shell":
        return _run_shell(step, cwd=cwd)
    if step.kind == "hygiene":
        return _run_hygiene(step, progress=progress)
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
    progress: QualityGateProgress | None = None,
) -> GateReport:
    """Execute all steps for *profile* and return aggregated report."""
    cwd = cwd or ROOT
    steps = steps_for_profile(profile)
    report = GateReport(profile=profile)
    for index, step in enumerate(steps):
        if progress is not None:
            progress.start(index)
        result = _run_step(step, cwd=cwd, progress=progress)
        report.results.append(result)
        if progress is not None:
            progress.finish(index, result)
        if stop_on_fail and not result.passed and not result.skipped:
            if progress is not None:
                progress.cancel_remaining(index + 1)
            break
    return report
