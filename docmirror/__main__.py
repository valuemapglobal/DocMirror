# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Executable module entry for ``python -m docmirror``.

Implements the default parse workflow invoked by the ``docmirror`` console
script: single-file parsing with Rich progress stages, recursive batch mode
with configurable concurrency, multi-edition JSON output (mirror, community,
enterprise, finance), and timestamped persistence
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


def _community_review_summary(path: Path | None) -> dict[str, object] | None:
    """Read a compact, user-facing review summary from the saved Community JSON."""
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if (payload.get("schema") or {}).get("name") == "docmirror.community":
        schema = payload.get("schema") or {}
        document = payload.get("document") or {}
        warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
        actionable = [item for item in warnings if isinstance(item, dict) and item.get("level") in {"warning", "error"}]
        review_messages = [str(item.get("message") or "") for item in actionable if item.get("message")][:3]
        return {
            "plugin": str(schema.get("support_level") or "unknown"),
            "document_type": str(document.get("type") or schema.get("domain") or "unknown"),
            "score": 1.0 if not actionable else 0.0,
            "readiness": "ready" if not actionable else "review",
            "warning_count": len(actionable),
            "review_messages": review_messages,
        }
    plugin = payload.get("plugin") if isinstance(payload.get("plugin"), dict) else {}
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    issues = quality.get("issues") if isinstance(quality.get("issues"), list) else []
    review_messages = [
        str(issue.get("message") or "")
        for issue in issues
        if isinstance(issue, dict) and issue.get("severity") in {"warning", "error"} and issue.get("message")
    ][:3]
    return {
        "plugin": str(plugin.get("name") or "unknown"),
        "document_type": str(classification.get("matched_document_type") or "unknown"),
        "score": float(quality.get("score", 0.0) or 0.0),
        "readiness": str(quality.get("readiness") or "unknown"),
        "warning_count": len(status.get("warnings") or []),
        "review_messages": review_messages,
    }


def _show_community_review_summary(path: Path | None) -> None:
    summary = _community_review_summary(path)
    if summary is None:
        return
    console.print(
        "[bold cyan]Community:[/bold cyan] "
        f"plugin={_safe_str(str(summary['plugin']))}  "
        f"type={_safe_str(str(summary['document_type']))}  "
        f"quality={float(summary['score']):.4f}  "
        f"readiness={_safe_str(str(summary['readiness']))}  "
        f"warnings={int(summary['warning_count'])}"
    )
    for message in summary["review_messages"]:
        console.print(f"[yellow]Review:[/yellow] {_safe_str(str(message))}")
    if summary["plugin"] == "generic" and summary["readiness"] == "review":
        console.print(
            "[dim]For difficult scans: --mode accurate --ocr force --ocr-language zh "
            "--ocr-locale zh-CN --ocr-correction safe --page-split auto[/dim]"
        )


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
[yellow]Support us with a ⭐ on GitHub: https://github.com/valuemapglobal/DocMirror[/yellow]
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
        "\n[yellow]Want your name here? Contribute to DocMirror at: https://github.com/valuemapglobal/DocMirror[/yellow]\n"
    )


async def parse_document(
    file_path: str,
    output_dir: Path,
    no_save: bool,
    *,
    pages: str | None = None,
    max_pages: int | None = None,
    workers: str | int | None = None,
    mode: str | None = None,
    doc_type: str | None = None,
    doc_type_policy: str | None = None,
    doc_type_hint: str | None = None,
    ocr: str | None = None,
    ocr_correction: str | None = None,
    ocr_language: str | None = None,
    ocr_country: str | None = None,
    ocr_locale: str | None = None,
    ocr_correction_packs: str | list[str] | tuple[str, ...] | None = None,
    page_split: str | None = None,
    run_id: str | None = None,
    overwrite: bool = False,
    all_outputs: bool = False,
) -> None:
    from docmirror.input.entry.factory import PerceiveOptions, perceive_document
    from docmirror.input.entry.options import normalize_parse_policy

    path = Path(file_path).resolve()
    if not path.exists():
        console.print(f"[bold red]Error[/bold red]: File not found: {file_path}")
        return
    if path.is_dir():
        console.print(
            f"[bold red]Error[/bold red]: Path is a directory (use it as the batch root to parse all files inside): {path}"
        )
        return

    policy = normalize_parse_policy(
        pages=pages,
        max_pages=max_pages,
        mode=mode,
        doc_type=doc_type,
        doc_type_policy=doc_type_policy,
        doc_type_hint=doc_type_hint,
        ocr=ocr,
        ocr_correction=ocr_correction,
        ocr_language=ocr_language,
        ocr_country=ocr_country,
        ocr_locale=ocr_locale,
        ocr_correction_packs=ocr_correction_packs,
        page_split=page_split,
    )
    from docmirror.configs.runtime.performance import resolve_worker_budget

    page_workers = resolve_worker_budget(workers, file_count=1).page_workers_per_file

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
                PerceiveOptions(policy=policy, max_workers=page_workers, on_progress=bus.emit),
            )
            _extraction_end = time.monotonic()

            # Phase 2: Output building (community/enterprise/finance editions)
            bus.emit("community_plugin", 0.0, "Post-processing: building edition outputs...")
            if not no_save:
                file_id = "001"
                from docmirror.server.edition_outputs import write_outputs

                _saved_task_id, written = write_outputs(
                    result,
                    output_dir,
                    file_path=str(path),
                    file_id=file_id,
                    task_id=run_id,
                    overwrite=overwrite,
                    on_progress=bus.emit,
                    include_mirror=all_outputs,
                    include_manifest=all_outputs,
                )
                saved_path = written.get("mirror") or written.get("community")

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
            extracted_text = result.raw_text or result.full_text
            table.add_row("Extracted Text", f"{len(extracted_text)} chars")
            table.add_row("Structured Text", f"{len(result.full_text)} chars")
            table.add_row("Time Elapsed", f"{wall_elapsed_ms:.0f} ms")

            # Wall-clock breakdown (CLI-02)
            _extraction_ms = int((_extraction_end - _wall_start) * 1000)
            _build_ms = int(max(0, wall_elapsed_ms - _extraction_ms))
            table.add_row("Extraction", f"{_extraction_ms:,} ms")
            if _build_ms > 10:
                table.add_row("Output Build", f"{_build_ms:,} ms")

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
            console.print("[cyan]https://github.com/valuemapglobal/DocMirror/issues[/cyan]")

        # Display edition summaries (already written inside progress context)
        if not no_save and saved_path:
            label = "Mirror" if "mirror" in written else "Community output"
            console.print(f"[bold blue]\U0001f4be {label} saved to:[/bold blue] [white]{saved_path}[/white]")
            _show_community_review_summary(written.get("community"))

    except Exception as e:
        console.print(f"[bold red]Critical Error:[/bold red] {_safe_str(str(e))}")


def _save_outputs(
    result,
    path: Path,
    output_dir: Path,
    task_id: str | None = None,
    overwrite: bool = False,
    all_outputs: bool = False,
) -> str:
    """Save the fixed delivery projections to a timestamped subdirectory.

    Returns task_id (directory name).
    """
    from docmirror.server.edition_outputs import write_outputs

    task_id, _written = write_outputs(
        result,
        output_dir,
        file_path=str(path),
        file_id="001",
        task_id=task_id,
        overwrite=overwrite,
        include_mirror=all_outputs,
        include_manifest=all_outputs,
    )
    return task_id


def main() -> None:
    # ── Subcommand dispatch ──
    import sys as _sys

    if len(_sys.argv) > 1 and _sys.argv[1] == "mcp":
        import argparse as _ap

        from docmirror.server.mcp import run_sse, run_stdio

        _p = _ap.ArgumentParser(
            prog="docmirror mcp", description="Start the DocMirror MCP (Model Context Protocol) server"
        )
        _p.add_argument(
            "--transport",
            choices=["stdio", "sse"],
            default="stdio",
            help="Transport protocol (default: stdio). SSE allows HTTP clients.",
        )
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
    from docmirror import __version__

    parser.add_argument("-v", "--version", action="version", version=f"DocMirror {__version__}")
    parser.add_argument("file", nargs="?", help="Path to a document, directory, or glob")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to save parse results (default: ./output)",
    )
    parser.add_argument("--no-save", action="store_true", help="Do not save result to disk")
    parser.add_argument(
        "-all",
        "--all",
        dest="all_outputs",
        action="store_true",
        help="Also write the diagnostic Mirror JSON and manifest",
    )
    parser.add_argument("--pages", "-p", default=None, help="Page ranges, 1-based: 1-3,8,10-")
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
        "--ocr-correction",
        default="safe",
        choices=["off", "safe", "suggest"],
        help="Deterministic OCR correction policy",
    )
    parser.add_argument("--ocr-language", default=None, help="ISO 639 OCR language hint, for example zh or en")
    parser.add_argument("--ocr-country", default=None, help="ISO country hint, for example CN or US")
    parser.add_argument("--ocr-locale", default=None, help="OCR locale hint, for example zh-CN")
    parser.add_argument(
        "--ocr-correction-pack",
        action="append",
        default=[],
        help="Enable a correction pack by id; can be repeated",
    )
    parser.add_argument(
        "--page-split",
        default="auto",
        choices=["auto", "off", "force"],
        help="Split scanned two-page spreads before OCR",
    )
    parser.add_argument("--doc-type", "-t", default=None, help="Manual document type")
    parser.add_argument(
        "--doc-type-policy",
        default="prefer",
        choices=["prefer", "force"],
        help="How strongly to apply --doc-type",
    )
    parser.add_argument("--recursive", "-r", action="store_true", help="Recursively parse directory/glob inputs")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="SUBSTR",
        help="Skip files whose path contains SUBSTR (e.g. --exclude ICBC); can be repeated",
    )
    parser.add_argument("--include-ext", default=None, help="Comma-separated extensions to include in batch mode")
    parser.add_argument("--authors", action="store_true", help="Show contributors and authors")
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("--verbose", action="store_true", help="Show detailed pipeline logs")
    verbosity.add_argument("--quiet", "-q", action="store_true", help="Suppress informational pipeline logs")
    parser.add_argument(
        "--overwrite", action="store_true", help="Allow overwriting an explicit --run-id output directory"
    )
    parser.add_argument("--run-id", default=None, help="Explicit run/task id for output directory")
    # --slm flag removed in v1.1 — superseded by LlmDocumentRestorer

    args = parser.parse_args()
    resolved_log_level = "error" if args.quiet else ("debug" if args.verbose else "info")
    logging.basicConfig(level=getattr(logging, resolved_log_level.upper(), logging.INFO))
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
        from docmirror.input.entry.options import normalize_parse_policy

        policy = normalize_parse_policy(
            pages=args.pages,
            max_pages=args.max_pages,
            mode=args.mode,
            doc_type=args.doc_type,
            doc_type_policy=args.doc_type_policy,
            doc_type_hint=None,
            ocr=args.ocr,
            ocr_correction=args.ocr_correction,
            ocr_language=args.ocr_language,
            ocr_country=args.ocr_country,
            ocr_locale=args.ocr_locale,
            ocr_correction_packs=args.ocr_correction_pack,
            page_split=args.page_split,
        )
        _cpu_count = multiprocessing.cpu_count()
        _budget = resolve_worker_budget(args.workers, file_count=len(files), cpu_count=_cpu_count)
        _semaphore = asyncio.Semaphore(_budget.file_workers)
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
                    from docmirror.input.entry.factory import PerceiveOptions
                    from docmirror.input.pipeline import perceive_document

                    path = fp.resolve()
                    result = await perceive_document(
                        path,
                        PerceiveOptions(policy=policy, max_workers=_budget.page_workers_per_file),
                    )

                    # Handle both MirrorResult (new) and PerceptionResult (raw fallback)
                    if hasattr(result, "to_dict"):
                        vn_data = result.to_dict()
                        success = len(vn_data.get("pages", [])) > 0
                        doctype = (vn_data.get("document", {}) or {}).get("document_type", "unknown")
                        pages = len(vn_data.get("pages", []))
                        text_len = sum(
                            len(str(a.get("text", ""))) for a in vn_data.get("evidence", {}).get("text_atoms", [])
                        )
                    else:
                        vn_data = result.to_mirror_json_vnext(source_filename=str(path))
                        success = result.success if hasattr(result, "success") else True
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
                        _save_outputs(
                            result,
                            path,
                            args.output_dir,
                            overwrite=args.overwrite,
                            all_outputs=args.all_outputs,
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
                args.output_dir,
                args.no_save,
                pages=args.pages,
                max_pages=args.max_pages,
                workers=args.workers,
                mode=args.mode,
                doc_type=args.doc_type,
                doc_type_policy=args.doc_type_policy,
                doc_type_hint=None,
                ocr=args.ocr,
                ocr_correction=args.ocr_correction,
                ocr_language=args.ocr_language,
                ocr_country=args.ocr_country,
                ocr_locale=args.ocr_locale,
                ocr_correction_packs=args.ocr_correction_pack,
                page_split=args.page_split,
                run_id=args.run_id,
                overwrite=args.overwrite,
                all_outputs=args.all_outputs,
            )
        )


if __name__ == "__main__":
    main()
