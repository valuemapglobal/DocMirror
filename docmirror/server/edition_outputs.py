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
from docmirror.models.serialization import dumps_json
from pathlib import Path
from typing import Any
from uuid import uuid4

from docmirror.server.output_builder import build_community_output, build_extended_output


def build_all_edition_outputs(
    result,
    *,
    full_text: str = "",
    file_path: str = "",
) -> dict[str, dict[str, Any] | None]:
    """Return edition outputs that would be written as ``001_*.json`` files."""
    outputs: dict[str, dict[str, Any] | None] = {
        "mirror": result.to_api_dict(),
        "community": build_community_output(result, full_text),
    }
    for edition in ("enterprise", "finance"):
        try:
            importlib.import_module(f"docmirror_{edition}")
        except ImportError:
            outputs[edition] = None
            continue
        outputs[edition] = build_extended_output(result, edition, full_text, file_path)
    return outputs


def write_four_files(
    result,
    output_dir: Path,
    *,
    file_path: str = "",
    full_text: str = "",
    file_id: str = "001",
    task_id: str | None = None,
) -> tuple[str, dict[str, Path]]:
    """
    Write ``001_mirror.json`` and edition files under ``output_dir / task_id /``.

    Returns ``(task_id, {edition: path})`` for files actually written.
    """
    from datetime import datetime

    task_id = task_id or f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:4]}"
    task_dir = output_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    document_id = f"doc_{task_id}_{file_id}"
    full_text = full_text or getattr(result, "full_text", "") or ""
    file_path = file_path or getattr(result, "file_path", "") or ""

    written: dict[str, Path] = {}

    mirror = result.to_api_dict()
    mirror["document_id"] = document_id
    mirror.setdefault("metadata", {})
    mirror["metadata"]["task_id"] = task_id
    mirror["metadata"]["file_id"] = file_id
    mirror_path = task_dir / f"{file_id}_mirror.json"
    mirror_path.write_text(dumps_json(mirror, ensure_ascii=False, indent=2), encoding="utf-8")
    written["mirror"] = mirror_path

    for edition, builder in (
        ("community", lambda: build_community_output(result, full_text)),
        ("enterprise", lambda: build_extended_output(result, "enterprise", full_text, file_path)),
        ("finance", lambda: build_extended_output(result, "finance", full_text, file_path)),
    ):
        if edition != "community":
            try:
                importlib.import_module(f"docmirror_{edition}")
            except ImportError:
                continue
        payload = builder()
        if not payload:
            continue
        payload.setdefault("document", {})["document_id"] = document_id
        payload.setdefault("metadata", {})
        payload["metadata"]["task_id"] = task_id
        payload["metadata"]["file_id"] = file_id
        out_path = task_dir / f"{file_id}_{edition}.json"
        out_path.write_text(dumps_json(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written[edition] = out_path

    return task_id, written
