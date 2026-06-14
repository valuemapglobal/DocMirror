# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""CLI entry point for DocMirror document parsing engine.

Provides single-file and batch-directory parsing with rich progress
display, multiple output formats, and result persistence.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import multiprocessing
import os
import time
import traceback
import uuid
from datetime import datetime as _dt
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


def discover_files(root: Path) -> list[Path]:
    """Recursively collect all files under *root* (excludes SKIP_NAMES)."""
    files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name not in SKIP_NAMES:
            files.append(p)
    return files


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


def save_result(result_dict: dict, source_path: Path, output_dir: Path) -> tuple[Path, str]:
    """Save parse result as JSON under a timestamped subdirectory.
    
    Returns (saved_file_path, task_id) where task_id is the directory name
    (e.g. "20260613_084225_07e4").
    """
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:4]
    task_id = f"{ts}_{short_id}"
    task_dir = output_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    output_file = task_dir / "001_mirror.json"
    output_file.write_text(json.dumps(result_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_file, task_id


async def parse_document(
    file_path: str,
    format_out: str,
    output_dir: Path,
    no_save: bool,
    skip_cache: bool = False,
    include_text: bool = False,
    mirror_level: str = "standard",
) -> None:
    from docmirror.core.entry.factory import perceive_document
    from docmirror.core.entry.factory import PerceiveOptions

    path = Path(file_path).resolve()
    if not path.exists():
        console.print(f"[bold red]Error[/bold red]: File not found: {file_path}")
        return
    if path.is_dir():
        console.print(
            f"[bold red]Error[/bold red]: Path is a directory (use it as the batch root to parse all files inside): {path}"
        )
        return

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
            result = await perceive_document(path, PerceiveOptions(skip_cache=skip_cache))
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
        api_dict = result.to_api_dict(include_text=include_text, mirror_level=mirror_level)

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
            saved_path, task_id = save_result(api_dict, path, output_dir)
            file_id = "001"
            document_id = f"doc_{task_id}_{file_id}"

            # Inject task/file/document IDs into the mirror output
            api_dict["document_id"] = document_id
            api_dict.setdefault("metadata", {})
            api_dict["metadata"]["task_id"] = task_id
            api_dict["metadata"]["file_id"] = file_id
            # Rewrite with IDs
            saved_path.write_text(json.dumps(api_dict, ensure_ascii=False, indent=2), encoding="utf-8")

            # Generate community edition output with IDs
            community_schema = _build_community_output(result, result.full_text or "")
            if community_schema:
                community_schema.setdefault("document", {})["document_id"] = document_id
                community_schema["metadata"]["task_id"] = task_id
                community_schema["metadata"]["file_id"] = file_id
                community_path = saved_path.parent / f"{file_id}_community.json"
                community_path.write_text(json.dumps(community_schema, ensure_ascii=False, indent=2), encoding="utf-8")
                rows = community_schema.get("data", {}).get("summary", {}).get("total_rows", 0)
                summary = _format_community_summary(community_schema)
                console.print(f"[cyan]📦 Community:[/cyan] {community_path.name}  → {summary}")

            # Generate enterprise edition output (docmirror-enterprise)
            enterprise_schema = _build_extended_output(result, "enterprise", result.full_text or "", str(path))
            if enterprise_schema:
                enterprise_schema.setdefault("document", {})["document_id"] = document_id
                enterprise_schema["metadata"]["task_id"] = task_id
                enterprise_schema["metadata"]["file_id"] = file_id
                enterprise_path = saved_path.parent / f"{file_id}_enterprise.json"
                enterprise_path.write_text(json.dumps(enterprise_schema, ensure_ascii=False, indent=2), encoding="utf-8")
                rows = enterprise_schema.get("data", {}).get("summary", {}).get("total_rows", 0)
                doctype = enterprise_schema.get("document", {}).get("document_type", "unknown")
                console.print(f"[cyan]📦 Enterprise:[/cyan] {enterprise_path.name}  → {doctype} ({rows} rows)")

            # Generate finance edition output (docmirror-finance)
            finance_schema = _build_extended_output(result, "finance", result.full_text or "", str(path))
            if finance_schema:
                finance_schema.setdefault("document", {})["document_id"] = document_id
                finance_schema["metadata"]["task_id"] = task_id
                finance_schema["metadata"]["file_id"] = file_id
                finance_path = saved_path.parent / f"{file_id}_finance.json"
                finance_path.write_text(json.dumps(finance_schema, ensure_ascii=False, indent=2), encoding="utf-8")
                rows = finance_schema.get("data", {}).get("summary", {}).get("total_rows", 0)
                doctype = finance_schema.get("document", {}).get("document_type", "unknown")
                console.print(f"[cyan]📦 Finance:[/cyan] {finance_path.name}  → {doctype} ({rows} rows)")

            _print_entitlement_warnings(enterprise_schema, finance_schema)

            console.print(f"[bold blue]\U0001f4be Mirror saved to:[/bold blue] [white]{saved_path}[/white]")

    except Exception as e:
        console.print(f"[bold red]Critical Error:[/bold red] {_safe_str(str(e))}")





def _save_multi_edition(result, api_dict: dict, path: Path, output_dir: Path, include_text: bool = False) -> str:
    """Save mirror + community + enterprise + finance outputs to a timestamped subdirectory.
    
    Returns task_id (directory name).
    """
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:4]
    task_id = f"{ts}_{short_id}"
    task_dir = output_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    
    file_id = "001"
    document_id = f"doc_{task_id}_{file_id}"
    
    # Inject IDs into mirror
    api_dict["document_id"] = document_id
    api_dict.setdefault("metadata", {})
    api_dict["metadata"]["task_id"] = task_id
    api_dict["metadata"]["file_id"] = file_id
    
    saved_path = task_dir / "001_mirror.json"
    saved_path.write_text(json.dumps(api_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # Community edition
    community_schema = _build_community_output(result, getattr(result, "full_text", "") or "")
    if community_schema:
        community_schema.setdefault("document", {})["document_id"] = document_id
        community_schema["metadata"]["task_id"] = task_id
        community_schema["metadata"]["file_id"] = file_id
        community_path = task_dir / f"{file_id}_community.json"
        community_path.write_text(json.dumps(community_schema, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # Enterprise edition
    enterprise_schema = _build_extended_output(result, "enterprise", getattr(result, "full_text", "") or "", str(path))
    if enterprise_schema:
        enterprise_schema.setdefault("document", {})["document_id"] = document_id
        enterprise_schema["metadata"]["task_id"] = task_id
        enterprise_schema["metadata"]["file_id"] = file_id
        enterprise_path = task_dir / f"{file_id}_enterprise.json"
        enterprise_path.write_text(json.dumps(enterprise_schema, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # Finance edition
    finance_schema = _build_extended_output(result, "finance", getattr(result, "full_text", "") or "", str(path))
    if finance_schema:
        finance_schema.setdefault("document", {})["document_id"] = document_id
        finance_schema["metadata"]["task_id"] = task_id
        finance_schema["metadata"]["file_id"] = file_id
        finance_path = task_dir / f"{file_id}_finance.json"
        finance_path.write_text(json.dumps(finance_schema, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return task_id


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
    parser.add_argument(
        "file", nargs="?", help="Path to a document or a directory (recursively parse all files under it)"
    )
    parser.add_argument("--format", default="markdown", choices=["markdown", "json", "text"], help="Output format")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to save parse results (default: ./output)",
    )
    parser.add_argument("--no-save", action="store_true", help="Do not save result to disk")
    parser.add_argument("--skip-cache", action="store_true", help="Skip cache and force a full re-parse")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="SUBSTR",
        help="Skip files whose path contains SUBSTR (e.g. --exclude 工商银行); can be repeated",
    )
    parser.add_argument("--authors", action="store_true", help="Show contributors and authors")
    parser.add_argument("--include-text", action="store_true", help="Include full markdown text in output")
    parser.add_argument(
        "--mirror-level",
        default=DEFAULT_MIRROR_LEVEL,
        choices=["standard", "slim", "forensic"],
        help="Mirror output level: standard (physical+logical), slim (logical only), forensic (physical only)",
    )
    parser.add_argument("--slm", action="store_true", help="[Experimental] Enable pure CPU Small Language Model (SLM) semantic KV extraction")

    args = parser.parse_args()

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
    path = Path(args.file).resolve()
    if not path.exists():
        console.print(f"[bold red]Error[/bold red]: Path not found: {path}")
        return

    if path.is_dir():
        files = discover_files(path)
        if args.exclude:
            excluded = [f for f in files if any(pat in str(f) for pat in args.exclude)]
            files = [f for f in files if not any(pat in str(f) for pat in args.exclude)]
            if excluded:
                console.print(f"[dim]Excluding {len(excluded)} file(s) matching: {', '.join(args.exclude)}[/dim]")
        if not files:
            console.print(f"[bold yellow]No files found under[/bold yellow] {path}")
            return
        console.print(f"[bold cyan]Batch mode:[/bold cyan] {len(files)} file(s) under [white]{path}[/white]\n")

        _cpu_count = multiprocessing.cpu_count()
        _max_concurrency = max(4, _cpu_count * 2)
        _semaphore = asyncio.Semaphore(_max_concurrency)
        console.print(f"[dim]🔥 File-level concurrency: {_max_concurrency} ({_cpu_count} CPU cores)[/dim]\n")

        async def _process_one(fp: Path, idx: int, total: int):
            """Parse a single file in batch mode (no Rich Progress per file)."""
            async with _semaphore:
                name = fp.name
                console.print(f"[bold cyan][{idx}/{total}][/bold cyan] ⏳ {name}")
                try:
                    from docmirror.core.entry.factory import perceive_document, PerceiveOptions
                    path = fp.resolve()
                    result = await perceive_document(path, PerceiveOptions(skip_cache=args.skip_cache))

                    api_dict = result.to_api_dict(
                        include_text=args.include_text,
                        mirror_level=args.mirror_level,
                    )
                    if result.success:
                        doctype = getattr(result.entities, "document_type", "unknown")
                        pages = getattr(result, "page_count", 0)
                        text_len = len(getattr(result, "full_text", ""))
                        console.print(f"[bold cyan][{idx}/{total}][/bold cyan] ✅ {name}  → {doctype} ({pages}p, {text_len} chars)")
                    else:
                        console.print(f"[bold yellow][{idx}/{total}][/bold yellow] ⚠️ {name}  → parse returned failure")

                    if not args.no_save:
                        _save_multi_edition(result, api_dict, path, args.output_dir, args.include_text)
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
                args.file,
                args.format,
                args.output_dir,
                args.no_save,
                args.skip_cache,
                args.include_text,
                args.mirror_level,
            )
        )


if __name__ == "__main__":
    main()
