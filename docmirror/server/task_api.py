# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Durable REST Task API routes."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from docmirror.input.entry.options import normalize_parse_control
from docmirror.server.task_executor import (
    execute_parse_task,
    initialize_task_manifest,
    read_task_manifest,
    task_directory,
    task_output_root,
)

router = APIRouter(prefix="/v1/tasks", tags=["Tasks"])
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _verify_api_key(authorization: str | None) -> None:
    configured = os.environ.get("DOCMIRROR_API_KEY", "")
    if not configured:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token != configured:
        raise HTTPException(status_code=403, detail="Invalid API key")


@router.post("")
async def create_task(
    file: UploadFile = File(..., description="Document to parse"),
    wait: bool = Query(default=False, description="Wait for terminal task status"),
    formats: str = Query(default="json"),
    editions: str = Query(default="mirror,community"),
    mode: str = Query(default="auto", pattern="^(auto|fast|balanced|accurate|forensic)$"),
    pages: str | None = Query(default=None),
    max_pages: int | None = Query(default=None),
    workers: str | None = Query(default=None),
    include_text: bool = Query(default=False),
    authorization: str | None = Header(default=None),
):
    """Create a durable single-file parse task."""
    _verify_api_key(authorization)
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided in upload")
    control = _parse_control(
        formats=formats,
        editions=editions,
        mode=mode,
        pages=pages,
        max_pages=max_pages,
        workers=workers,
        include_text=include_text,
    )
    task_id = _new_task_id()
    output_root = task_output_root()
    task_dir = task_directory(task_id, output_root=output_root)
    stored = await _store_uploads(task_dir, [(file, "001")])
    initialize_task_manifest(
        output_root,
        task_id,
        [_input_entry("001", file.filename)],
        formats=control.output.formats,
        editions=control.output.editions,
        runtime_control=control.to_dict(),
    )
    return await _start_or_wait(
        files=[(stored[0], file.filename)],
        output_root=output_root,
        task_id=task_id,
        control=control,
        wait=wait,
        include_text=include_text,
    )


@router.post("/batch")
async def create_batch_task(
    files: list[UploadFile] = File(..., description="Documents to parse"),
    wait: bool = Query(default=False, description="Wait for terminal task status"),
    formats: str = Query(default="json"),
    editions: str = Query(default="mirror,community"),
    mode: str = Query(default="auto", pattern="^(auto|fast|balanced|accurate|forensic)$"),
    pages: str | None = Query(default=None),
    max_pages: int | None = Query(default=None),
    workers: str | None = Query(default=None),
    include_text: bool = Query(default=False),
    authorization: str | None = Header(default=None),
):
    """Create a batch task with per-file partial-failure isolation."""
    _verify_api_key(authorization)
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if any(not upload.filename for upload in files):
        raise HTTPException(status_code=400, detail="Every upload must have a filename")
    control = _parse_control(
        formats=formats,
        editions=editions,
        mode=mode,
        pages=pages,
        max_pages=max_pages,
        workers=workers,
        include_text=include_text,
    )
    task_id = _new_task_id()
    output_root = task_output_root()
    task_dir = task_directory(task_id, output_root=output_root)
    upload_specs = [(upload, f"{index:03d}") for index, upload in enumerate(files, start=1)]
    stored = await _store_uploads(task_dir, upload_specs)
    inputs = [_input_entry(f"{index:03d}", upload.filename or "") for index, upload in enumerate(files, start=1)]
    initialize_task_manifest(
        output_root,
        task_id,
        inputs,
        formats=control.output.formats,
        editions=control.output.editions,
        runtime_control=control.to_dict(),
    )
    return await _start_or_wait(
        files=[(path, upload.filename or "") for path, upload in zip(stored, files, strict=True)],
        output_root=output_root,
        task_id=task_id,
        control=control,
        wait=wait,
        include_text=include_text,
    )


@router.get("/{task_id}/artifacts")
async def list_task_artifacts(
    task_id: str,
    authorization: str | None = Header(default=None),
):
    """List stable artifact keys and task-relative paths."""
    _verify_api_key(authorization)
    manifest = _manifest_or_404(task_id)
    return {"task_id": task_id, "status": manifest.get("status"), "artifacts": manifest.get("artifacts") or {}}


@router.get("/{task_id}/artifacts/{artifact_key}")
async def get_task_artifact(
    task_id: str,
    artifact_key: str,
    authorization: str | None = Header(default=None),
):
    """Download one manifest-declared artifact without exposing arbitrary paths."""
    _verify_api_key(authorization)
    manifest = _manifest_or_404(task_id)
    relative = (manifest.get("artifacts") or {}).get(artifact_key)
    if not isinstance(relative, str) or not relative:
        raise HTTPException(status_code=404, detail="Artifact not found")
    task_dir = task_directory(task_id)
    candidate = (task_dir / relative).resolve()
    if not candidate.is_relative_to(task_dir.resolve()) or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(candidate, filename=candidate.name)


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    authorization: str | None = Header(default=None),
):
    """Return the current durable task manifest."""
    _verify_api_key(authorization)
    return _manifest_or_404(task_id)


def _parse_control(**kwargs: Any):
    try:
        return normalize_parse_control(**kwargs)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _store_uploads(task_dir: Path, uploads: list[tuple[UploadFile, str]]) -> list[Path]:
    input_dir = task_dir / "inputs"
    input_dir.mkdir(parents=True, exist_ok=False)
    stored: list[Path] = []
    try:
        for upload, file_id in uploads:
            filename = _safe_filename(upload.filename or "upload.bin")
            path = input_dir / f"{file_id}_{filename}"
            with path.open("wb") as handle:
                while chunk := await upload.read(1024 * 1024):
                    handle.write(chunk)
            stored.append(path)
        return stored
    except Exception:
        for path in stored:
            path.unlink(missing_ok=True)
        raise


async def _start_or_wait(
    *,
    files: list[tuple[Path, str]],
    output_root: Path,
    task_id: str,
    control: Any,
    wait: bool,
    include_text: bool,
):
    coroutine = execute_parse_task(
        files,
        output_root=output_root,
        task_id=task_id,
        control=control,
        formats=control.output.formats,
        editions=control.output.editions,
        include_text=include_text,
    )
    if wait:
        return await coroutine
    background = asyncio.create_task(coroutine, name=f"docmirror-task:{task_id}")
    _BACKGROUND_TASKS.add(background)
    background.add_done_callback(_BACKGROUND_TASKS.discard)
    manifest = read_task_manifest(task_id, output_root=output_root)
    return JSONResponse(status_code=202, content=manifest)


def _manifest_or_404(task_id: str) -> dict[str, Any]:
    try:
        manifest = read_task_manifest(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    if not manifest:
        raise HTTPException(status_code=404, detail="Task not found")
    return manifest


def _new_task_id() -> str:
    return f"task_{uuid4().hex}"


def _input_entry(file_id: str, filename: str) -> dict[str, Any]:
    return {"file_id": file_id, "file_name": filename, "status": "queued"}


def _safe_filename(filename: str) -> str:
    basename = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
    return cleaned or "upload.bin"


__all__ = ["router"]
