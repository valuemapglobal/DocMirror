# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Console and file reports for release gate."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.release_gate.models import GateReport


def write_json_report(report: GateReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def format_markdown(report: GateReport) -> str:
    lines = [
        "# DocMirror Release Gate",
        "",
        f"- **Profile**: `{report.profile}`",
        f"- **Passed**: {report.passed}",
        f"- **Duration**: {report.total_ms} ms",
        "",
    ]
    if report.failed_steps:
        lines.append("## Failed steps")
        lines.append("")
        for step in report.failed_steps:
            lines.append(f"- **{step.step_id}** — {step.title}")
            if step.detail:
                lines.append(f"  - {step.detail}")
        lines.append("")

    lines.append("## Steps")
    lines.append("")
    lines.append("| Phase | Step | Status | ms |")
    lines.append("|-------|------|--------|-----|")
    for r in report.results:
        status = "SKIP" if r.skipped else ("PASS" if r.passed else "FAIL")
        lines.append(f"| {r.phase} | {r.step_id} | {status} | {r.duration_ms} |")
    lines.append("")
    return "\n".join(lines)


def write_markdown_report(report: GateReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_markdown(report), encoding="utf-8")


def print_console_summary(report: GateReport) -> None:
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"DocMirror Release Gate — profile={report.profile}")
        table.add_column("Phase")
        table.add_column("Step")
        table.add_column("Status")
        table.add_column("ms", justify="right")
        for r in report.results:
            if r.skipped:
                status = "[dim]SKIP[/dim]"
            elif r.passed:
                status = "[green]PASS[/green]"
            else:
                status = "[red]FAIL[/red]"
            table.add_row(r.phase, r.step_id, status, str(r.duration_ms))
        console.print(table)
        console.print(f"\n[bold]Total[/bold]: {report.total_ms} ms")
        if report.passed:
            console.print("[green]Release gate PASSED[/green]")
        else:
            console.print(f"[red]Release gate FAILED[/red] — {len(report.failed_steps)} step(s)")
            for step in report.failed_steps:
                console.print(f"  [red]✗[/red] {step.step_id}: {step.detail or step.log_tail[:200]}")
    except ImportError:
        print(f"Release gate profile={report.profile} passed={report.passed} ms={report.total_ms}")
        for r in report.results:
            mark = "SKIP" if r.skipped else ("PASS" if r.passed else "FAIL")
            print(f"  [{mark}] {r.phase}/{r.step_id} ({r.duration_ms}ms)")
