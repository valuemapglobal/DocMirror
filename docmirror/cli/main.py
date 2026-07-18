# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""DocMirror CLI root.

The root command is intentionally dependency-light. Heavy parse, server, plugin,
and PDF/UA modules are imported only when their subcommands run.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from typing import Any

import click

from docmirror import __version__

TAGLINE = "DocMirror - The Trust Layer for Commercial Documents. Parse. Prove. Trust."

COMMANDS = {
    "classify": ("docmirror.cli.classify", "classify"),
    "mcp": ("docmirror.cli.mcp", "mcp"),
    "ocr-correction": ("docmirror.cli.ocr_correction", "ocr_correction"),
    "pdfua": ("docmirror.cli.pdfua", "pdfua"),
    "plugins": ("docmirror.cli.plugins", "plugins"),
}

COMMAND_HELP = {
    "classify": "Classify commercial documents by type.",
    "doctor": "Show installation and optional capability status.",
    "mcp": "Start the DocMirror MCP server.",
    "ocr-correction": "Validate, inspect, and evaluate OCR correction packs.",
    "parse": "Parse a document; Community JSON is the default output.",
    "pdfua": "Convert a document to tagged PDF/UA.",
    "plugins": "Plugin management commands.",
    "version": "Print the DocMirror version.",
}


class LazyGroup(click.Group):
    """Click group that imports optional subcommands only when invoked."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted({*super().list_commands(ctx), *COMMANDS})

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        if args and _looks_like_parse_input(args[0]) and args[0] not in self.list_commands(ctx):
            return "parse", self.get_command(ctx, "parse"), args
        return super().resolve_command(ctx, args)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command
        target = COMMANDS.get(cmd_name)
        if target is None:
            return None
        module_name, attr = target
        module = importlib.import_module(module_name)
        return getattr(module, attr)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        rows = []
        for name in self.list_commands(ctx):
            rows.append((name, COMMAND_HELP.get(name, "")))
        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


def _load_env_if_available() -> None:
    spec = importlib.util.find_spec("dotenv")
    if spec is None:
        return
    from dotenv import load_dotenv

    env_root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(env_root / ".env", override=False)


def _looks_like_parse_input(value: str) -> bool:
    if value.startswith("-"):
        return False
    if any(char in value for char in "*?["):
        return True
    suffix = Path(value).suffix.lower()
    if suffix:
        return True
    return Path(value).exists()


@click.group(cls=LazyGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="DocMirror")
@click.pass_context
def main(ctx: click.Context) -> None:
    """The Trust Layer for Commercial Documents. Parse. Prove. Trust."""
    return


@main.command("version")
def version() -> None:
    """Print the DocMirror version."""
    click.echo(__version__)


@main.command("doctor")
def doctor() -> None:
    """Show installation and optional capability status."""
    capabilities = {
        "core": ["pydantic", "yaml", "rich", "filetype", "click"],
        "pdf": ["fitz", "pdfplumber"],
        "ocr": ["numpy", "cv2", "rapidocr_onnxruntime"],
        "office": ["docx", "openpyxl", "pptx"],
        "server": ["fastapi", "uvicorn"],
        "ai": ["openai", "google.generativeai"],
    }
    click.echo(f"DocMirror {__version__}")
    click.echo("Category: Commercial Document Trust Layer")
    for name, modules in capabilities.items():
        missing = [module for module in modules if _find_spec_quiet(module) is None]
        if missing:
            install = "" if name == "core" else f" (install: pip install 'docmirror[{name}]')"
            click.echo(f"- {name}: missing {', '.join(missing)}{install}")
        else:
            click.echo(f"- {name}: ok")


def _find_spec_quiet(module_name: str) -> Any:
    try:
        return importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        return None


@main.command()
@click.argument("file", required=True)
@click.option(
    "--output-dir",
    "-o",
    default=lambda: os.environ.get("DOCMIRROR_TASK_OUTPUT_DIR", "output"),
    show_default=True,
    help="Output directory (env: DOCMIRROR_TASK_OUTPUT_DIR or default 'output')",
)
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
    "--ocr-correction",
    default="safe",
    type=click.Choice(["off", "safe", "suggest"]),
    show_default=True,
    help="Deterministic OCR correction policy",
)
@click.option("--ocr-language", default=None, help="ISO 639 OCR language hint, for example zh or en")
@click.option("--ocr-country", default=None, help="ISO 3166-1 alpha-2 country hint, for example CN or US")
@click.option("--ocr-locale", default=None, help="OCR locale hint, for example zh-CN")
@click.option("--ocr-correction-pack", "ocr_correction_packs", multiple=True, help="Enable a correction pack by id")
@click.option(
    "--page-split",
    default="auto",
    type=click.Choice(["auto", "off", "force"]),
    show_default=True,
    help="Split scanned two-page spreads before OCR",
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
    default=None,
    hidden=True,
    help="Output editions: mirror,community,enterprise,finance,all",
)
@click.option(
    "--mirror",
    "include_mirror",
    is_flag=True,
    help="Also persist the canonical _mirror.json diagnostic artifact",
)
@click.option(
    "--profile",
    "output_profile",
    default=None,
    type=click.Choice(["community", "default", "editions", "quickstart", "ga_full", "full", "forensic", "compact"]),
    metavar="PROFILE",
    show_choices=False,
    help="Output artifact profile, for example quickstart, compact, or forensic",
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
@click.option("--split-layers", is_flag=True, hidden=True, help="Export L1/L2/L3 as separate files")
@click.option("--include-text", is_flag=True, hidden=True, help="Include full text in output")
@click.option(
    "--mirror-level",
    default=None,
    type=click.Choice(["standard", "compact", "forensic"]),
    hidden=True,
    help="Mirror output level: standard/compact/forensic",
)
@click.option(
    "--geometry",
    default=None,
    type=click.Choice(["none", "page", "block", "token", "full"]),
    hidden=True,
    help="Geometry output level",
)
@click.option("--debug-artifact", is_flag=True, hidden=True, help="Write debug artifact")
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
def parse(
    file: str,
    output_dir: str,
    no_save: bool,
    pages: str | None,
    max_pages: int | None,
    workers: str | None,
    mode: str,
    ocr: str,
    ocr_correction: str,
    ocr_language: str | None,
    ocr_country: str | None,
    ocr_locale: str | None,
    ocr_correction_packs: tuple[str, ...],
    page_split: str,
    formats: str,
    editions: str,
    include_mirror: bool,
    output_profile: str | None,
    doc_type: str | None,
    doc_type_policy: str,
    cache_policy: str,
    split_layers: bool,
    include_text: bool,
    mirror_level: str | None,
    geometry: str | None,
    debug_artifact: bool,
    recursive: bool,
    exclude: tuple[str, ...],
    include_ext: str | None,
    log_level: str,
    overwrite: bool,
    run_id: str | None,
) -> None:
    """Parse a document and save Community JSON by default."""
    import asyncio
    import logging

    _load_env_if_available()
    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    resolved_skip_cache = cache_policy in {"refresh", "off"}

    from docmirror.__main__ import discover_inputs, parse_document

    inputs = discover_inputs(file, recursive=recursive, include_ext=include_ext)
    if exclude:
        inputs = [p for p in inputs if not any(pat in str(p) for pat in exclude)]
    if not inputs:
        raise click.ClickException(f"Path/glob not found or no files matched: {file}")

    requested_editions = editions
    if include_mirror:
        requested_editions = "mirror,community" if editions is None else f"mirror,{editions}"

    async def _parse_one(path: Path) -> None:
        await parse_document(
            str(path.resolve()),
            "json",
            Path(output_dir),
            no_save=no_save,
            skip_cache=resolved_skip_cache,
            include_text=include_text,
            split_layers=split_layers,
            debug_artifact=debug_artifact,
            export_parquet=False,
            mirror_level=mirror_level,
            pages=pages,
            max_pages=max_pages,
            workers=workers,
            mode=mode,
            formats=formats,
            editions=requested_editions,
            output_profile=output_profile,
            cache_policy=cache_policy,
            doc_type=doc_type,
            doc_type_policy=doc_type_policy,
            doc_type_hint=None,
            ocr=ocr,
            ocr_correction=ocr_correction,
            ocr_language=ocr_language,
            ocr_country=ocr_country,
            ocr_locale=ocr_locale,
            ocr_correction_packs=ocr_correction_packs,
            page_split=page_split,
            geometry=geometry,
            include_geometry=None,
            run_id=run_id,
            overwrite=overwrite,
        )

    async def _parse_many() -> None:
        for path in inputs:
            await _parse_one(path)

    asyncio.run(_parse_many())


if __name__ == "__main__":
    main()
