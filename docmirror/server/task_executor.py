# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persistent execution helpers for the DocMirror REST Task API."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import ParsePolicy, normalize_parse_policy
from docmirror.runtime.ledger import EventLedger, build_manifest_v2
from docmirror.sdk.integration.request import ParseRequest
from docmirror.server.edition_outputs import write_outputs
from docmirror.server.task_result import TaskResult, task_result_from_manifest

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
    *,
    parse_policy: dict[str, Any] | None = None,
    max_workers: int | None = None,
    worker_budget: dict[str, int] | None = None,
) -> Path:
    """Create the durable manifest before execution starts."""
    task_dir = task_directory(task_id, output_root=output_root)
    task_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = task_dir / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"task already exists: {task_id}")
    manifest = build_manifest_v2(
        task_id,
        status="running",
        stage="queued",
        inputs=inputs,
        parse_policy=parse_policy,
        runtime_control={
            "worker_budget": worker_budget or ({"page_workers_per_file": max_workers} if max_workers else {})
        },
        entry="rest",
    )
    EventLedger(task_dir).write_manifest(manifest)
    return manifest_path


def read_task_manifest(task_id: str, *, output_root: Path | None = None) -> dict[str, Any]:
    """Load a task manifest, returning an empty dict when it does not exist."""
    task_dir = task_directory(task_id, output_root=output_root)
    return EventLedger(task_dir).read_manifest()


async def execute_parse_task(
    request: ParseRequest,
    *,
    output_root: Path,
    task_id: str,
    timeout_s: float = 300.0,
) -> TaskResult:
    """Parse one or more files and atomically publish a terminal manifest.

    Each batch member owns an isolated artifact directory so markdown,
    evidence and visual-debug filenames cannot collide. A failure in one
    member never discards successful members.
    """
    task_dir = task_directory(task_id, output_root=output_root)
    ledger = EventLedger(task_dir)
    manifest = ledger.read_manifest()
    if manifest.get("status") in _TERMINAL_STATUSES:
        return task_result_from_manifest(task_dir / "manifest.json")

    if not request.inputs:
        raise ValueError("ParseRequest.inputs must contain at least one document")

    policy = _policy_from_request(request)
    from docmirror.configs.runtime.performance import resolve_worker_budget

    budget = resolve_worker_budget(request.workers, file_count=len(request.inputs))
    files = _materialize_inputs(request, task_dir)
    file_semaphore = asyncio.Semaphore(budget.file_workers)
    if not manifest:
        initialize_task_manifest(
            output_root,
            task_id,
            [_input_entry(file_id, file_name) for _path, file_name, file_id in files],
            parse_policy=policy.to_dict(),
            max_workers=budget.page_workers_per_file,
            worker_budget=_worker_budget_dict(budget),
        )
        manifest = ledger.read_manifest()

    manifest["stage"] = "parsing"
    manifest["progress"] = _progress(total=len(files), completed=0, failed=0, running=len(files))
    ledger.write_manifest(manifest)

    batch = len(files) > 1
    input_entries = list(manifest.get("inputs") or [])

    try:
        from docmirror.ocr.vlm_gateway import _gateway

        _gateway.collect_fallbacks()
    except Exception:
        _gateway = None

    async def process_one(index: int, source_path: Path, original_name: str, file_id: str) -> dict[str, Any]:
        entry = (
            input_entries[index - 1]
            if index - 1 < len(input_entries)
            else {
                "file_id": file_id,
                "file_name": original_name,
            }
        )
        entry.update({"file_id": file_id, "file_name": original_name, "status": "running"})
        try:
            async with file_semaphore:
                result = await asyncio.wait_for(
                    perceive_document(
                        source_path,
                        PerceiveOptions(policy=policy, max_workers=budget.page_workers_per_file),
                    ),
                    timeout=timeout_s,
                )
            artifact_dir = task_dir / "files" / file_id if batch else task_dir
            _written_task_id, written = write_outputs(
                result,
                output_root,
                file_path=str(source_path),
                file_id=file_id,
                task_id=task_id,
                overwrite=True,
                artifact_dir=artifact_dir,
                include_mirror=False,
                include_manifest=True,
            )
            child_manifest = EventLedger(artifact_dir).read_manifest()
            artifacts = dict(child_manifest.get("artifacts") or {})
            if not artifacts:
                artifacts = {name: path.name for name, path in written.items()}
            task_artifacts = {
                name: relative
                for name, relative in _parent_artifact_map(
                    task_dir=task_dir,
                    artifact_dir=artifact_dir,
                    artifacts=artifacts,
                    file_id=file_id,
                    batch=batch,
                ).items()
                if not name.endswith("mirror") and name != "mirror"
            }
            input_artifacts = {
                name: relative
                for name, relative in _input_artifact_map(
                    task_dir=task_dir,
                    artifact_dir=artifact_dir,
                    artifacts=artifacts,
                ).items()
                if name != "mirror"
            }
            public_availability = {
                name: value
                for name, value in (child_manifest.get("edition_availability") or {}).items()
                if name != "mirror"
            }
            from docmirror.evidence.quality import build_quality_summary

            quality_summary = build_quality_summary(result)
            document_type = str(getattr(getattr(result, "entities", None), "document_type", "") or "generic")
            entry.update(
                {
                    "status": "success",
                    "document_type": document_type,
                    "page_count": int(getattr(result, "page_count", 0) or 0),
                    "quality_summary": quality_summary,
                    "artifacts": input_artifacts,
                    "edition_availability": public_availability,
                    "errors": [],
                }
            )
            return {
                "file_id": file_id,
                "file_name": original_name,
                "status": "success",
                "artifacts": task_artifacts,
                "edition_availability": public_availability,
                "mirror_completeness": child_manifest.get("mirror_completeness") or {},
                "quality_summary": quality_summary,
            }
        except asyncio.TimeoutError:
            error = {
                "code": "TIMEOUT",
                "message": f"parse exceeded {timeout_s:g}s timeout",
                "recoverable": True,
            }
            entry.update({"status": "failed", "artifacts": {}, "edition_availability": {}, "errors": [error]})
            return {
                "file_id": file_id,
                "file_name": original_name,
                "status": "failed",
                "error": error,
            }
        except Exception as exc:
            error = {
                "code": "PARSER_ERROR",
                "message": str(exc),
                "recoverable": False,
            }
            entry.update({"status": "failed", "artifacts": {}, "edition_availability": {}, "errors": [error]})
            return {
                "file_id": file_id,
                "file_name": original_name,
                "status": "failed",
                "error": error,
            }
        finally:
            _cleanup_managed_input(source_path, task_dir)

    outcomes = await asyncio.gather(
        *(process_one(index, path, name, file_id) for index, (path, name, file_id) in enumerate(files, start=1))
    )
    successes = [outcome for outcome in outcomes if outcome["status"] == "success"]
    failures = [outcome for outcome in outcomes if outcome["status"] == "failed"]
    status = "partial" if successes and failures else ("success" if successes else "failed")

    artifacts: dict[str, str] = {}
    edition_availability: dict[str, Any] = {}
    mirror_completeness: dict[str, Any] = {}
    quality_summary: dict[str, Any] = {}
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
        if outcome.get("quality_summary"):
            if batch:
                quality_summary[outcome["file_id"]] = outcome["quality_summary"]
            else:
                quality_summary = outcome["quality_summary"]
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
            "quality_summary": quality_summary,
            "fallbacks": fallbacks,
            "errors": errors,
        }
    )
    ledger.write_manifest(manifest)
    return task_result_from_manifest(task_dir / "manifest.json")


def _policy_from_request(request: ParseRequest) -> ParsePolicy:
    return normalize_parse_policy(
        pages=request.pages,
        max_pages=request.max_pages,
        mode=request.mode,
        doc_type=request.doc_type,
        doc_type_policy=request.doc_type_policy,
        ocr=request.ocr,
        ocr_correction=request.ocr_correction,
        ocr_language=request.ocr_language,
        ocr_country=request.ocr_country,
        ocr_locale=request.ocr_locale,
        ocr_correction_packs=request.ocr_correction_packs,
        page_split=request.page_split,
    )


def _materialize_inputs(request: ParseRequest, task_dir: Path) -> list[tuple[Path, str, str]]:
    files: list[tuple[Path, str, str]] = []
    managed_root = task_dir / "inputs"
    seen_file_ids: set[str] = set()
    for index, item in enumerate(request.inputs, start=1):
        file_id = item.file_id or f"{index:03d}"
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", file_id):
            raise ValueError(f"Invalid file_id: {file_id!r}")
        if file_id in seen_file_ids:
            raise ValueError(f"Duplicate file_id: {file_id!r}")
        seen_file_ids.add(file_id)
        file_name = item.file_name or "document"
        if item.file_path:
            path = Path(item.file_path).resolve()
        elif item.data is not None:
            managed_root.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file_name).name).strip("._") or "document.bin"
            path = managed_root / f"{file_id}_{safe_name}"
            path.write_bytes(item.data)
        else:
            raise ValueError(f"Input {file_id} has neither file_path nor data")
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {path}")
        files.append((path, file_name, file_id))
    return files


def _cleanup_managed_input(source_path: Path, task_dir: Path) -> None:
    managed_root = (task_dir / "inputs").resolve()
    try:
        candidate = source_path.resolve()
        if candidate.is_relative_to(managed_root):
            candidate.unlink(missing_ok=True)
    except OSError:
        pass


def _input_entry(file_id: str, file_name: str) -> dict[str, Any]:
    return {"file_id": file_id, "file_name": file_name, "status": "queued"}


def _worker_budget_dict(budget: Any) -> dict[str, int]:
    return {
        "total": int(budget.total),
        "file_workers": int(budget.file_workers),
        "page_workers_per_file": int(budget.page_workers_per_file),
        "layout_workers": int(budget.layout_workers),
    }


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


def _input_artifact_map(
    *,
    task_dir: Path,
    artifact_dir: Path,
    artifacts: dict[str, Any],
) -> dict[str, str]:
    """Return role-keyed paths for one input, rooted at the parent task."""
    result: dict[str, str] = {}
    for role, relative in artifacts.items():
        candidate = artifact_dir / str(relative)
        try:
            result[str(role)] = str(candidate.resolve().relative_to(task_dir.resolve()))
        except ValueError:
            continue
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
    "task_directory",
    "task_output_root",
]
