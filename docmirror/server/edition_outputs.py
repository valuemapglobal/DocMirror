# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Multi-edition JSON output writer for CLI and API consumers.

Implements the four-file contract documented in design 04: given a
``ParseResult``, builds mirror, community, enterprise, and finance edition
payloads via ``output_builder`` and writes them to a timestamped task
directory with stable ``task_id``, ``file_id``, and ``document_id`` fields.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any
from uuid import uuid4

from docmirror.models.serialization import dumps_json
from docmirror.server.output_builder import build_all_edition_outputs, build_all_projections

__all__ = ["build_all_edition_outputs", "build_all_projections", "write_four_files"]


def _inject_output_ids(payload: dict[str, Any], *, document_id: str, task_id: str, file_id: str) -> None:
    payload.setdefault("document", {})["document_id"] = document_id
    payload.setdefault("metadata", {})
    payload["metadata"]["task_id"] = task_id
    payload["metadata"]["file_id"] = file_id


def write_four_files(
    result,
    output_dir: Path,
    *,
    file_path: str = "",
    full_text: str = "",
    file_id: str = "001",
    task_id: str | None = None,
    mirror_level: str = "standard",
    include_text: bool = False,
    editions: tuple[str, ...] | list[str] | None = None,
    overwrite: bool = False,
    request_id: str = "",
) -> tuple[str, dict[str, Path]]:
    """
    Write ``001_mirror.json`` and edition files under ``output_dir / task_id /``.

    Returns ``(task_id, {edition: path})`` for files actually written.
    """
    from datetime import datetime

    task_id = task_id or f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:4]}"
    task_dir = output_dir / task_id
    if task_dir.exists() and not overwrite:
        raise FileExistsError(f"output task directory already exists: {task_dir}")
    task_dir.mkdir(parents=True, exist_ok=True)

    document_id = f"doc_{task_id}_{file_id}"
    full_text = full_text or getattr(result, "full_text", "") or ""
    file_path = file_path or getattr(result, "file_path", "") or ""

    requested_editions = tuple(editions or ("mirror", "community", "enterprise", "finance"))
    if "all" in requested_editions:
        requested_editions = ("mirror", "community", "enterprise", "finance")

    projections = build_all_projections(
        result,
        full_text=full_text,
        file_path=file_path,
        mirror_level=mirror_level,
        include_text=include_text,
        request_id=request_id,
    )

    written: dict[str, Path] = {}

    mirror = projections.get("mirror") if "mirror" in requested_editions else None
    if mirror:
        _inject_output_ids(mirror, document_id=document_id, task_id=task_id, file_id=file_id)
        mirror_path = task_dir / f"{file_id}_mirror.json"
        mirror_path.write_text(dumps_json(mirror, ensure_ascii=False, indent=2), encoding="utf-8")
        written["mirror"] = mirror_path

    for edition in ("community", "enterprise", "finance"):
        if edition not in requested_editions:
            continue
        if edition != "community":
            try:
                importlib.import_module(f"docmirror_{edition}")
            except ImportError:
                continue
        payload = projections.get(edition)
        if not payload:
            continue
        _inject_output_ids(payload, document_id=document_id, task_id=task_id, file_id=file_id)
        out_path = task_dir / f"{file_id}_{edition}.json"
        out_path.write_text(dumps_json(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written[edition] = out_path

    return task_id, written
