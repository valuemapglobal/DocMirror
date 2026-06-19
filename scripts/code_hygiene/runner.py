# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Orchestrate all hygiene checks."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scripts.code_hygiene.allowlist import load_allowlist
from scripts.code_hygiene.checks import (
    check_commented_blocks,
    check_orphan_configs,
    check_orphan_modules,
    check_orphan_scripts,
    check_ruff_strict,
    check_vulture,
)
from scripts.code_hygiene.models import CheckResult, HygieneReport
from scripts.code_hygiene.report import print_console_summary, write_json_report, write_markdown_report

ALL_CHECKS: dict[str, Callable[..., CheckResult]] = {
    "ruff_strict": check_ruff_strict,
    "vulture": check_vulture,
    "orphan_modules": check_orphan_modules,
    "orphan_configs": check_orphan_configs,
    "orphan_scripts": check_orphan_scripts,
    "commented_blocks": check_commented_blocks,
}


def run_hygiene_audit(
    *,
    checks: tuple[str, ...] | None = None,
    allowlist_path: Path | None = None,
    min_vulture_confidence: int = 80,
    json_out: Path | None = None,
    markdown_out: Path | None = None,
    console: bool = True,
) -> HygieneReport:
    """Run hygiene audit and return aggregated report."""
    allowlist = load_allowlist(allowlist_path)
    names = checks or tuple(ALL_CHECKS.keys())
    report = HygieneReport()

    for name in names:
        fn = ALL_CHECKS.get(name)
        if fn is None:
            report.results.append(
                CheckResult(name=name, skipped=True, skip_reason=f"unknown check: {name}")
            )
            continue
        if name == "vulture":
            result = fn(allowlist, min_confidence=min_vulture_confidence)
        else:
            result = fn(allowlist)
        report.results.append(result)

    if json_out:
        write_json_report(report, json_out)
    if markdown_out:
        write_markdown_report(report, markdown_out)
    if console:
        print_console_summary(report)
    return report
