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
import threading
import time
import traceback
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env", override=False)

# Default output directory (relative to cwd)
DEFAULT_OUTPUT_DIR = Path(os.environ.get("DOCMIRROR_TASK_OUTPUT_DIR", "output"))
DEFAULT_MIRROR_LEVEL = os.environ.get("DOCMIRROR_MIRROR_LEVEL", "standard")


def _safe_str(s: str) -> str:
    """Encode/decode to replace surrogates so console.print() never raises UnicodeEncodeError."""
    if not isinstance(s, str):
        s = str(s)
    return s.encode("utf-8", errors="replace").decode("utf-8")


def _effective_table_count(result) -> int:
    total = int(getattr(result, "total_tables", 0) or 0)
    if total > 0:
        return total
    mirror = getattr(result, "mirror", None)
    blocks = getattr(mirror, "blocks", None)
    if blocks is not None:
        return sum(1 for block in blocks if getattr(block, "type", None) == "table")
    if isinstance(mirror, dict):
        return sum(1 for block in mirror.get("blocks", []) if block.get("type") == "table")
    return total


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
[bold white]Commercial Document Trust Layer[/bold white]
[white]Parse. Prove. Trust.[/white]
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
    export_csv: bool = False,
    export_chunks: bool = False,
    export_parquet: bool = False,
    split_layers: bool = False,  # noqa: ARG001 — CLI reserved
    debug_artifact: bool = False,  # noqa: ARG001 — CLI reserved
) -> None:
    from docmirror.input.entry.factory import PerceiveOptions, perceive_document
    from docmirror.input.entry.options import normalize_parse_control

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
    )
    mirror_level = control.output.mirror_level
    include_text = control.output.include_text

    # ── ProgressBus with live Rich progress bar ──
    from docmirror.runtime import ProgressBus, ProgressSignal

    class _ProgressAdapter:
        """Adapt ProgressBus signals to a live Rich progress bar (thread-safe)."""

        def __init__(self, progress, task_id):
            self._lock = threading.Lock()
            self._progress = progress
            self._task_id = task_id

        def __call__(self, signal: ProgressSignal):
            with self._lock:
                self._progress.update(
                    self._task_id,
                    completed=signal.overall_pct,
                    description=f"[cyan]{signal.message}[/cyan]",
                )

    from rich.progress import BarColumn, TaskProgressColumn, TimeElapsedColumn

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
       console=console,
   )

    result = None
    _wall_start = 0.0
    _extraction_end = 0.0
    wall_elapsed_ms = 0
    file_id = "001"

    saved_path: Path | None = None
    written: dict[str, Path] = {}
    with progress:
        overall_task = progress.add_task("[cyan]Initializing...[/cyan]", total=100.0)
        adapter = _ProgressAdapter(progress, overall_task)
        bus = ProgressBus(on_progress=adapter)

        _wall_start = time.monotonic()
        try:
            # Phase 1: Extraction pipeline (real progress from pdf_processor etc.)
            bus.emit("load_document", 0.0, "Initializing document parser...")
            result = await perceive_document(
                path,
                PerceiveOptions(control=control, on_progress=bus.emit),
            )
            _extraction_end = time.monotonic()

            # Phase 2: Output building (community/enterprise/finance editions)
            bus.emit("community_plugin", 0.0, "Post-processing: building edition outputs...")
            if not no_save:
                file_id = "001"
                from docmirror.server.edition_outputs import write_four_files

                _saved_task_id, written = write_four_files(
                    result,
                    output_dir,
                    file_path=str(path),
                    full_text=result.full_text or "",
                    file_id=file_id,
                    mirror_level=mirror_level,
                    include_text=include_text,
                    editions=control.output.editions,
                    task_id=run_id,
                    overwrite=overwrite,
                    on_progress=bus.emit,
                )
                saved_path = written.get("mirror")

            # All phases complete — real "Done!" after all work
            bus.emit("extended_plugins", 100.0, "All editions complete")
            progress.update(overall_task, completed=100.0, description="[bold green]✅ Done![/bold green]")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            progress.update(overall_task, completed=100.0, description="[bold red]❌ Failed[/bold red]")
            console.print(f"[bold red]Critical Error:[/bold red] {_safe_str(str(e))}")
            return

    # Wall-clock elapsed for display metrics
    wall_elapsed_ms = int((time.monotonic() - _wall_start) * 1000) if _wall_start > 0 else 0

    # ── Display results (outside spinner) ──
    try:
        if result is not None and result.success:
            console.print("\n[bold green]\u2705 Parsing Complete![/bold green]")

            table = Table(show_header=False, border_style="green")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="white")

            table.add_row("Status", str(result.status))
            table.add_row("Confidence", f"{result.confidence:.2%}")
            table.add_row("Pages", str(result.page_count))
            table.add_row("Tables Found", str(_effective_table_count(result)))
            table.add_row("Extracted Text", f"{len(result.full_text)} chars")
            table.add_row("Time Elapsed", f"{wall_elapsed_ms:.0f} ms")

            # Wall-clock breakdown (CLI-02)
            _extraction_ms = int((_extraction_end - _wall_start) * 1000)
            _build_ms = int(max(0, wall_elapsed_ms - _extraction_ms))
            table.add_row("Extraction", f"{_extraction_ms:,} ms")
            if _build_ms > 10:
                table.add_row("Output Build", f"{_build_ms:,} ms")

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

            # Factual speed metric (no marketing pitch)
            effective_ms = max(_extraction_ms, 1)
            speed = len(result.full_text) / (effective_ms / 1000)
            _entities = getattr(result, "entities", None)
            _doc_type = getattr(_entities, "document_type", "unknown") if _entities else "unknown"
            console.print(
                f"\n[bold magenta]📊[/bold magenta] Performance: {speed:.0f} chars/sec  "
                f"| type={_doc_type}  | pages={result.page_count}  "
                f"| extraction={_extraction_ms}ms  build={_build_ms}ms"
            )
        else:
            console.print("\n[bold red]\u274c Parsing Failed[/bold red]")
            if result is not None and result.error:
                console.print(f"[red]{_safe_str(result.error.message)}[/red]")

            console.print("\n[bold yellow]Open Source Power[/bold yellow]")
            console.print("[white]Encountered an unsupported exotic format? This is how we improve![/white]")
            console.print("[white]Please attach the logs and a sample document by opening an issue at:[/white]")
            console.print("[cyan]https://github.com/valuemapglobal/docmirror/issues[/cyan]")

        # Display edition summaries (already written inside progress context)
        if not no_save and saved_path:

            console.print(f"[bold blue]\U0001f4be Mirror saved to:[/bold blue] [white]{saved_path}[/white]")
            _write_requested_exports(
                result,
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
        result,
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
    from docmirror.output.serialization import dumps_json

    artifacts: dict[str, str] = {"json": mirror_path.name}
    mirror_vnext: dict | None = None
    for fmt in formats:
        normalized = fmt.lower().strip()
        if normalized == "json":
            continue
        try:
            from docmirror.output.exporters.dispatch import export_parse_result

            if mirror_vnext is None and mirror_path.exists():
                try:
                    mirror_vnext = json.loads(mirror_path.read_text(encoding="utf-8"))
                except Exception:
                    mirror_vnext = {}
            payload, _media_type, suffix = export_parse_result(result, normalized, mirror_vnext=mirror_vnext)
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

    # Merge with any existing manifest (written by write_four_files with
    # edition_availability and mirror_completeness) so we never lose info.
    manifest_path = task_dir / "manifest.json"
    existing: dict = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    # Preserve edition artifacts from write_four_files (mirror, community, enterprise, finance)
    # while adding/overriding format-specific entries (json, markdown, csv, etc.)
    existing_artifacts = existing.get("artifacts", {})
    merged_artifacts = {**existing_artifacts, **artifacts}
    manifest = {**existing,
        "file_id": file_id,
        "formats": list(formats),
        "artifacts": merged_artifacts,
        "parse_control": parse_control,
        "parse_control_fingerprint": parse_control_fingerprint,
        "implicit_promotions": parse_control.get("implicit_promotions") or [],
        "deprecated_mappings": parse_control.get("deprecated_mappings") or [],
    }
    manifest_path.write_text(dumps_json(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifacts


def main() -> None:
    # ── Subcommand dispatch ──
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == "mcp":
        import argparse as _ap

        from docmirror.server.mcp import run_sse, run_stdio
        _p = _ap.ArgumentParser(prog="docmirror mcp", description="Start the DocMirror MCP (Model Context Protocol) server")
        _p.add_argument("--transport", choices=["stdio", "sse"], default="stdio",
                        help="Transport protocol (default: stdio). SSE allows HTTP clients.")
        _p.add_argument("--port", type=int, default=8001, help="Port for SSE transport (default: 8001)")
        _p.add_argument("--host", type=str, default="0.0.0.0", help="Host for SSE transport (default: 0.0.0.0)")
        _args = _p.parse_args(_sys.argv[2:])
        if _args.transport == "stdio":
            run_stdio()
        else:
            run_sse(host=_args.host, port=_args.port)
        return


    parser = argparse.ArgumentParser(
        description="DocMirror - The Trust Layer for Commercial Documents. Parse. Prove. Trust."
    )
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
        "--editions", default=None, help="Output editions: mirror,community,enterprise,finance,all"
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
        help="Skip files whose path contains SUBSTR (e.g. --exclude ICBC); can be repeated",
    )
    parser.add_argument("--include-ext", default=None, help="Comma-separated extensions to include in batch mode")
    parser.add_argument("--authors", action="store_true", help="Show contributors and authors")
    parser.add_argument("--include-text", action="store_true", help="Include full markdown text in output")
    parser.add_argument(
        "--mirror-level",
        default=None,
        choices=["standard", "compact", "forensic"],
        help=f"Mirror output level: standard/compact/forensic (default: {DEFAULT_MIRROR_LEVEL})",
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
    # --slm flag removed in v1.1 — superseded by LlmDocumentRestorer

    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    resolved_skip_cache = args.cache_policy in {"refresh", "off"}

    # args.slm removed in v1.1 — superseded by LlmDocumentRestorer

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
        from docmirror.input.entry.options import ResourceControl, normalize_parse_control

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
                    from docmirror.input.pipeline import perceive_document

                    path = fp.resolve()
                    result = await perceive_document(path)

                    # Handle both MirrorResult (new) and PerceptionResult (legacy fallback)
                    if hasattr(result, 'to_dict'):
                        vn_data = result.to_dict()
                        success = len(vn_data.get("pages", [])) > 0
                        doctype = (vn_data.get("document", {}) or {}).get("document_type", "unknown")
                        pages = len(vn_data.get("pages", []))
                        text_len = sum(len(str(a.get("text", ""))) for a in vn_data.get("evidence", {}).get("text_atoms", []))
                    else:
                        vn_data = result.to_mirror_json_vnext(source_filename=str(path))
                        success = result.success if hasattr(result, 'success') else True
                        doctype = getattr(getattr(result, "entities", None), "document_type", "unknown")
                        pages = getattr(result, "page_count", 0)
                        text_len = len(getattr(result, "full_text", ""))

                    if success:
                        console.print(
                            f"[bold cyan][{idx}/{total}][/bold cyan] ✅ {name}  → {doctype} ({pages}p, {text_len} chars)"
                        )
                    else:
                        console.print(f"[bold yellow][{idx}/{total}][/bold yellow] ⚠️ {name}  → parse returned failure")

                    if not args.no_save:
                        _save_multi_edition(
                            result,
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
            )
        )


if __name__ == "__main__":
    main()
