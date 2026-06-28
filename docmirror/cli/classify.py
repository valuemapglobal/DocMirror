# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Click command group for intelligent document classification.

Exposes ``docmirror classify`` — a directory-oriented workflow that walks
files, samples or parses content, and sorts them into financial and general
document types using the plugin and evidence engines. Supports dry-run preview,
custom output directories, and report generation via ``classify_report``.

Usage::

    docmirror classify <directory>
    docmirror classify <directory> -o <output_dir>
    docmirror classify <directory> --dry-run
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


@click.command()
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--output-dir", "-o", type=click.Path(path_type=Path), default=None, help="Classification output directory (default: ./classified_output)"
)
@click.option(
    "--rules", "-r", type=click.Path(exists=True, path_type=Path), default=None, help="Classification rules file path (YAML format)"
)
@click.option("--dry-run", is_flag=True, default=False, help="Preview classification results, do not move files")
@click.option(
    "--report-format",
    type=click.Choice(["markdown", "json", "csv"]),
    default="markdown",
    help="Report format (default: markdown)",
)
def classify(source_dir, output_dir, rules, dry_run, report_format):
    """
    Intelligently classify financial files in a directory.

    Walks through all files in SOURCE_DIR, automatically parses content, and classifies them into corresponding directories.
    Leverages DocMirror plugin system and rule engine for accurate classification.

    \b
    Examples:
      # Basic usage
      docmirror classify /path/to/documents

      # Specify output directory
      docmirror classify /path/to/documents -o /path/to/output

      # Preview mode (no file moving)
      docmirror classify /path/to/documents --dry-run

      # Use custom rules
      docmirror classify /path/to/documents -r custom_rules.yaml

      # Generate JSON report
      docmirror classify /path/to/documents --report-format json
    """

    # Set output directory
    output_dir = output_dir or Path.cwd() / "classified_output"

    console.print("\n" + "=" * 80)
    console.print("[bold cyan]Smart File Classification System[/bold cyan]")
    console.print("=" * 80)

    console.print(f"\n[bold]Source directory:[/bold] {source_dir}")
    console.print(f"[bold]Output directory:[/bold] {output_dir}")
    console.print(f"[bold]Rules file:[/bold] {rules or 'default'}")
    console.print(f"[bold]Mode:[/bold] {'Preview (no file moving)' if dry_run else 'Active classification'}")
    console.print(f"[bold]Report format:[/bold] {report_format}\n")

    if dry_run:
        console.print("[yellow]⚠ Preview mode: files will not be moved[/yellow]\n")

    # Run classification
    try:
        from docmirror.cli.classify_engine import FileClassifier
        from docmirror.cli.classify_report import (
            generate_pending_report,
            generate_report,
            print_summary,
        )

        classifier = FileClassifier(rules_path=rules, output_dir=output_dir, dry_run=dry_run)

        # Execute classification
        results = asyncio.run(classifier.classify_directory(source_dir))

        # Print summary
        print_summary(results)

        # Generate report
        if results.total_files > 0:
            report_path = generate_report(results, output_dir, report_format)
            console.print(f"[bold green]✓[/bold green] Report: {report_path}")

            # If there are pending files, generate pending report
            if results.pending_count > 0:
                pending_path = generate_pending_report(results, output_dir)
                console.print(f"[bold yellow]⚠[/bold yellow] Pending report: {pending_path}")

        # Return status code
        if results.failed_count > 0:
            raise SystemExit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Classification interrupted by user[/yellow]")
        raise SystemExit(130)
    except Exception as e:
        console.print(f"\n[bold red]✖ Classification failed:[/bold red] {e}")
        logger.exception("Classification failed")
        raise SystemExit(1)
