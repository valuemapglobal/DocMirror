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
from dotenv import load_dotenv

import click

from docmirror.cli.benchmark import benchmark
from docmirror.cli.classify import classify
from docmirror.cli.plugins import plugins

# Load .env from project root
_env_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_env_root / '.env', override=False)

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
@click.option("--output-dir", "-o", default=lambda: os.environ.get("DOCMIRROR_TASK_OUTPUT_DIR", "output"), show_default=True, help="Output directory (env: DOCMIRROR_TASK_OUTPUT_DIR or default 'output')")
@click.option("--no-save", is_flag=True, help="Do not save result to disk")
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
@click.option(
    "--ocr",
    default="auto",
    type=click.Choice(["auto", "force", "off", "fallback"]),
    show_default=True,
    help="OCR policy",
)
@click.option(
    "--format",
    "-f",
    "formats",
    default="json",
    show_default=True,
    help="Output formats: json,csv,markdown,chunks,html,parquet,all",
)
@click.option(
    "--editions",
    default="mirror,community",
    show_default=True,
    help="Output editions: mirror,community,enterprise,finance,all",
)
@click.option("--doc-type", default=None, help="Manual document type")
@click.option(
    "--doc-type-policy",
    default="prefer",
    type=click.Choice(["prefer", "force"]),
    show_default=True,
    help="How strongly to apply --doc-type",
)
@click.option(
    "--cache-policy",
    default="read-write",
    type=click.Choice(["read-write", "read-only", "refresh", "off"]),
    show_default=True,
    help="Cache policy",
)
@click.option("--split-layers", is_flag=True, help="Export L1/L2/L3 as separate files")
@click.option("--include-text", is_flag=True, help="Include full text in output")
@click.option(
    "--mirror-level",
    default=None,
    type=click.Choice(["standard", "forensic"]),
    help="Mirror output level: standard/forensic",
)
@click.option(
    "--geometry",
    default=None,
    type=click.Choice(["none", "page", "block", "token", "full"]),
    help="Geometry output level",
)
@click.option("--debug-artifact", is_flag=True, help="Write debug artifact")
@click.option("--recursive", is_flag=True, help="Recursively parse directory/glob inputs")
@click.option("--exclude", multiple=True, metavar="SUBSTR", help="Skip files whose path contains SUBSTR")
@click.option("--include-ext", default=None, help="Comma-separated extensions to include in batch mode")
@click.option(
    "--log-level",
    default="info",
    type=click.Choice(["debug", "info", "warning", "error"]),
    show_default=True,
    help="Logging level",
)
@click.option("--overwrite", is_flag=True, help="Allow overwriting an explicit --run-id output directory")
@click.option("--run-id", default=None, help="Explicit run/task id for output directory")
@click.option("--slm", is_flag=True, help="Enable SLM extraction")
def parse(
    file,
    output_dir,
    no_save,
    pages,
    max_pages,
    workers,
    mode,
    ocr,
    formats,
    editions,
    doc_type,
    doc_type_policy,
    cache_policy,
    split_layers,
    include_text,
    mirror_level,
    geometry,
    debug_artifact,
    recursive,
    exclude,
    include_ext,
    log_level,
    overwrite,
    run_id,
    slm,
):
    """Parse a document and save results."""
    import logging

    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    if slm:
        os.environ["DOCMIRROR_ENABLE_SLM"] = "1"
    resolved_skip_cache = cache_policy in {"refresh", "off"}

    from docmirror.__main__ import discover_inputs, parse_document

    inputs = discover_inputs(file, recursive=recursive, include_ext=include_ext)
    if exclude:
        inputs = [p for p in inputs if not any(pat in str(p) for pat in exclude)]
    if not inputs:
        raise click.ClickException(f"Path/glob not found or no files matched: {file}")
    if len(inputs) == 1:
        asyncio.run(
            parse_document(
                str(inputs[0].resolve()),
                "json",
                Path(output_dir),
                no_save=no_save,
                skip_cache=resolved_skip_cache,
                include_text=include_text,
                split_layers=split_layers,
                debug_artifact=debug_artifact,
                export_chunks=False,
                export_csv=False,
                export_parquet=False,
                mirror_level=mirror_level,
                pages=pages,
                max_pages=max_pages,
                workers=workers,
                mode=mode,
                formats=formats,
                editions=editions,
                cache_policy=cache_policy,
                doc_type=doc_type,
                doc_type_policy=doc_type_policy,
                doc_type_hint=None,
                ocr=ocr,
                geometry=geometry,
                include_geometry=None,
                run_id=run_id,
                overwrite=overwrite,
                slm=slm,
            )
        )
        return

    async def _parse_many() -> None:
        for fp in inputs:
            await parse_document(
                str(fp.resolve()),
                "json",
                Path(output_dir),
                no_save=no_save,
                skip_cache=resolved_skip_cache,
                include_text=include_text,
                split_layers=split_layers,
                debug_artifact=debug_artifact,
                export_chunks=False,
                export_csv=False,
                export_parquet=False,
                mirror_level=mirror_level,
                pages=pages,
                max_pages=max_pages,
                workers=workers,
                mode=mode,
                formats=formats,
                editions=editions,
                cache_policy=cache_policy,
                doc_type=doc_type,
                doc_type_policy=doc_type_policy,
                doc_type_hint=None,
                ocr=ocr,
                geometry=geometry,
                include_geometry=None,
                overwrite=overwrite,
                slm=slm,
            )

    asyncio.run(_parse_many())


if __name__ == "__main__":
    main()
