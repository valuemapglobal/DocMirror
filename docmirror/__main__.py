# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Executable module entry for ``python -m docmirror``.

Implements the default parse workflow invoked by the ``docmirror`` console
script: single-file parsing with Rich progress stages, recursive batch mode
with configurable concurrency, multi-edition JSON output (mirror, community,
enterprise, finance), optional cache bypass, and timestamped persistence
under ``output/``. Argument parsing lives in ``main()``; subcommands such as
``classify`` and ``plugins`` are registered separately in ``docmirror.cli.main``.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import logging
import multiprocessing
import os
import time
import traceback
from dataclasses import replace
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

# Default output directory (relative to cwd)
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_MIRROR_LEVEL = os.environ.get("DOCMIRROR_MIRROR_LEVEL", "standard")


def _safe_str(s: str) -> str:
    """Encode/decode to replace surrogates so console.print() never raises UnicodeEncodeError."""
    if not isinstance(s, str):
        s = str(s)
    return s.encode("utf-8", errors="replace").decode("utf-8")


# Skip these when discovering files in a directory
SKIP_NAMES = {".DS_Store", ".gitkeep", "Thumbs.db"}


def discover_files(root: Path, *, recursive: bool = False, include_ext: str | None = None) -> list[Path]:
    """Collect files under *root* (excludes SKIP_NAMES)."""
    allowed_ext = _parse_include_ext(include_ext)
    files: list[Path] = []
    iterator = root.rglob("*") if recursive else root.iterdir()
    for p in sorted(iterator):
        if p.is_file() and p.name not in SKIP_NAMES and _matches_include_ext(p, allowed_ext):
            files.append(p)
    return files


def _parse_include_ext(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip().lower().lstrip(".") for part in raw.split(",") if part.strip()}


def _matches_include_ext(path: Path, allowed_ext: set[str]) -> bool:
    if not allowed_ext:
        return True
    return path.suffix.lower().lstrip(".") in allowed_ext


def discover_inputs(raw: str, *, recursive: bool = False, include_ext: str | None = None) -> list[Path]:
    path = Path(raw).expanduser()
    allowed_ext = _parse_include_ext(include_ext)
    if path.exists():
        if path.is_dir():
            return discover_files(path, recursive=recursive, include_ext=include_ext)
        return [path] if _matches_include_ext(path, allowed_ext) else []
    matches = [Path(p) for p in glob.glob(raw, recursive=recursive)]
    return sorted(
        p for p in matches if p.is_file() and p.name not in SKIP_NAMES and _matches_include_ext(p, allowed_ext)
    )


BANNER = r"""[cyan]
 ____             __  __ _
|  _ \  ___   ___|  \/  (_)_ __ _ __ ___  _ __
| | | |/ _ \ / __| |\/| | | '__| '__/ _ \| '__|
| |_| | (_) | (__| |  | | | |  | | | (_) | |
|____/ \___/ \___|_|  |_|_|_|  |_|  \___/|_|
[/cyan]
[bold white]Universal Document Parsing Engine[/bold white]
[yellow]Support us with a ⭐ on GitHub: https://github.com/valuemapglobal/docmirror[/yellow]
"""


def print_banner():
    console.print(Panel(BANNER, border_style="cyan", padding=(1, 2)))


def show_authors():
    console.print(
        Panel(
            "[bold cyan]Made with \u2764\ufe0f by[/bold cyan]\n[white]Adam Lin[/white]",
            title="Authors",
            border_style="cyan",
        )
    )
    console.print(
        "\n[yellow]Want your name here? Contribute to DocMirror at: https://github.com/valuemapglobal/docmirror[/yellow]\n"
    )


async def parse_document(
    file_path: str,
    format_out: str,
    output_dir: Path,
    no_save: bool,
    skip_cache: bool = False,
    include_text: bool = False,
    mirror_level: str | None = None,
    *,
    pages: str | None = None,
    max_pages: int | None = None,
    workers: str | int | None = None,
    mode: str | None = None,
    formats: str | list[str] | tuple[str, ...] | None = None,
    editions: str | list[str] | tuple[str, ...] | None = None,
    cache_policy: str | None = None,
    doc_type: str | None = None,
    doc_type_policy: str | None = None,
    doc_type_hint: str | None = None,
    ocr: str | None = None,
    geometry: str | None = None,
    include_geometry: bool | None = None,
    run_id: str | None = None,
    overwrite: bool = False,
    slm: bool = False,
    export_csv: bool = False,
    export_chunks: bool = False,
    export_parquet: bool = False,
    split_layers: bool = False,  # noqa: ARG001 — CLI reserved
    debug_artifact: bool = False,  # noqa: ARG001 — CLI reserved
) -> None:
    from docmirror.core.entry.factory import PerceiveOptions, perceive_document
    from docmirror.core.entry.options import normalize_parse_control

    path = Path(file_path).resolve()
    if not path.exists():
        console.print(f"[bold red]Error[/bold red]: File not found: {file_path}")
        return
    if path.is_dir():
        console.print(
            f"[bold red]Error[/bold red]: Path is a directory (use it as the batch root to parse all files inside): {path}"
        )
        return

    requested_formats = formats if formats is not None else format_out
    extra_formats = []
    if export_csv:
        console.print("[yellow]Deprecated:[/yellow] --export-csv is deprecated; use -f csv or -f json,csv.")
        extra_formats.append("csv")
    if export_chunks:
        console.print("[yellow]Deprecated:[/yellow] --export-chunks is deprecated; use -f chunks or -f json,chunks.")
        extra_formats.append("chunks")
    if export_parquet:
        extra_formats.append("parquet")
    if extra_formats:
        requested_formats = ",".join([str(requested_formats), *extra_formats])
    control = normalize_parse_control(
        pages=pages,
        max_pages=max_pages,
        workers=workers,
        mode=mode,
        formats=requested_formats,
        editions=editions,
        mirror_level=mirror_level,
        geometry=geometry,
        include_geometry=include_geometry,
        include_text=include_text,
        doc_type=doc_type,
        doc_type_policy=doc_type_policy,
        doc_type_hint=doc_type_hint,
        cache_policy=cache_policy,
        skip_cache=skip_cache,
        ocr=ocr,
        slm=slm,
    )
    mirror_level = control.output.mirror_level
    include_text = control.output.include_text

    # ── Pipeline stage definitions for progress display ──
    STAGES = [
        (5, "[cyan]Loading document...[/cyan]"),
        (15, "[cyan]Extracting pages...[/cyan]"),
        (35, "[cyan]Detecting layout & tables...[/cyan]"),
        (55, "[cyan]Running OCR & text extraction...[/cyan]"),
        (70, "[cyan]Analyzing entities & structure...[/cyan]"),
        (85, "[cyan]Mapping columns & validating...[/cyan]"),
        (95, "[cyan]Building result...[/cyan]"),
    ]

    from rich.progress import BarColumn, TaskProgressColumn, TimeElapsedColumn

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    async def _animate_progress(progress, task_id):
        """Simulate stage-based progress while parsing runs."""
        start = time.monotonic()
        stage_idx = 0
        while not progress.tasks[task_id].finished:
            elapsed = time.monotonic() - start
            # Advance through stages based on elapsed time
            # Rough heuristic: ~2s per stage for a typical document
            target_stage = min(int(elapsed / 2.0), len(STAGES) - 1)
            while stage_idx <= target_stage and stage_idx < len(STAGES):
                pct, desc = STAGES[stage_idx]
                progress.update(task_id, completed=pct, description=desc)
                stage_idx += 1
            await asyncio.sleep(0.15)

    with progress:
        task_id = progress.add_task(
            STAGES[0][1],
            total=100,
        )
        # Start progress animation concurrently with parsing
        _wall_start = time.monotonic()
        anim_task = asyncio.create_task(_animate_progress(progress, task_id))
        try:
            result = await perceive_document(path, PerceiveOptions(control=control))
            progress.update(task_id, completed=100, description="[bold green]✅ Done![/bold green]")
            anim_task.cancel()
        except Exception as e:
            progress.update(task_id, completed=100, description="[bold red]❌ Failed[/bold red]")
            anim_task.cancel()
            console.print(f"[bold red]Critical Error:[/bold red] {_safe_str(str(e))}")
            return

    wall_elapsed_ms = (time.monotonic() - _wall_start) * 1000

    # ── Display results (outside spinner) ──
    try:
        if result.success:
            console.print("\n[bold green]\u2705 Parsing Complete![/bold green]")

            table = Table(show_header=False, border_style="green")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="white")

            table.add_row("Status", str(result.status))
            table.add_row("Confidence", f"{result.confidence:.2%}")
            table.add_row("Pages", str(result.page_count))
            table.add_row("Tables Found", str(result.total_tables))
            table.add_row("Extracted Text", f"{len(result.full_text)} chars")
            table.add_row("Time Elapsed", f"{wall_elapsed_ms:.0f} ms")

            # Detect cached results: internal timing >> wall time
            is_cached = (
                result.parser_info
                and result.parser_info.elapsed_ms > 0
                and wall_elapsed_ms < result.parser_info.elapsed_ms * 0.5
                and wall_elapsed_ms < 2000
            )
            if is_cached:
                table.add_row("", "[dim italic]⚡ cached result[/dim italic]")

            console.print(table)

            effective_ms = max(wall_elapsed_ms, 1)
            speed = len(result.full_text) / (effective_ms / 1000)
            console.print(f"\n[bold magenta]\u26a1 BLAZING FAST:[/bold magenta] Processed at {speed:.0f} chars/sec!")
            console.print(
                "[dim]Copy this benchmark and share it on Twitter / V2EX to show off your speed! \u26a1[/dim]"
            )
        else:
            console.print("\n[bold red]\u274c Parsing Failed[/bold red]")
            if result.error:
                console.print(f"[red]{_safe_str(result.error.message)}[/red]")

            console.print("\n[bold yellow]Open Source Power[/bold yellow]")
            console.print("[white]Encountered an unsupported exotic format? This is how we improve![/white]")
            console.print("[white]Please attach the logs and a sample document by opening an issue at:[/white]")
            console.print("[cyan]https://github.com/valuemapglobal/docmirror/issues[/cyan]")

        # Save result to disk (both success and failure, for diagnostics)
        if not no_save:
            file_id = "001"
            from docmirror.server.edition_outputs import write_four_files

            task_id, written = write_four_files(
                result.mirror if hasattr(result, "mirror") else result,
                output_dir,
                file_path=str(path),
                full_text=result.full_text or "",
                file_id=file_id,
                mirror_level=mirror_level,
                include_text=include_text,
                editions=control.output.editions,
                task_id=run_id,
                overwrite=overwrite,
            )
            saved_path = written["mirror"]

            # Generate community edition output with IDs
            community_schema = None
            if "community" in written:
                community_path = written["community"]
                community_schema = json.loads(community_path.read_text(encoding="utf-8"))
                summary = _format_community_summary(community_schema)
                console.print(f"[cyan]📦 Community:[/cyan] {community_path.name}  → {summary}")

            # Generate enterprise edition output (docmirror-enterprise)
            enterprise_schema = None
            if "enterprise" in written:
                enterprise_path = written["enterprise"]
                enterprise_schema = json.loads(enterprise_path.read_text(encoding="utf-8"))
                rows = enterprise_schema.get("data", {}).get("summary", {}).get("total_rows", 0)
                doctype = enterprise_schema.get("document", {}).get("document_type", "unknown")
                console.print(f"[cyan]📦 Enterprise:[/cyan] {enterprise_path.name}  → {doctype} ({rows} rows)")

            # Generate finance edition output (docmirror-finance)
            finance_schema = None
            if "finance" in written:
                finance_path = written["finance"]
                finance_schema = json.loads(finance_path.read_text(encoding="utf-8"))
                rows = finance_schema.get("data", {}).get("summary", {}).get("total_rows", 0)
                doctype = finance_schema.get("document", {}).get("document_type", "unknown")
                console.print(f"[cyan]📦 Finance:[/cyan] {finance_path.name}  → {doctype} ({rows} rows)")

            _print_entitlement_warnings(enterprise_schema, finance_schema)

            console.print(f"[bold blue]\U0001f4be Mirror saved to:[/bold blue] [white]{saved_path}[/white]")
            _write_requested_exports(
                result.mirror if hasattr(result, "mirror") else result,
                saved_path.parent,
                file_id=file_id,
                formats=control.output.formats,
                mirror_path=saved_path,
                parse_control=control.to_dict(),
                parse_control_fingerprint=control.fingerprint(),
            )

    except Exception as e:
        console.print(f"[bold red]Critical Error:[/bold red] {_safe_str(str(e))}")


def _save_multi_edition(
    result,
    _api_dict: dict,
    path: Path,
    output_dir: Path,
    include_text: bool = False,
    mirror_level: str = "standard",
    editions: tuple[str, ...] | list[str] | None = None,
    task_id: str | None = None,
    overwrite: bool = False,
) -> str:
    """Save mirror + community + enterprise + finance outputs to a timestamped subdirectory.

    Returns task_id (directory name).
    """
    from docmirror.server.edition_outputs import write_four_files

    task_id, _written = write_four_files(
        result.mirror if hasattr(result, "mirror") else result,
        output_dir,
        file_path=str(path),
        full_text=getattr(result, "full_text", "") or "",
        file_id="001",
        task_id=task_id,
        mirror_level=mirror_level,
        include_text=include_text,
        editions=editions,
        overwrite=overwrite,
    )
    return task_id


def _write_requested_exports(
    result,
    task_dir: Path,
    *,
    file_id: str,
    formats: tuple[str, ...],
    mirror_path: Path,
    parse_control: dict,
    parse_control_fingerprint: str,
) -> dict[str, str]:
    """Write non-JSON requested exports and a small artifact manifest."""
    from docmirror.models.serialization import dumps_json

    artifacts: dict[str, str] = {"json": mirror_path.name}
    for fmt in formats:
        normalized = fmt.lower().strip()
        if normalized == "json":
            continue
        try:
            if normalized == "markdown":
                out_path = task_dir / f"{file_id}.md"
                out_path.write_text(getattr(result, "full_text", "") or "", encoding="utf-8")
            else:
                from docmirror.exporters.dispatch import export_parse_result

                payload, _media_type, suffix = export_parse_result(result, normalized)
                out_path = task_dir / f"{file_id}{suffix}"
                if isinstance(payload, bytes):
                    out_path.write_bytes(payload)
                else:
                    out_path.write_text(payload, encoding="utf-8")
            artifacts[normalized] = out_path.name
            console.print(f"[cyan]📄 Export:[/cyan] {out_path.name}")
        except Exception as exc:
            artifacts[normalized] = f"ERROR: {exc}"
            console.print(f"[yellow]Export {normalized} skipped:[/yellow] {exc}")

    manifest = {
        "file_id": file_id,
        "formats": list(formats),
        "artifacts": artifacts,
        "parse_control": parse_control,
        "parse_control_fingerprint": parse_control_fingerprint,
        "implicit_promotions": parse_control.get("implicit_promotions") or [],
        "deprecated_mappings": parse_control.get("deprecated_mappings") or [],
    }
    manifest_path = task_dir / "manifest.json"
    manifest_path.write_text(dumps_json(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifacts


def _print_entitlement_warnings(*schemas: dict | None) -> None:
    """Print entitlement / lifecycle summaries after edition outputs."""
    from docmirror.plugins.licensing.lifecycle import lifecycle_cli_message

    msg = lifecycle_cli_message()
    if msg:
        console.print(f"[yellow]⚠ License:[/yellow] {msg}")

    for schema in schemas:
        if not schema:
            continue
        warnings = (schema.get("status") or {}).get("warnings") or []
        if "_license_warning" not in warnings:
            continue
        edition = schema.get("edition") or "enterprise"
        console.print(
            f"[yellow]⚠ Entitlement:[/yellow] {edition} output degraded "
            f"(missing license). Run [cyan]docmirror plugins license show[/cyan]"
        )


def _format_community_summary(community_schema: dict) -> str:
    """Human-readable community 6+1 summary for CLI."""
    data = community_schema.get("data") or {}
    plugin = community_schema.get("plugin") or {}
    doctype = community_schema.get("document", {}).get("document_type", "unknown")
    name = plugin.get("name", doctype)
    rows = (data.get("summary") or {}).get("total_rows", 0)
    if name == "generic":
        nf = len(data.get("fields") or {})
        ns = len(data.get("sections") or [])
        return f"{doctype} via generic ({nf} fields, {ns} sections, {rows} rows)"
    if rows:
        return f"{name} premium ({rows} rows)"
    nf = len(data.get("fields") or {})
    return f"{name} premium ({nf} fields)"


def _build_community_output(result, full_text: str = "") -> dict | None:
    """Delegate to shared output_builder (CLI/API shared)."""
    from docmirror.server.output_builder import build_community_output

    return build_community_output(result, full_text)


def _build_extended_output(result, edition: str, full_text: str = "", file_path: str = "") -> dict | None:
    """Delegate to shared output_builder (CLI/API shared)."""
    from docmirror.server.output_builder import build_extended_output

    return build_extended_output(result, edition, full_text, file_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="DocMirror - Universal Document Parsing Engine")
    parser.add_argument("file", nargs="?", help="Path to a document, directory, or glob")
    parser.add_argument(
        "--format", "-f", default="json", help="Output formats: json,csv,markdown,chunks,html,parquet,all"
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to save parse results (default: ./output)",
    )
    parser.add_argument("--no-save", action="store_true", help="Do not save result to disk")
    parser.add_argument(
        "--cache-policy",
        choices=["read-write", "read-only", "refresh", "off"],
        default="read-write",
        help="Cache policy: read-write/read-only/refresh/off",
    )
    parser.add_argument("--pages", default=None, help="Page ranges, 1-based: 1-3,8,10-")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum pages after applying --pages")
    parser.add_argument("--workers", "-j", default=None, help="Total worker budget for this command (int or auto)")
    parser.add_argument(
        "--mode",
        "-m",
        default="auto",
        choices=["auto", "fast", "balanced", "accurate", "forensic"],
        help="Parse mode",
    )
    parser.add_argument("--ocr", default="auto", choices=["auto", "force", "off", "fallback"], help="OCR policy")
    parser.add_argument(
        "--editions", default="mirror,community", help="Output editions: mirror,community,enterprise,finance,all"
    )
    parser.add_argument("--doc-type", default=None, help="Manual document type")
    parser.add_argument(
        "--doc-type-policy",
        default="prefer",
        choices=["prefer", "force"],
        help="How strongly to apply --doc-type",
    )
    parser.add_argument("--recursive", action="store_true", help="Recursively parse directory/glob inputs")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="SUBSTR",
        help="Skip files whose path contains SUBSTR (e.g. --exclude 工商银行); can be repeated",
    )
    parser.add_argument("--include-ext", default=None, help="Comma-separated extensions to include in batch mode")
    parser.add_argument("--authors", action="store_true", help="Show contributors and authors")
    parser.add_argument("--include-text", action="store_true", help="Include full markdown text in output")
    parser.add_argument(
        "--mirror-level",
        default=None,
        choices=["standard", "forensic"],
        help=f"Mirror output level: standard/forensic (default: {DEFAULT_MIRROR_LEVEL})",
    )
    parser.add_argument(
        "--geometry",
        default=None,
        choices=["none", "page", "block", "token", "full"],
        help="Geometry output level",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Allow overwriting an explicit --run-id output directory"
    )
    parser.add_argument("--run-id", default=None, help="Explicit run/task id for output directory")
    parser.add_argument(
        "--slm",
        action="store_true",
        help="[Experimental] Enable pure CPU Small Language Model (SLM) semantic KV extraction",
    )

    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    resolved_skip_cache = args.cache_policy in {"refresh", "off"}

    if args.slm:
        os.environ["DOCMIRROR_ENABLE_SLM"] = "1"

    if args.authors:
        print_banner()
        show_authors()
        return

    if not args.file:
        print_banner()
        parser.print_help()
        return

    print_banner()
    files = discover_inputs(args.file, recursive=args.recursive, include_ext=args.include_ext)
    path = Path(args.file).expanduser().resolve()
    if not files:
        console.print(f"[bold red]Error[/bold red]: Path/glob not found or no supported files matched: {args.file}")
        return

    if path.is_dir() or len(files) > 1:
        if args.exclude:
            excluded = [f for f in files if any(pat in str(f) for pat in args.exclude)]
            files = [f for f in files if not any(pat in str(f) for pat in args.exclude)]
            if excluded:
                console.print(f"[dim]Excluding {len(excluded)} file(s) matching: {', '.join(args.exclude)}[/dim]")
        if not files:
            console.print(f"[bold yellow]No files found under[/bold yellow] {path}")
            return
        console.print(f"[bold cyan]Batch mode:[/bold cyan] {len(files)} file(s) under [white]{path}[/white]\n")

        from docmirror.configs.runtime.performance import resolve_worker_budget
        from docmirror.core.entry.options import ResourceControl, normalize_parse_control

        control = normalize_parse_control(
            pages=args.pages,
            max_pages=args.max_pages,
            workers=args.workers,
            mode=args.mode,
            formats=args.format,
            editions=args.editions,
            mirror_level=args.mirror_level,
            geometry=args.geometry,
            include_geometry=None,
            include_text=args.include_text,
            doc_type=args.doc_type,
            doc_type_policy=args.doc_type_policy,
            doc_type_hint=None,
            cache_policy=args.cache_policy,
            skip_cache=resolved_skip_cache,
            ocr=args.ocr,
            slm=args.slm,
        )
        _cpu_count = multiprocessing.cpu_count()
        _budget = resolve_worker_budget(control.resource.workers, file_count=len(files), cpu_count=_cpu_count)
        _semaphore = asyncio.Semaphore(_budget.file_workers)
        _per_file_control = replace(
            control,
            resource=ResourceControl(
                workers=_budget.page_workers_per_file,
                page_executor=control.resource.page_executor,
            ),
        )
        console.print(
            f"[dim]🔥 Worker budget: total={_budget.total}, files={_budget.file_workers}, "
            f"pages/file={_budget.page_workers_per_file}, layout={_budget.layout_workers} "
            f"({_cpu_count} CPU cores)[/dim]\n"
        )

        async def _process_one(fp: Path, idx: int, total: int):
            """Parse a single file in batch mode (no Rich Progress per file)."""
            async with _semaphore:
                name = fp.name
                console.print(f"[bold cyan][{idx}/{total}][/bold cyan] ⏳ {name}")
                try:
                    from docmirror.core.entry.factory import PerceiveOptions, perceive_document

                    path = fp.resolve()
                    result = await perceive_document(path, PerceiveOptions(control=_per_file_control))

                    api_dict = result.to_api_dict(
                        include_text=_per_file_control.output.include_text,
                        mirror_level=_per_file_control.output.mirror_level,
                    )
                    if result.success:
                        doctype = getattr(result.entities, "document_type", "unknown")
                        pages = getattr(result, "page_count", 0)
                        text_len = len(getattr(result, "full_text", ""))
                        console.print(
                            f"[bold cyan][{idx}/{total}][/bold cyan] ✅ {name}  → {doctype} ({pages}p, {text_len} chars)"
                        )
                    else:
                        console.print(f"[bold yellow][{idx}/{total}][/bold yellow] ⚠️ {name}  → parse returned failure")

                    if not args.no_save:
                        _save_multi_edition(
                            result,
                            api_dict,
                            path,
                            args.output_dir,
                            _per_file_control.output.include_text,
                            _per_file_control.output.mirror_level,
                            editions=control.output.editions,
                            overwrite=args.overwrite,
                        )
                except Exception as e:
                    console.print(f"[bold red][{idx}/{total}][/bold red] ❌ {name}: {e}")
                    console.print(f"[dim red]{traceback.format_exc()[:300]}[/dim red]")

        async def _batch_parse():
            tasks = [_process_one(fp, i, len(files)) for i, fp in enumerate(files, 1)]
            await asyncio.gather(*tasks)
            console.print(f"[bold green]\n🎉 All {len(files)} files processed![/bold green]")

        asyncio.run(_batch_parse())
    else:
        asyncio.run(
            parse_document(
                str(files[0]),
                args.format,
                args.output_dir,
                args.no_save,
                resolved_skip_cache,
                args.include_text,
                args.mirror_level,
                pages=args.pages,
                max_pages=args.max_pages,
                workers=args.workers,
                mode=args.mode,
                formats=args.format,
                editions=args.editions,
                cache_policy=args.cache_policy,
                doc_type=args.doc_type,
                doc_type_policy=args.doc_type_policy,
                doc_type_hint=None,
                ocr=args.ocr,
                geometry=args.geometry,
                include_geometry=None,
                run_id=args.run_id,
                overwrite=args.overwrite,
                slm=args.slm,
            )
        )


if __name__ == "__main__":
    main()
