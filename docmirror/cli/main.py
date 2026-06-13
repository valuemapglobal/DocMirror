# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror CLI - Main Entry Point
=================================

Unified command-line interface for DocMirror.

Usage:
    docmirror [file]                    # Parse document
    docmirror classify <dir>            # Classify documents
    docmirror plugins list              # List plugins
    docmirror plugins enable <name>     # Enable plugin
    docmirror plugins license show      # Show license
"""

from __future__ import annotations

import click

from docmirror.cli.benchmark import benchmark
from docmirror.cli.classify import classify
from docmirror.cli.plugins import plugins


@click.group()
@click.version_option(version="0.4.0", prog_name="DocMirror")
def main():
    """DocMirror - Universal Document Parsing Engine"""
    pass


# Register subcommands
main.add_command(plugins)
main.add_command(classify)
main.add_command(benchmark)



@main.command()
@click.argument("file", required=True)
@click.option("--output-dir", "-o", default="output", show_default=True, help="Output directory")
@click.option("--skip-cache", is_flag=True, help="Skip cache")
@click.option("--split-layers", is_flag=True, help="Export L1/L2/L3 as separate files")
@click.option("--no-stage-output", is_flag=True, help="Disable 3-stage output")
@click.option("--export-csv", is_flag=True, help="Export CSV")
@click.option("--export-chunks", is_flag=True, help="Export RAG chunks")
@click.option("--include-text", is_flag=True, help="Include full text in output")
@click.option(
    "--mirror-level",
    default="standard",
    type=click.Choice(["standard", "slim", "forensic"]),
    help="Mirror output: standard (physical+logical), slim (logical only), forensic (physical only)",
)
@click.option("--debug-artifact", is_flag=True, help="Write debug artifact")
@click.option("--slm", is_flag=True, help="Enable SLM extraction")
def parse(file, output_dir, skip_cache, split_layers, no_stage_output, export_csv, export_chunks, include_text, mirror_level, debug_artifact, slm):
    """Parse a document and save results."""
    import asyncio
    import os
    from pathlib import Path

    if slm:
        os.environ["DOCMIRROR_ENABLE_SLM"] = "1"

    from docmirror.__main__ import parse_document

    asyncio.run(parse_document(
        str(Path(file).resolve()),
        "json",
        Path(output_dir),
        no_save=False,
        skip_cache=skip_cache,
        include_text=include_text,
        split_layers=split_layers,
        stage_output=not no_stage_output,
        debug_artifact=debug_artifact,
        export_chunks=export_chunks,
        export_csv=export_csv,
        export_parquet=False,
        mirror_level=mirror_level,
    ))


if __name__ == "__main__":
    main()
