# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PDF/UA accessible document CLI command (GA1.0-ODL-02 Phase 3).

Registered as ``docmirror pdfua INPUT OUTPUT [--language LANG] [--version UA-1|UA-2]``.
Converts any document supported by DocMirror into a tagged, accessible PDF.

Requires: ``pip install docmirror[pdfua]`` (adds PyMuPDF >= 1.23.0).
"""

from __future__ import annotations

from pathlib import Path

import click


@click.command("pdfua")
@click.argument("input", type=click.Path(exists=True, readable=True))
@click.argument("output", type=click.Path(writable=True), default=None, required=False)
@click.option(
    "--language",
    default="en-US",
    show_default=True,
    help="Document language code (BCP 47, e.g. zh-CN, de-DE).",
)
@click.option(
    "--version",
    "schema_version",
    type=click.Choice(["UA-1", "UA-2"]),
    default="UA-1",
    show_default=True,
    help="PDF/UA specification version target.",
)
@click.option(
    "--dmir",
    "dmir_path",
    type=click.Path(exists=True, readable=True),
    default=None,
    help="Skip parsing; use existing DMIR JSON file instead of --input document.",
)
def pdfua(input: str, output: str | None, language: str, schema_version: str, dmir_path: str | None) -> None:
    """Convert INPUT document to a tagged, accessible PDF/UA document.

    Parses INPUT with DocMirror, then generates a PDF/UA-1 (or PDF/UA-2) compliant
    tagged PDF. If --dmir is provided, skips parsing and reads the DMIR JSON directly.

    Examples:

        docmirror pdfua report.pdf accessible_report.pdf

        docmirror pdfua invoice.pdf --language zh-CN --version UA-1

        docmirror pdfua --dmir report.dmir.json accessible_report.pdf
    """
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn

    console = Console()
    input_path = Path(input)

    try:
        from docmirror.output.exporters.pdfua import export_pdfua
        from docmirror.output.exporters.pdfua_types import PdfUaVersion
    except ImportError:
        console.print(
            "[red]PyMuPDF >= 1.23.0 is required for PDF/UA export.[/red]\n"
            "Install with: [bold]pip install 'docmirror[pdfua]'[/bold]"
        )
        raise SystemExit(1)

    # Resolve output path
    output_path: Path
    if output:
        output_path = Path(output)
    else:
        output_path = input_path.with_suffix(".accessible.pdf")

    # Determine schema version
    ver = PdfUaVersion.PDFUA_1 if schema_version == "UA-1" else PdfUaVersion.PDFUA_2

    # Get DMIR — either from file or by parsing the input document
    if dmir_path:
        import json

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Loading DMIR...", total=None)
            with open(dmir_path) as f:
                dmir = json.load(f)
    else:
        # Parse the input document using DocMirror's engine
        import json as _json

        from docmirror.input.entry.factory import PerceiveOptions, perceive_document

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description=f"Parsing [bold]{input_path.name}[/bold]...", total=None)
            result = perceive_document(input_path, PerceiveOptions())

        from docmirror.output.dmir import serialize_dmir

        dmir = serialize_dmir(result)

    # Export to PDF/UA
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(description="Generating accessible PDF...", total=None)
        export_result = export_pdfua(
            dmir,
            output_path=output_path,
            title=input_path.stem,
            language=language,
            schema_version=ver,
        )

    if export_result.success:
        console.print(f"[green]Accessible PDF written to [bold]{output_path.resolve()}[/bold][/green]")
        console.print(f"  Pages: {export_result.page_count}")
        console.print(f"  Language: {language}")
        console.print(f"  PDF/UA version: {ver.value}")
        if export_result.warnings:
            console.print("[yellow]Warnings:[/yellow]")
            for w in export_result.warnings:
                console.print(f"  [yellow]![/yellow] {w}")
    else:
        console.print(f"[red]Export failed:[/red]")
        for e in export_result.errors:
            console.print(f"  [red]![/red] {e}")
        raise SystemExit(1)
