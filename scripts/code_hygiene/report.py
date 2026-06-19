# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Render hygiene audit reports."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from scripts.code_hygiene.models import HygieneReport


def write_json_report(report: HygieneReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def format_markdown(report: HygieneReport) -> str:
    lines: list[str] = [
        "# DocMirror Code Hygiene Audit",
        "",
        "## Summary",
        "",
        f"- **Errors**: {report.total_errors}",
        f"- **Warnings**: {report.total_warnings}",
        f"- **Total findings**: {len(report.findings)}",
        "",
    ]

    by_category: dict[str, list] = defaultdict(list)
    for finding in report.findings:
        by_category[finding.category.value].append(finding)

    for category in sorted(by_category):
        items = by_category[category]
        lines.append(f"## {category} ({len(items)})")
        lines.append("")
        for f in items[:50]:
            sev = f.severity.value.upper()
            loc = f" `{f.location}`" if f.location else ""
            lines.append(f"- **[{sev}]** {f.message}{loc}")
            if f.hint:
                lines.append(f"  - _Hint:_ {f.hint}")
        if len(items) > 50:
            lines.append(f"- _… and {len(items) - 50} more_")
        lines.append("")

    lines.append("## Checks")
    lines.append("")
    for result in report.results:
        status = "skipped" if result.skipped else "ok"
        lines.append(
            f"- **{result.name}** ({status}, {result.duration_ms}ms) — "
            f"errors={result.error_count}, warnings={result.warning_count}"
        )
        if result.skip_reason:
            lines.append(f"  - skip: {result.skip_reason}")
    lines.append("")
    return "\n".join(lines)


def write_markdown_report(report: HygieneReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_markdown(report), encoding="utf-8")


def print_console_summary(report: HygieneReport) -> None:
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="DocMirror Hygiene Audit")
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Errors", justify="right")
        table.add_column("Warnings", justify="right")
        table.add_column("ms", justify="right")
        for r in report.results:
            status = "SKIP" if r.skipped else "OK"
            table.add_row(r.name, status, str(r.error_count), str(r.warning_count), str(r.duration_ms))
        console.print(table)
        console.print(
            f"\n[bold]Total[/bold]: errors={report.total_errors} warnings={report.total_warnings} "
            f"findings={len(report.findings)}"
        )
        if report.total_errors:
            console.print("[red]Hygiene audit failed (errors present).[/red]")
        elif report.total_warnings:
            console.print("[yellow]Hygiene audit passed with warnings.[/yellow]")
        else:
            console.print("[green]Hygiene audit clean.[/green]")
    except ImportError:
        print(f"Hygiene: errors={report.total_errors} warnings={report.total_warnings}")
        for r in report.results:
            print(f"  {r.name}: errors={r.error_count} warnings={r.warning_count} skipped={r.skipped}")
