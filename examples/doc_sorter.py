#!/usr/bin/env python3
"""
DocMirror Document Sorter (doc-sorter)
=======================================

Scans a target directory, parses each file with DocMirror,
classifies using SceneDetector, and moves files into Temp/{scene_name}/.

Usage:
    python examples/doc_sorter.py /path/to/target/directory
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docmirror.core.factory import perceive_document
from docmirror.core.classification.evidence_engine import _SCENE_KEYWORDS as CLASSIFICATION_CATEGORIES

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

console = Console()

# ── Constants ──
SKIP_NAMES: set[str] = {".DS_Store", ".gitkeep", "Thumbs.db", ".gitignore"}
TEMP_DIR_NAME = "Temp"
LOG_FILE_NAME = "_sorted_log.json"


# ── Utility functions ──

def discover_files(root: Path) -> list[Path]:
    """Recursively collect all files under root (excludes Temp dir and skip names)."""
    files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if TEMP_DIR_NAME in p.parts:
            continue
        if p.is_file() and p.name not in SKIP_NAMES:
            files.append(p)
    return files


def ensure_temp_structure(temp_dir: Path) -> None:
    """Create Temp subdirectories for all known scene types."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    for name in (CLASSIFICATION_CATEGORIES or {}):
        (temp_dir / name).mkdir(parents=True, exist_ok=True)


def rename_and_move(file_path: Path, target_dir: Path, scene: str, entities) -> Path:
    """Rename file using extracted info, then move into target_dir."""
    # Build name parts from entities
    name = ""
    if hasattr(entities, "subject_name") and entities.subject_name:
        name = entities.subject_name.strip()
    org = ""
    if hasattr(entities, "organization") and entities.organization:
        org = entities.organization.strip()
    date_str = ""
    if hasattr(entities, "document_date") and entities.document_date:
        raw = entities.document_date.strip()
        if raw:
            date_str = raw.replace("/", "").replace("-", "").replace("年", "").replace("月", "").replace("日", "")[:8]

    type_name = scene.replace("_", " ").title()
    parts = [p for p in [name, type_name, org, date_str] if p]
    if not parts:
        base_name = file_path.stem
        parts = [base_name, type_name]

    safe = re.sub(r'[\\/:*?"<>|]', "_", "_".join(parts)).strip()[:100]
    new_name = f"{safe}{file_path.suffix}"

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / new_name
    counter = 1
    while target_path.exists():
        target_path = target_dir / f"{target_path.stem}_{counter}{file_path.suffix}"
        counter += 1

    shutil.move(str(file_path), str(target_path))
    return target_path


async def process_file(file_path: Path, temp_dir: Path) -> dict:
    """Parse a single file, classify, rename and move."""
    rel_path = file_path.relative_to(temp_dir.parent)

    try:
        result = await perceive_document(str(file_path))
    except Exception as e:
        return {"file": str(rel_path), "status": "failed", "domain": None, "error": str(e)}

    scene = getattr(result.entities, "document_type", None)
    if scene and scene not in ("unknown", "other", "DocumentType.OTHER", ""):
        new_path = rename_and_move(file_path, temp_dir / scene, scene, result.entities)
        return {
            "file": str(rel_path),
            "status": "matched",
            "domain": scene,
            "target": str(new_path.relative_to(temp_dir.parent)),
        }
    else:
        return {"file": str(rel_path), "status": "unmatched", "domain": None, "error": None}


async def sort_documents(target_dir: Path) -> None:
    """Main entry: discover, process, and sort all documents."""
    target_dir = target_dir.resolve()
    if not target_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Target directory not found: {target_dir}")
        sys.exit(1)

    files = discover_files(target_dir)
    if not files:
        console.print(f"[yellow]No files found outside[/yellow] [bold]Temp/[/bold] [yellow]in[/yellow] {target_dir}")
        return

    temp_dir = target_dir / TEMP_DIR_NAME
    ensure_temp_structure(temp_dir)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )

    progress.start()
    task = progress.add_task(f"[cyan]Processing {len(files)} file(s)...", total=len(files))

    records: list[dict] = []
    matched_count = 0
    unmatched_count = 0
    failed_count = 0

    for file_path in files:
        rel_path = file_path.relative_to(target_dir)
        progress.update(task, description=f"[dim]{rel_path}[/dim]")

        record = await process_file(file_path, temp_dir)
        records.append(record)

        if record["status"] == "matched":
            matched_count += 1
            progress.update(task, description=f"[green]\u2713[/green] {record['file']} \u2192 {record.get('target', '?')}")
        elif record["status"] == "unmatched":
            unmatched_count += 1
            progress.update(task, description=f"[yellow]?[/yellow] {record['file']} (unmatched)")
        else:
            failed_count += 1
            progress.update(task, description=f"[red]\u2717[/red] {record['file']} (failed)")

        progress.advance(task)

    progress.stop()
    console.print()

    # Save log
    summary = {
        "executed_at": datetime.now().isoformat(),
        "target_directory": str(target_dir),
        "total_processed": len(records),
        "matched": matched_count,
        "unmatched": unmatched_count,
        "failed": failed_count,
        "records": records,
    }
    log_path = temp_dir / LOG_FILE_NAME
    history: list[dict] = []
    if log_path.exists():
        try:
            history = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    history.append(summary)
    log_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    table = Table(title="Sorting Results", border_style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Total files", str(len(records)))
    table.add_row("[green]Matched[/green]", str(matched_count))
    table.add_row("[yellow]Unmatched[/yellow]", str(unmatched_count))
    table.add_row("[red]Failed[/red]", str(failed_count))
    console.print(table)
    console.print(f"[dim]\U0001f4c4 Log saved to {log_path.relative_to(target_dir)}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DocMirror Document Sorter — parse, sort and rename documents by type"
    )
    parser.add_argument("target_dir", help="Target directory containing documents to sort")
    args = parser.parse_args()

    asyncio.run(sort_documents(Path(args.target_dir)))


if __name__ == "__main__":
    main()
