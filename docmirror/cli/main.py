# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror CLI main entry point and Click application root.

Registers top-level command groups (parse, classify, plugins, benchmark) and
delegates to ``docmirror.__main__`` for single-file and batch parsing with
Rich progress output. This module is the console-script target for the
``docmirror`` command; library callers should use ``perceive_document()`` instead.

Usage::

    docmirror [file]                    # Parse one file or batch directory
    docmirror classify <dir>            # Classify documents by type
    docmirror plugins list              # List installed plugins
    docmirror plugins community         # Show community 6+1 plugin set
    docmirror plugins enable <name>     # Enable a plugin
    docmirror plugins license show      # Display license status
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import click

from docmirror.cli.benchmark import benchmark
from docmirror.cli.classify import classify
from docmirror.cli.plugins import plugins


@click.group()
@click.version_option(version="0.4.0", prog_name="DocMirror")
def main():
    """DocMirror - Universal Document Parsing Engine.

    Community structured output: 6 premium domains + generic.community_plugin fallback.
    """
    pass


# Register subcommands
main.add_command(plugins)
main.add_command(classify)
main.add_command(benchmark)



@main.command()
@click.argument("file", required=True)
@click.option("--output-dir", "-o", default="output", show_default=True, help="Output directory")
@click.option("--pages", default=None, help="Page ranges, 1-based: 1-3,8,10-")
@click.option("--max-pages", type=int, default=None, help="Maximum pages after applying --pages")
@click.option("--workers", "-j", default=None, help="Total worker budget for this command (int or auto)")
@click.option(
    "--mode",
    "-m",
    default="auto",
    type=click.Choice(["auto", "fast", "balanced", "accurate", "forensic"]),
    show_default=True,
    help="Parse mode",
)
@click.option("--format", "-f", "formats", default="json", show_default=True, help="Output formats: json,csv,markdown,chunks,html,parquet,all")
@click.option("--doc-type-hint", default=None, help="Manual document type hint, optionally type:force")
@click.option("--skip-cache", is_flag=True, help="Skip cache")
@click.option("--use-cache/--no-use-cache", default=True, help="Enable or disable cache usage")
@click.option("--split-layers", is_flag=True, help="Export L1/L2/L3 as separate files")
@click.option("--no-stage-output", is_flag=True, help="Disable 3-stage output")
@click.option("--export-csv", is_flag=True, help="Export CSV")
@click.option("--export-chunks", is_flag=True, help="Export RAG chunks")
@click.option("--include-text", is_flag=True, help="Include full text in output")
@click.option(
    "--mirror-level",
    default="standard",
    type=click.Choice(["standard", "forensic"]),
    help="Mirror output level: standard (physical+logical), forensic (physical audit, no logical_tables)",
)
@click.option("--include-geometry", is_flag=True, help="Include table/cell geometry by using forensic mirror output")
@click.option("--debug-artifact", is_flag=True, help="Write debug artifact")
@click.option("--slm", is_flag=True, help="Enable SLM extraction")
def parse(file, output_dir, pages, max_pages, workers, mode, formats, doc_type_hint, skip_cache, use_cache, split_layers, no_stage_output, export_csv, export_chunks, include_text, mirror_level, include_geometry, debug_artifact, slm):
    """Parse a document and save results."""
    if slm:
        os.environ["DOCMIRROR_ENABLE_SLM"] = "1"
    if include_geometry and mirror_level != "forensic":
        mirror_level = "forensic"

    resolved_skip_cache = skip_cache or not use_cache

    from docmirror.__main__ import parse_document

    asyncio.run(parse_document(
        str(Path(file).resolve()),
        "json",
        Path(output_dir),
        no_save=False,
        skip_cache=resolved_skip_cache,
        include_text=include_text,
        split_layers=split_layers,
        stage_output=not no_stage_output,
        debug_artifact=debug_artifact,
        export_chunks=export_chunks,
        export_csv=export_csv,
        export_parquet=False,
        mirror_level=mirror_level,
        pages=pages,
        max_pages=max_pages,
        workers=workers,
        mode=mode,
        formats=formats,
        doc_type_hint=doc_type_hint,
        slm=slm,
    ))


if __name__ == "__main__":
    main()
