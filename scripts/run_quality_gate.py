#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""DocMirror Quality Gate — unified code-quality scan.

Single entry point for hygiene audit and pre-production release checks.

Profiles::

    hygiene   Code hygiene only (dead code, orphans, ruff strict) — CI hygiene job
    quick     ~1–3 min: ruff + fast hygiene subset
    standard  ~8–20 min: CI parity (contracts + architecture + unit tests)
    full      ~30+ min: standard + tier regression + coverage

Examples::

    python scripts/run_quality_gate.py --profile hygiene --strict
    python scripts/run_quality_gate.py --profile hygiene --only ruff_strict,vulture
    python scripts/run_quality_gate.py                        # standard (default)
    python scripts/run_quality_gate.py --profile quick --stop-on-fail
    python scripts/run_quality_gate.py --list-steps
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.code_hygiene.runner import ALL_CHECKS, run_hygiene_audit  # noqa: E402
from scripts.release_gate.config import (  # noqa: E402
    PROFILE_DESCRIPTIONS,
    steps_for_profile,
)
from scripts.release_gate.config import (
    PROFILES as GATE_PROFILES,
)
from scripts.release_gate.models import StepResult  # noqa: E402
from scripts.release_gate.progress import QualityGateProgress  # noqa: E402
from scripts.release_gate.report import (  # noqa: E402
    print_console_summary as print_gate_summary,
)
from scripts.release_gate.report import (
    write_json_report as write_gate_json,
)
from scripts.release_gate.report import (
    write_markdown_report as write_gate_markdown,
)
from scripts.release_gate.runner import run_release_gate  # noqa: E402

HYGIENE_PROFILE = "hygiene"
ALL_PROFILES = (HYGIENE_PROFILE,) + GATE_PROFILES


def _resolve_hygiene_checks(args: argparse.Namespace) -> tuple[str, ...] | None:
    return tuple(c.strip() for c in args.only.split(",") if c.strip()) or None


def _check_to_step_result(name: str, result) -> StepResult:
    if result.skipped:
        return StepResult(
            step_id=name,
            title=name,
            phase="hygiene",
            passed=True,
            skipped=True,
            duration_ms=result.duration_ms,
            detail=result.skip_reason,
        )
    passed = result.error_count == 0
    detail = f"errors={result.error_count} warnings={result.warning_count}"
    return StepResult(
        step_id=name,
        title=name,
        phase="hygiene",
        passed=passed,
        duration_ms=result.duration_ms,
        detail=detail if not passed else "",
    )


def _run_hygiene_profile(args: argparse.Namespace) -> int:
    checks = _resolve_hygiene_checks(args)
    check_names = list(checks or ALL_CHECKS.keys())
    show_progress = not args.quiet

    with QualityGateProgress.for_hygiene_checks(check_names, enabled=show_progress) as progress:
        report = run_hygiene_audit(
            checks=checks,
            allowlist_path=args.allowlist,
            min_vulture_confidence=args.min_vulture_confidence,
            json_out=args.json_out,
            markdown_out=args.markdown_out,
            console=False,
            on_check_start=(lambda i, _n: progress.start(i)) if show_progress else None,
            on_check_done=(lambda i, r: progress.finish(i, _check_to_step_result(r.name, r)))
            if show_progress
            else None,
        )

    if not args.quiet:
        from scripts.code_hygiene.report import print_console_summary

        print_console_summary(report)

    if args.strict and report.total_errors > 0:
        return 1
    if args.fail_on_warnings and (report.total_errors > 0 or report.total_warnings > 0):
        return 1
    return 0


def _run_gate_profile(args: argparse.Namespace) -> int:
    steps = steps_for_profile(args.profile)
    show_progress = not args.quiet
    with QualityGateProgress.for_gate_steps(args.profile, steps, enabled=show_progress) as progress:
        report = run_release_gate(
            args.profile,
            stop_on_fail=args.stop_on_fail,
            progress=progress if show_progress else None,
        )
    if args.json_out:
        write_gate_json(report, args.json_out)
    if args.markdown_out:
        write_gate_markdown(report, args.markdown_out)
    if not args.quiet:
        print_gate_summary(report)
    return 0 if report.passed else 1


def _list_steps() -> int:
    print(f"\n[{HYGIENE_PROFILE}] Code hygiene audit only")
    print(f"  checks: {', '.join(ALL_CHECKS)}")
    for name in GATE_PROFILES:
        print(f"\n[{name}] {PROFILE_DESCRIPTIONS[name]}")
        for step in steps_for_profile(name):
            opt = " (optional)" if step.optional else ""
            print(f"  {step.phase:12} {step.step_id}{opt}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DocMirror quality gate — hygiene audit and pre-production checks",
    )
    parser.add_argument(
        "--profile",
        choices=ALL_PROFILES,
        default="standard",
        help="Scan profile (default: standard)",
    )
    parser.add_argument("--json", type=Path, dest="json_out", help="Write JSON report")
    parser.add_argument("--markdown", type=Path, dest="markdown_out", help="Write Markdown report")
    parser.add_argument("--quiet", action="store_true", help="Suppress live progress and final summary")

    # Hygiene-only options (--profile hygiene)
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help=f"Hygiene: comma-separated checks (default: all). Available: {','.join(ALL_CHECKS)}",
    )
    parser.add_argument("--allowlist", type=Path, help="Hygiene: override allowlist yaml path")
    parser.add_argument("--min-vulture-confidence", type=int, default=80)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Hygiene: exit 1 on error-level findings",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Hygiene: exit 1 on warnings too",
    )

    # Gate options (quick / standard / full)
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Gate: stop after first failing step",
    )
    parser.add_argument(
        "--list-steps",
        action="store_true",
        help="List steps per profile and exit",
    )
    args = parser.parse_args()

    if args.list_steps:
        return _list_steps()

    if args.profile == HYGIENE_PROFILE:
        return _run_hygiene_profile(args)
    return _run_gate_profile(args)


if __name__ == "__main__":
    raise SystemExit(main())
