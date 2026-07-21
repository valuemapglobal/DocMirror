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
    "license": ("docmirror.cli.plugins", "license"),
    "mcp": ("docmirror.cli.mcp", "mcp"),
    "ocr": ("docmirror.cli.ocr_correction", "ocr_correction"),
    "pdfua": ("docmirror.cli.pdfua", "pdfua"),
    "plugins": ("docmirror.cli.plugins", "plugins"),
}

COMMAND_HELP = {
    "classify": "Classify commercial documents by type.",
    "doctor": "Show installation and optional capability status.",
    "license": "Show or manage the active license.",
    "mcp": "Start the DocMirror MCP server.",
    "ocr": "Maintain OCR correction packs.",
    "pdfua": "Convert a document to tagged PDF/UA.",
    "plugins": "Plugin management commands.",
}

_ADVANCED_PARSE_OPTIONS = (("--ocr-correction-pack ID", "Enable a correction pack; may be repeated."),)


class LazyGroup(click.Group):
    """Click group that imports optional subcommands only when invoked."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted({*super().list_commands(ctx), *COMMANDS})

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        if args and args[0] == "parse":
            raise click.UsageError("Use 'docmirror FILE' directly; the parse subcommand was removed.")
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
            command = self.get_command(ctx, name)
            if command is None or command.hidden:
                continue
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


def _show_help_all(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(ctx.get_help())
    formatter = click.HelpFormatter()
    with formatter.section("Advanced parse options"):
        formatter.write_dl(list(_ADVANCED_PARSE_OPTIONS))
    click.echo(formatter.getvalue().rstrip())
    ctx.exit()


@click.group(cls=LazyGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--help-all",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_show_help_all,
    help="Show help including advanced parse options and exit.",
)
@click.version_option(__version__, "-v", "--version", prog_name="DocMirror")
@click.pass_context
def main(ctx: click.Context) -> None:
    """The Trust Layer for Commercial Documents. Parse. Prove. Trust.

    Parse files directly with ``docmirror FILE [OPTIONS]``.
    """
    return


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


@main.command(hidden=True)
@click.argument("file", required=True)
@click.option(
    "--output-dir",
    "-o",
    default=lambda: os.environ.get("DOCMIRROR_TASK_OUTPUT_DIR", "output"),
    show_default=True,
    help="Output directory (env: DOCMIRROR_TASK_OUTPUT_DIR or default 'output')",
)
@click.option("--no-save", is_flag=True, help="Do not save result to disk")
@click.option(
    "-all",
    "--all",
    "all_outputs",
    is_flag=True,
    help="Also write the diagnostic Mirror JSON and manifest",
)
@click.option("--pages", "-p", default=None, help="Page ranges, 1-based: 1-3,8,10-")
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
@click.option(
    "--ocr-correction-pack",
    "ocr_correction_packs",
    multiple=True,
    hidden=True,
    help="Enable a correction pack by id",
)
@click.option(
    "--page-split",
    default="auto",
    type=click.Choice(["auto", "off", "force"]),
    show_default=True,
    help="Split scanned two-page spreads before OCR",
)
@click.option("--doc-type", "-t", default=None, help="Manual document type")
@click.option(
    "--doc-type-policy",
    default="prefer",
    type=click.Choice(["prefer", "force"]),
    show_default=True,
    help="How strongly to apply --doc-type",
)
@click.option("--recursive", "-r", is_flag=True, help="Recursively parse directory/glob inputs")
@click.option("--exclude", multiple=True, metavar="SUBSTR", help="Skip files whose path contains SUBSTR")
@click.option("--include-ext", default=None, help="Comma-separated extensions to include in batch mode")
@click.option("--verbose", is_flag=True, help="Show detailed pipeline logs")
@click.option("--quiet", "-q", is_flag=True, help="Suppress informational pipeline logs")
@click.option("--overwrite", is_flag=True, help="Allow overwriting an explicit --run-id output directory")
@click.option("--run-id", default=None, help="Explicit run/task id for output directory")
def parse(
    file: str,
    output_dir: str,
    no_save: bool,
    all_outputs: bool,
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
    doc_type: str | None,
    doc_type_policy: str,
    recursive: bool,
    exclude: tuple[str, ...],
    include_ext: str | None,
    verbose: bool,
    quiet: bool,
    overwrite: bool,
    run_id: str | None,
) -> None:
    """Parse a document and save the Community three-part bundle."""
    import asyncio
    import logging

    _load_env_if_available()
    if quiet and verbose:
        raise click.UsageError("--quiet and --verbose are mutually exclusive")
    resolved_log_level = "error" if quiet else ("debug" if verbose else "info")
    logging.basicConfig(level=getattr(logging, resolved_log_level.upper(), logging.INFO))
    from docmirror.__main__ import discover_inputs, parse_document

    inputs = discover_inputs(file, recursive=recursive, include_ext=include_ext)
    if exclude:
        inputs = [p for p in inputs if not any(pat in str(p) for pat in exclude)]
    if not inputs:
        raise click.ClickException(f"Path/glob not found or no files matched: {file}")

    async def _parse_one(path: Path) -> None:
        await parse_document(
            str(path.resolve()),
            Path(output_dir),
            no_save=no_save,
            pages=pages,
            max_pages=max_pages,
            workers=workers,
            mode=mode,
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
            run_id=run_id,
            overwrite=overwrite,
            all_outputs=all_outputs,
        )

    async def _parse_many() -> None:
        for path in inputs:
            await _parse_one(path)

    asyncio.run(_parse_many())


if __name__ == "__main__":
    main()
