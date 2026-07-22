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

from docmirror.input.entry.options import normalize_parse_policy
from docmirror.sdk.integration.request import InputRef, ParseRequest
from docmirror.server.task_executor import (
    execute_parse_task,
    initialize_task_manifest,
    read_task_manifest,
    task_directory,
    task_output_root,
)
from docmirror.server.task_result import task_result_from_manifest

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
    file: UploadFile | None = File(default=None, description="One document to parse"),
    files: list[UploadFile] | None = File(default=None, description="One or more documents to parse"),
    wait: bool = Query(default=False, description="Wait for terminal task status"),
    mode: str = Query(default="auto", pattern="^(auto|fast|balanced|accurate|forensic)$"),
    ocr_correction: str = Query(default="safe", pattern="^(off|safe|suggest)$"),
    ocr_language: str | None = Query(default=None),
    ocr_country: str | None = Query(default=None),
    ocr_locale: str | None = Query(default=None),
    ocr_correction_packs: str | None = Query(default=None),
    pages: str | None = Query(default=None),
    max_pages: int | None = Query(default=None),
    workers: str | None = Query(default=None),
    doc_type_hint: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    """Create one task containing one or more heterogeneous documents."""
    _verify_api_key(authorization)
    uploads = ([file] if file is not None else []) + list(files or [])
    return await submit_upload_task(
        uploads,
        wait=wait,
        mode=mode,
        pages=pages,
        max_pages=max_pages,
        workers=workers,
        doc_type_hint=doc_type_hint,
        ocr_correction=ocr_correction,
        ocr_language=ocr_language,
        ocr_country=ocr_country,
        ocr_locale=ocr_locale,
        ocr_correction_packs=ocr_correction_packs,
    )


@router.post("/batch")
async def create_batch_task(
    files: list[UploadFile] = File(..., description="Documents to parse"),
    wait: bool = Query(default=False, description="Wait for terminal task status"),
    mode: str = Query(default="auto", pattern="^(auto|fast|balanced|accurate|forensic)$"),
    ocr_correction: str = Query(default="safe", pattern="^(off|safe|suggest)$"),
    ocr_language: str | None = Query(default=None),
    ocr_country: str | None = Query(default=None),
    ocr_locale: str | None = Query(default=None),
    ocr_correction_packs: str | None = Query(default=None),
    pages: str | None = Query(default=None),
    max_pages: int | None = Query(default=None),
    workers: str | None = Query(default=None),
    doc_type_hint: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    """Compatibility alias for submitting multiple files to one task."""
    _verify_api_key(authorization)
    return await submit_upload_task(
        files,
        wait=wait,
        mode=mode,
        pages=pages,
        max_pages=max_pages,
        workers=workers,
        doc_type_hint=doc_type_hint,
        ocr_correction=ocr_correction,
        ocr_language=ocr_language,
        ocr_country=ocr_country,
        ocr_locale=ocr_locale,
        ocr_correction_packs=ocr_correction_packs,
    )


@router.get("/{task_id}/artifacts")
async def list_task_artifacts(
    task_id: str,
    authorization: str | None = Header(default=None),
):
    """List stable artifact keys and task-relative paths."""
    _verify_api_key(authorization)
    manifest = _manifest_or_404(task_id)
    result = task_result_from_manifest(task_directory(task_id) / "manifest.json")
    return {"task_id": task_id, "status": manifest.get("status"), "artifacts": result.public_dict()["artifacts"]}


@router.get("/{task_id}/artifacts/{artifact_key}")
async def get_task_artifact(
    task_id: str,
    artifact_key: str,
    authorization: str | None = Header(default=None),
):
    """Download one manifest-declared artifact without exposing arbitrary paths."""
    _verify_api_key(authorization)
    if not _is_public_artifact_role(artifact_key):
        raise HTTPException(status_code=404, detail="Artifact not found")
    manifest = _manifest_or_404(task_id)
    relative = (manifest.get("artifacts") or {}).get(artifact_key)
    if not isinstance(relative, str) or not relative:
        raise HTTPException(status_code=404, detail="Artifact not found")
    task_dir = task_directory(task_id)
    candidate = (task_dir / relative).resolve()
    if not candidate.is_relative_to(task_dir.resolve()) or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(candidate, filename=candidate.name)


@router.get("/{task_id}/files/{file_id}/artifacts/{role}")
async def get_input_artifact(
    task_id: str,
    file_id: str,
    role: str,
    authorization: str | None = Header(default=None),
):
    """Download an artifact by input id and stable role."""
    _verify_api_key(authorization)
    if not _is_public_artifact_role(role):
        raise HTTPException(status_code=404, detail="Artifact not found")
    manifest = _manifest_or_404(task_id)
    input_entry = next(
        (item for item in manifest.get("inputs") or [] if item.get("file_id") == file_id),
        None,
    )
    relative = (input_entry or {}).get("artifacts", {}).get(role)
    return _artifact_response(task_id, relative)


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    authorization: str | None = Header(default=None),
):
    """Return the current durable task manifest."""
    _verify_api_key(authorization)
    _manifest_or_404(task_id)
    return task_result_from_manifest(task_directory(task_id) / "manifest.json").public_dict()


async def submit_upload_task(
    uploads: list[UploadFile],
    *,
    wait: bool,
    mode: str = "auto",
    pages: str | None = None,
    max_pages: int | None = None,
    workers: str | int | None = None,
    doc_type_hint: str | None = None,
    ocr_correction: str = "safe",
    ocr_language: str | None = None,
    ocr_country: str | None = None,
    ocr_locale: str | None = None,
    ocr_correction_packs: str | None = None,
):
    """Store uploads, create the canonical request, and start one task."""
    if not uploads:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if any(not upload.filename for upload in uploads):
        raise HTTPException(status_code=400, detail="Every upload must have a filename")

    policy = _parse_policy(
        mode=mode,
        pages=pages,
        max_pages=max_pages,
        doc_type_hint=doc_type_hint,
        ocr_correction=ocr_correction,
        ocr_language=ocr_language,
        ocr_country=ocr_country,
        ocr_locale=ocr_locale,
        ocr_correction_packs=ocr_correction_packs,
    )
    from docmirror.configs.runtime.performance import resolve_worker_budget

    budget = resolve_worker_budget(workers, file_count=len(uploads))
    task_id = _new_task_id()
    output_root = task_output_root()
    task_dir = task_directory(task_id, output_root=output_root)
    upload_specs = [(upload, f"{index:03d}") for index, upload in enumerate(uploads, start=1)]
    stored = await _store_uploads(task_dir, upload_specs)
    refs = [
        InputRef(file_path=str(path), file_id=file_id, file_name=upload.filename or "document")
        for path, (upload, file_id) in zip(stored, upload_specs, strict=True)
    ]
    request = ParseRequest.from_policy(
        refs,
        policy,
        pages=pages,
        max_pages=max_pages,
        workers=workers,
    )
    initialize_task_manifest(
        output_root,
        task_id,
        [_input_entry(ref.file_id, ref.file_name) for ref in refs],
        parse_policy=policy.to_dict(),
        max_workers=budget.page_workers_per_file,
        worker_budget={
            "total": budget.total,
            "file_workers": budget.file_workers,
            "page_workers_per_file": budget.page_workers_per_file,
            "layout_workers": budget.layout_workers,
        },
    )
    return await _start_or_wait(request=request, output_root=output_root, task_id=task_id, wait=wait)


def _parse_policy(**kwargs: Any):
    try:
        return normalize_parse_policy(**kwargs)
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
    request: ParseRequest,
    output_root: Path,
    task_id: str,
    wait: bool,
):
    coroutine = execute_parse_task(
        request,
        output_root=output_root,
        task_id=task_id,
    )
    if wait:
        return (await coroutine).public_dict()
    background = asyncio.create_task(coroutine, name=f"docmirror-task:{task_id}")
    _BACKGROUND_TASKS.add(background)
    background.add_done_callback(_BACKGROUND_TASKS.discard)
    result = task_result_from_manifest(task_directory(task_id, output_root=output_root) / "manifest.json")
    return JSONResponse(status_code=202, content=result.public_dict())


def _manifest_or_404(task_id: str) -> dict[str, Any]:
    try:
        manifest = read_task_manifest(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    if not manifest:
        raise HTTPException(status_code=404, detail="Task not found")
    return manifest


def _artifact_response(task_id: str, relative: Any):
    if not isinstance(relative, str) or not relative:
        raise HTTPException(status_code=404, detail="Artifact not found")
    task_dir = task_directory(task_id)
    candidate = (task_dir / relative).resolve()
    if not candidate.is_relative_to(task_dir.resolve()) or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(candidate, filename=candidate.name)


def _new_task_id() -> str:
    return f"task_{uuid4().hex}"


def _input_entry(file_id: str, filename: str) -> dict[str, Any]:
    return {"file_id": file_id, "file_name": filename, "status": "queued"}


def _safe_filename(filename: str) -> str:
    basename = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
    return cleaned or "upload.bin"


def _is_public_artifact_role(role: str) -> bool:
    return role != "mirror" and not role.endswith("_mirror")


__all__ = ["router", "submit_upload_task"]
