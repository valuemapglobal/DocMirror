# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persistent execution helpers for the DocMirror REST Task API."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.runtime.ledger import EventLedger, build_manifest_v2
from docmirror.server.edition_outputs import write_four_files

_TERMINAL_STATUSES = {"success", "partial", "failed"}


def task_output_root() -> Path:
    """Resolve the task store at request time so test/deployment env changes apply."""
    configured = os.environ.get("DOCMIRROR_TASK_OUTPUT_DIR") or os.environ.get("DOCMIRROR_TASK_DIR") or "output/tasks"
    return Path(configured).resolve()


def task_directory(task_id: str, *, output_root: Path | None = None) -> Path:
    """Return a validated task directory beneath the configured task store."""
    if not task_id or any(part in {"", ".", ".."} for part in Path(task_id).parts) or Path(task_id).is_absolute():
        raise ValueError("invalid task_id")
    root = (output_root or task_output_root()).resolve()
    candidate = (root / task_id).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("invalid task_id")
    return candidate


def initialize_task_manifest(
    output_root: Path,
    task_id: str,
    inputs: list[dict[str, Any]],
    formats: list[str] | tuple[str, ...] | None = None,
    editions: list[str] | tuple[str, ...] | None = None,
    *,
    runtime_control: dict[str, Any] | None = None,
) -> Path:
    """Create the durable manifest before execution starts."""
    task_dir = task_directory(task_id, output_root=output_root)
    task_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = task_dir / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"task already exists: {task_id}")
    if editions is None:
        from docmirror.framework.edition_defaults import default_editions

        editions = default_editions()

    manifest = build_manifest_v2(
        task_id,
        status="running",
        stage="queued",
        inputs=inputs,
        formats=list(formats or ["json"]),
        editions=list(editions),
        runtime_control=runtime_control,
        entry="rest",
    )
    EventLedger(task_dir).write_manifest(manifest)
    return manifest_path


def read_task_manifest(task_id: str, *, output_root: Path | None = None) -> dict[str, Any]:
    """Load a task manifest, returning an empty dict when it does not exist."""
    task_dir = task_directory(task_id, output_root=output_root)
    return EventLedger(task_dir).read_manifest()


async def execute_parse_task(
    files: list[tuple[Path, str]],
    *,
    output_root: Path,
    task_id: str,
    control: Any,
    formats: tuple[str, ...] | list[str],
    editions: tuple[str, ...] | list[str],
    include_text: bool = False,
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """Parse one or more files and atomically publish a terminal manifest.

    Each batch member owns an isolated artifact directory so markdown,
    evidence and visual-debug filenames cannot collide. A failure in one
    member never discards successful members.
    """
    task_dir = task_directory(task_id, output_root=output_root)
    ledger = EventLedger(task_dir)
    manifest = ledger.read_manifest()
    if not manifest:
        raise FileNotFoundError(f"task manifest not found: {task_id}")
    if manifest.get("status") in _TERMINAL_STATUSES:
        return manifest

    manifest["stage"] = "parsing"
    manifest["progress"] = _progress(total=len(files), completed=0, failed=0, running=len(files))
    ledger.write_manifest(manifest)

    requested_formats = tuple(str(value) for value in formats)
    requested_editions = tuple(str(value) for value in editions)
    artifact_pack = any(value in {"markdown", "evidence"} for value in requested_formats)
    batch = len(files) > 1
    input_entries = list(manifest.get("inputs") or [])

    try:
        from docmirror.ocr.vlm_gateway import _gateway

        _gateway.collect_fallbacks()
    except Exception:
        _gateway = None

    async def process_one(index: int, source_path: Path, original_name: str) -> dict[str, Any]:
        file_id = f"{index:03d}"
        entry = (
            input_entries[index - 1]
            if index - 1 < len(input_entries)
            else {
                "file_id": file_id,
                "file_name": original_name,
            }
        )
        entry["status"] = "running"
        try:
            result = await asyncio.wait_for(
                perceive_document(source_path, PerceiveOptions(control=control)),
                timeout=timeout_s,
            )
            artifact_dir = task_dir / "files" / file_id if batch else task_dir
            _written_task_id, written = write_four_files(
                result,
                output_root,
                file_path=str(source_path),
                full_text=getattr(result, "full_text", "") or "",
                file_id=file_id,
                task_id=task_id,
                mirror_level=getattr(control.output, "mirror_level", "standard"),
                include_text=include_text,
                editions=requested_editions,
                overwrite=True,
                artifact_pack=artifact_pack,
                artifact_dir=artifact_dir,
            )
            child_manifest = EventLedger(artifact_dir).read_manifest() if artifact_pack else {}
            artifacts = dict(child_manifest.get("artifacts") or {})
            if not artifacts:
                artifacts = {name: path.name for name, path in written.items()}
            entry["status"] = "success"
            return {
                "file_id": file_id,
                "file_name": original_name,
                "status": "success",
                "artifacts": _parent_artifact_map(
                    task_dir=task_dir,
                    artifact_dir=artifact_dir,
                    artifacts=artifacts,
                    file_id=file_id,
                    batch=batch,
                ),
                "edition_availability": child_manifest.get("edition_availability") or {},
                "mirror_completeness": child_manifest.get("mirror_completeness") or {},
            }
        except asyncio.TimeoutError:
            entry["status"] = "failed"
            return {
                "file_id": file_id,
                "file_name": original_name,
                "status": "failed",
                "error": {
                    "code": "TIMEOUT",
                    "message": f"parse exceeded {timeout_s:g}s timeout",
                    "recoverable": True,
                },
            }
        except Exception as exc:
            entry["status"] = "failed"
            return {
                "file_id": file_id,
                "file_name": original_name,
                "status": "failed",
                "error": {
                    "code": "PARSER_ERROR",
                    "message": str(exc),
                    "recoverable": False,
                },
            }
        finally:
            source_path.unlink(missing_ok=True)

    outcomes = await asyncio.gather(
        *(process_one(index, path, name) for index, (path, name) in enumerate(files, start=1))
    )
    successes = [outcome for outcome in outcomes if outcome["status"] == "success"]
    failures = [outcome for outcome in outcomes if outcome["status"] == "failed"]
    status = "partial" if successes and failures else ("success" if successes else "failed")

    artifacts: dict[str, str] = {}
    edition_availability: dict[str, Any] = {}
    mirror_completeness: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    for outcome in outcomes:
        artifacts.update(outcome.get("artifacts") or {})
        if outcome.get("edition_availability"):
            if batch:
                edition_availability[outcome["file_id"]] = outcome["edition_availability"]
            else:
                edition_availability = outcome["edition_availability"]
        if outcome.get("mirror_completeness"):
            if batch:
                mirror_completeness[outcome["file_id"]] = outcome["mirror_completeness"]
            else:
                mirror_completeness = outcome["mirror_completeness"]
        if outcome.get("error"):
            errors.append(
                {
                    "file_id": outcome["file_id"],
                    "file_name": outcome["file_name"],
                    **outcome["error"],
                }
            )

    fallbacks = _gateway.collect_fallbacks() if _gateway is not None else []
    manifest.update(
        {
            "status": status,
            "stage": "completed",
            "progress": _progress(
                total=len(files),
                completed=len(successes),
                failed=len(failures),
                running=0,
            ),
            "inputs": input_entries,
            "artifacts": artifacts,
            "edition_availability": edition_availability,
            "mirror_completeness": mirror_completeness,
            "page_outcomes": outcomes,
            "fallbacks": fallbacks,
            "errors": errors,
        }
    )
    ledger.write_manifest(manifest)
    return manifest


async def run_batch_parse_task(
    files: list[tuple[Path, str]],
    output_root: Path,
    task_id: str,
    control: Any = None,
    include_text: bool = False,
) -> dict[str, Any]:
    """Backward-compatible wrapper over the durable Task API executor."""
    formats = tuple(getattr(getattr(control, "output", None), "formats", ("json",)))
    output_editions = getattr(getattr(control, "output", None), "editions", None)
    if output_editions is None:
        from docmirror.framework.edition_defaults import default_editions

        editions = default_editions()
    else:
        editions = tuple(output_editions)
    return await execute_parse_task(
        files,
        output_root=output_root,
        task_id=task_id,
        control=control,
        formats=formats,
        editions=editions,
        include_text=include_text,
    )


def _parent_artifact_map(
    *,
    task_dir: Path,
    artifact_dir: Path,
    artifacts: dict[str, Any],
    file_id: str,
    batch: bool,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, relative in artifacts.items():
        candidate = artifact_dir / str(relative)
        try:
            parent_relative = str(candidate.resolve().relative_to(task_dir.resolve()))
        except ValueError:
            continue
        key = f"{file_id}_{name}" if batch else str(name)
        result[key] = parent_relative
    return result


def _progress(*, total: int, completed: int, failed: int, running: int) -> dict[str, Any]:
    finished = completed + failed
    return {
        "total_units": total,
        "completed_units": completed,
        "failed_units": failed,
        "running_units": running,
        "percent": round(finished / max(total, 1) * 100.0, 2),
    }


__all__ = [
    "execute_parse_task",
    "initialize_task_manifest",
    "read_task_manifest",
    "run_batch_parse_task",
    "task_directory",
    "task_output_root",
]
