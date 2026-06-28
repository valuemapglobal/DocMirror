# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Classification report generator for the DocMirror CLI.

Builds aggregate statistics from a completed ``docmirror classify`` run and
writes human-readable or machine-readable summaries. Supports Markdown tables
for terminal review, JSON for downstream automation, and CSV for spreadsheet
import. Report sections typically include per-type counts, confidence
distribution, unmatched files, and institution breakdowns when available.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from docmirror.cli.classify_engine import ClassificationResults

logger = logging.getLogger(__name__)


def generate_report(results: ClassificationResults, output_dir: Path, format: str = "markdown") -> Path:
    """
    Generate classification report

    Args:
        results: Classification results
        output_dir: output directory
        format: report format (markdown, json, csv)

    Returns:
        Report file path
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if format == "markdown":
        report_path = output_dir / "classification_report.md"
        _generate_markdown_report(results, report_path)
    elif format == "json":
        report_path = output_dir / "classification_report.json"
        _generate_json_report(results, report_path)
    elif format == "csv":
        report_path = output_dir / "classification_report.csv"
        _generate_csv_report(results, report_path)
    else:
        raise ValueError(f"Unsupported report format: {format}")

    logger.info(f"[Report] Generated {format} report: {report_path}")
    return report_path


def generate_pending_report(results: ClassificationResults, output_dir: Path) -> Path:
    """
    Generate pending file report

    Args:
        results: Classification results
        output_dir: output directory

    Returns:
        Pending report file path
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "pending_review.json"

    pending_results = [r for r in results.results if r.is_pending]

    report_data = {
        "total_pending": len(pending_results),
        "files": [
            {
                "source_path": str(r.source_path),
                "target_path": str(r.target_path) if r.target_path else None,
                "category": r.category,
                "confidence": r.confidence,
                "matches": [
                    {
                        "source": m.source,
                        "category_id": m.category_id,
                        "category_name": m.category_name,
                        "confidence": m.confidence,
                        "details": m.details,
                    }
                    for m in r.matches
                ],
            }
            for r in pending_results
        ],
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    logger.info(f"[Report] Generated pending review report: {report_path}")
    return report_path


def _generate_markdown_report(results: ClassificationResults, report_path: Path) -> None:
    """Generate Markdown format report."""

    # Compute statistics
    category_stats = results.get_results_by_category()

    # Generate report content
    report = f"""# Intelligent File Classification Report

## Classification Overview

- **Total files**: {results.total_files}
- **Successfully classified**: {results.success_count}
- **Failed**: {results.failed_count}
- **Unmatched files**: {results.unmatched_count}
- **Pending files**: {results.pending_count}
- **Average confidence**: {results.avg_confidence:.2%}
- **Processing time**: {_format_duration(results.start_time, results.end_time)}

## By Category

| Category | Files | Percentage |
|------|--------|------|
"""

    for category, cat_results in sorted(category_stats.items()):
        count = len(cat_results)
        percentage = count / results.total_files * 100 if results.total_files > 0 else 0
        report += f"| {category} | {count} | {percentage:.1f}% |\n"

    report += """
## Successfully Classified Files

| # | File | Category | Target Path | Confidence |
|------|--------|------|----------|--------|
"""

    for i, result in enumerate([r for r in results.results if r.success], 1):
        report += f"| {i} | {result.source_path.name} | {result.category or 'N/A'} | {result.target_path or 'N/A'} | {result.confidence:.2%} |\n"

    # Pending files
    pending_results = [r for r in results.results if r.is_pending]
    if pending_results:
        report += """
## Pending Files (Manual Review Required)

| # | File | Recommended Category | Confidence | Matches |
|------|--------|----------|--------|--------|
"""

        for i, result in enumerate(pending_results, 1):
            report += f"| {i} | {result.source_path.name} | {result.category or 'N/A'} | {result.confidence:.2%} | {len(result.matches)} |\n"

    # Error files
    if results.errors:
        report += """
## Error Files

| # | File | Error Message |
|------|--------|----------|
"""

        for i, (file_path, error) in enumerate(results.errors, 1):
            report += f"| {i} | {file_path.name} | {error} |\n"

    # Unmatched files
    unmatched_results = [r for r in results.results if not r.success and not r.error]
    if unmatched_results:
        report += """
## Unmatched Files

| # | File | Path |
|------|--------|------|
"""

        for i, result in enumerate(unmatched_results, 1):
            report += f"| {i} | {result.source_path.name} | {result.source_path} |\n"

    # Write to file
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)


def _generate_json_report(results: ClassificationResults, report_path: Path) -> None:
    """Generate JSON format report."""

    report_data = {
        "summary": {
            "total_files": results.total_files,
            "success_count": results.success_count,
            "failed_count": results.failed_count,
            "unmatched_count": results.unmatched_count,
            "pending_count": results.pending_count,
            "avg_confidence": results.avg_confidence,
            "start_time": results.start_time.isoformat() if results.start_time else None,
            "end_time": results.end_time.isoformat() if results.end_time else None,
        },
        "category_stats": {},
        "files": [],
        "errors": [],
        "unmatched": [],
    }

    # Category statistics
    category_stats = results.get_results_by_category()
    for category, cat_results in category_stats.items():
        report_data["category_stats"][category] = {
            "count": len(cat_results),
            "files": [str(r.source_path.name) for r in cat_results],
        }

    # File details
    for result in results.results:
        if result.success:
            report_data["files"].append(
                {
                    "source_path": str(result.source_path),
                    "target_path": str(result.target_path) if result.target_path else None,
                    "category": result.category,
                    "confidence": result.confidence,
                    "matches": [
                        {
                            "source": m.source,
                            "category_id": m.category_id,
                            "category_name": m.category_name,
                            "confidence": m.confidence,
                        }
                        for m in result.matches
                    ],
                }
            )
        elif not result.error:
            report_data["unmatched"].append(str(result.source_path))

    # Error information
    for file_path, error in results.errors:
        report_data["errors"].append({"file_path": str(file_path), "error": error})

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)


def _generate_csv_report(results: ClassificationResults, report_path: Path) -> None:
    """Generate CSV format report."""

    with open(report_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)

        # Write header
        writer.writerow(["#", "File", "Source Path", "Target Path", "Category", "Confidence", "Status", "Error", "Matches"])

        # Write data
        for i, result in enumerate(results.results, 1):
            status = "Success" if result.success else ("Failed" if result.error else "Unmatched")
            writer.writerow(
                [
                    i,
                    result.source_path.name,
                    str(result.source_path),
                    str(result.target_path) if result.target_path else "",
                    result.category or "",
                    f"{result.confidence:.2%}",
                    status,
                    result.error or "",
                    len(result.matches),
                ]
            )

        # Write error records
        for i, (file_path, error) in enumerate(results.errors, len(results.results) + 1):
            writer.writerow([i, file_path.name, str(file_path), "", "", "", "Error", error, 0])


def _format_duration(start_time, end_time) -> str:
    """Format a time duration."""
    if not start_time or not end_time:
        return "N/A"

    duration = end_time - start_time
    total_seconds = int(duration.total_seconds())

    if total_seconds < 60:
        return f"{total_seconds} sec"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes} min {seconds} sec"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours} hr {minutes} min"


def print_summary(results: ClassificationResults) -> None:
    """
    Print classification summary to console.

    Args:
        results: Classification results
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n" + "=" * 80)
    console.print("[bold cyan]File Classification Complete[/bold cyan]")
    console.print("=" * 80)

    # Summary statistics
    console.print(f"\n[bold]Total files:[/bold] {results.total_files}")
    console.print(f"[bold green]Successfully classified:[/bold green] {results.success_count}")
    console.print(f"[bold red]Failed:[/bold red] {results.failed_count}")
    console.print(f"[bold yellow]Unmatched files:[/bold yellow] {results.unmatched_count}")
    console.print(f"[bold magenta]Pending files:[/bold magenta] {results.pending_count}")
    console.print(f"[bold]Average confidence:[/bold] {results.avg_confidence:.2%}")
    console.print(f"[bold]Processing time:[/bold] {_format_duration(results.start_time, results.end_time)}")

    # Category statistics
    category_stats = results.get_results_by_category()
    if category_stats:
        console.print("\n[bold]By Category:[/bold]")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Category", style="cyan")
        table.add_column("Files", justify="right")
        table.add_column("Percentage", justify="right")

        for category, cat_results in sorted(category_stats.items()):
            count = len(cat_results)
            percentage = count / results.total_files * 100 if results.total_files > 0 else 0
            table.add_row(category, str(count), f"{percentage:.1f}%")

        console.print(table)

    # Pending files prompt
    if results.pending_count > 0:
        console.print(f"\n[yellow]⚠ {results.pending_count} file(s) require manual review. See pending_review.json[/yellow]")

    # Error notice
    if results.failed_count > 0:
        console.print(f"\n[red]✖ {results.failed_count} file(s) failed classification. See report for details.[/red]")

    console.print()
