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
import logging
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from docmirror.models.entities.parse_result import ResultStatus
from docmirror.models.mirror.completeness import build_mirror_completeness
from docmirror.output.serialization import dumps_json
from docmirror.server.edition_availability import build_edition_availability
from docmirror.server.output_builder import build_all_edition_outputs, build_all_projections

__all__ = ["build_all_edition_outputs", "build_all_projections", "write_four_files"]


logger = logging.getLogger(__name__)


def _inject_output_ids(payload: dict[str, Any], *, document_id: str, task_id: str, file_id: str) -> None:
    if (payload.get("mirror") or {}).get("schema") == "docmirror.mirror_json":
        payload.setdefault("document", {})["document_id"] = document_id
        provenance = payload.setdefault("source", {}).setdefault("provenance", {})
        provenance["output_ids"] = {
            "task_id": task_id,
            "file_id": file_id,
        }
        return
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
    on_progress: Callable[[str, float, str], None] | None = None,
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

    # Edition routing: caller-resolved editions (from _default_editions via
    # resolve_edition_tier) take precedence.  None = direct API call without
    # control options — fall back to resolve_edition_tier as safety net.
    if editions is None:
        from docmirror.plugins._runtime.licensing.entitlements import resolve_edition_tier

        tier = resolve_edition_tier()
        requested_editions = {
            "finance": ("mirror", "community", "enterprise", "finance"),
            "enterprise": ("mirror", "community", "enterprise"),
        }.get(tier, ("mirror", "community"))
        logger.debug(
            "[EditionOutputs] License tier=%s → editions=%s (safety net)",
            tier, requested_editions,
        )
    else:
        requested_editions = tuple(editions)
        if "all" in requested_editions:
            requested_editions = ("mirror", "community", "enterprise", "finance")

    projections = build_all_projections(
        result,
        full_text=full_text,
        file_path=file_path,
        mirror_level=mirror_level,
        include_text=include_text,
        request_id=request_id,
        editions=requested_editions,
        on_progress=on_progress,
    )

    written: dict[str, Path] = {}
    verification_crop_assets: list[dict[str, Any]] = []

    mirror = projections.get("mirror") if "mirror" in requested_editions else None
    if mirror:
        _inject_output_ids(mirror, document_id=document_id, task_id=task_id, file_id=file_id)
        if file_path:
            try:
                from docmirror.structure.verification.crops import (
                    attach_unit_crop_ocr_candidates,
                    attach_verification_crop_assets,
                )

                verification_crop_assets = attach_verification_crop_assets(
                    mirror,
                    pdf_path=file_path,
                    task_dir=task_dir,
                )
                if verification_crop_assets:
                    attach_unit_crop_ocr_candidates(
                        mirror,
                        task_dir=task_dir,
                        crop_assets=verification_crop_assets,
                    )
            except Exception as exc:
                logger.warning("[EditionOutputs] verification crop artifacts failed: %s", exc)
                mirror.setdefault("diagnostics", {}).setdefault("pipeline", []).append(
                    {
                        "stage": "verification_crop_artifacts",
                        "status": "warn",
                        "reason": f"artifact_generation_failed:{exc}",
                    }
                )
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
                logger.warning(
                    "[EditionOutputs] License grants %s edition but package "
                    "'docmirror_%s' is not installed. Install it with: "
                    "pip install docmirror-%s",
                    edition, edition, edition,
                )
                continue
        payload = projections.get(edition)
        if not payload:
            continue
        _inject_output_ids(payload, document_id=document_id, task_id=task_id, file_id=file_id)
        out_path = task_dir / f"{file_id}_{edition}.json"
        out_path.write_text(dumps_json(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written[edition] = out_path

    # --- Write artifact manifest ---
    _manifest_entity = getattr(result, "entities", None)
    _manifest_doc_type = getattr(_manifest_entity, "document_type", "") if _manifest_entity else ""
    _manifest_status = getattr(result, "status", "")
    manifest = {
        "task_id": task_id,
        "document_id": document_id,
        "file_id": file_id,
        "status": _manifest_status.value if hasattr(_manifest_status, "value") else str(_manifest_status),
        "version": 2,
        "created_at": datetime.now().isoformat(),
        "artifacts": {edition: path.name for edition, path in written.items()},
        "edition_availability": build_edition_availability(
            requested=requested_editions,
            written=written,
            projections=projections,
            document_type=_manifest_doc_type,
        ),
        "mirror_completeness": build_mirror_completeness(result),
    }
    if verification_crop_assets:
        manifest["artifacts"]["verification_crops"] = "assets/verification_crops"
        manifest["verification_crop_count"] = len(verification_crop_assets)
    manifest_path = task_dir / "manifest.json"
    manifest_path.write_text(dumps_json(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return task_id, written
