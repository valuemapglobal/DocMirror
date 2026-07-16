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
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from docmirror.models.mirror.completeness import build_mirror_completeness
from docmirror.runtime.serialization import dumps_json
from docmirror.server.edition_availability import build_edition_availability
from docmirror.server.output_builder import build_all_projections

__all__ = ["build_all_projections", "write_four_files"]


logger = logging.getLogger(__name__)


def _verification_crop_hooks() -> tuple[Callable[..., list[dict[str, Any]]], Callable[..., Any]]:
    """Resolve crop hooks from the canonical geometry verification module."""
    from docmirror.geometry.verification import crops as canonical

    return (
        getattr(canonical, "attach_verification_crop_assets"),
        getattr(canonical, "attach_unit_crop_ocr_candidates"),
    )


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
    if not payload["metadata"].get("edition"):
        edition = payload.get("edition") or payload.get("metadata", {}).get("tier")
        if edition:
            payload["metadata"]["edition"] = edition


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
    artifact_pack: bool = False,
    profile: Any | None = None,
    on_progress: Callable[[str, float, str], None] | None = None,
    artifact_dir: Path | None = None,
) -> tuple[str, dict[str, Path]]:
    """
    Write ``001_mirror.json`` and edition files under ``output_dir / task_id /``.

    ``artifact_dir`` lets a parent batch task isolate each file's complete
    artifact pack while retaining the parent ``task_id`` in output lineage.

    Returns ``(task_id, {edition: path})`` for files actually written.
    """
    from datetime import datetime

    task_id = task_id or f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:4]}"
    task_dir = Path(artifact_dir) if artifact_dir is not None else output_dir / task_id
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

        tier = str(resolve_edition_tier()).strip().lower()
        requested_editions = {
            "finance": ("mirror", "community", "enterprise", "finance"),
            "ultimate": ("mirror", "community", "enterprise", "finance"),
            "enterprise": ("mirror", "community", "enterprise"),
        }.get(tier, ("mirror", "community"))
        logger.debug(
            "[EditionOutputs] License tier=%s → editions=%s (safety net)",
            tier,
            requested_editions,
        )
    else:
        requested_editions = tuple(editions)
        if "all" in requested_editions:
            requested_editions = ("mirror", "community", "enterprise", "finance")

    resolved_profile = None
    if profile is not None:
        from docmirror.configs.output_profile import OutputProfile, resolve_profile

        resolved_profile = profile if isinstance(profile, OutputProfile) else resolve_profile(str(profile))
        artifact_pack = artifact_pack or bool(
            resolved_profile.manifest
            or resolved_profile.markdown
            or resolved_profile.evidence_bundle
            or resolved_profile.quality_report
            or resolved_profile.visual_debug
        )

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
        if artifact_pack and file_path:
            try:
                attach_verification_crop_assets, attach_unit_crop_ocr_candidates = _verification_crop_hooks()

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
                    edition,
                    edition,
                    edition,
                )
                continue
        payload = projections.get(edition)
        if not payload:
            continue
        _inject_output_ids(payload, document_id=document_id, task_id=task_id, file_id=file_id)
        out_path = task_dir / f"{file_id}_{edition}.json"
        out_path.write_text(dumps_json(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written[edition] = out_path

    if not artifact_pack:
        return task_id, written

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
    if "mirror" in written:
        from docmirror.evidence.bundle import build_evidence_bundle
        from docmirror.evidence.visual import build_visual_overlay

        evidence_bundle = build_evidence_bundle(
            result, editions=projections, task_id=task_id, document_id=document_id, file_id=file_id
        )
        evidence_path = task_dir / "005_evidence_bundle.json"
        evidence_path.write_text(dumps_json(evidence_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        written["evidence_bundle"] = evidence_path
        manifest["artifacts"]["evidence_bundle"] = evidence_path.name
        manifest["artifacts"]["evidence"] = evidence_path.name

        markdown_path = task_dir / "output.md"
        markdown_path.write_text(full_text or getattr(result, "raw_text", "") or "", encoding="utf-8")
        written["markdown"] = markdown_path
        manifest["artifacts"]["markdown"] = markdown_path.name

        quality_path = task_dir / "quality_report.json"
        mirror_quality = projections.get("mirror", {}).get("quality", {})
        quality_path.write_text(
            dumps_json(
                {
                    "status": "ok",
                    "readiness": {
                        "status": "ready",
                        "gate_count": len(mirror_quality.get("gates") or []),
                        "warning_count": len(mirror_quality.get("warnings") or []),
                    },
                    "quality": mirror_quality,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        written["quality_report"] = quality_path
        manifest["artifacts"]["quality_report"] = quality_path.name

        visual_path = task_dir / "visual_debug.html"
        visual_overlay = build_visual_overlay(result, projections, evidence_bundle)
        visual_path.write_text(
            '<!doctype html><meta charset="utf-8"><title>DocMirror Visual Debug</title>'
            f'<script type="application/json" id="docmirror-visual">{dumps_json(visual_overlay, ensure_ascii=False)}</script>',
            encoding="utf-8",
        )
        written["visual_debug"] = visual_path
        manifest["artifacts"]["visual_debug"] = visual_path.name

    if resolved_profile is not None:
        from docmirror.server.artifact_pack import ensure_quickstart_artifact_pack

        manifest = ensure_quickstart_artifact_pack(
            task_dir,
            manifest,
            result=result,
            profile=resolved_profile,
            pdf_path=file_path or None,
        )
    manifest_path = task_dir / "manifest.json"
    manifest_path.write_text(dumps_json(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return task_id, written
