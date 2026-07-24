# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fixed multi-edition and Community Bundle delivery coordinator.

Every public surface uses the same delivery contract. There are no requested
formats, edition selectors, geometry modes, or output profiles.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from docmirror.models.mirror.completeness import build_mirror_completeness
from docmirror.models.schemas.registry import projection_schema_manifest, validate_projection_payload
from docmirror.runtime.serialization import dumps_json
from docmirror.server.artifact_writer import ArtifactWriter
from docmirror.server.edition_availability import build_edition_availability
from docmirror.server.output_builder import build_all_projections

__all__ = ["build_all_projections", "write_outputs"]


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
    if (payload.get("schema") or {}).get("name") == "docmirror.community":
        payload.setdefault("document", {})["id"] = document_id
        return
    payload.setdefault("document", {})["document_id"] = document_id
    payload.setdefault("metadata", {})
    payload["metadata"]["task_id"] = task_id
    payload["metadata"]["file_id"] = file_id
    if not payload["metadata"].get("edition"):
        edition = payload.get("edition") or payload.get("metadata", {}).get("tier")
        if edition:
            payload["metadata"]["edition"] = edition


def _write_community_bundle_files(
    bundle: Any,
    task_dir: Path,
    *,
    file_id: str,
    document_id: str,
) -> dict[str, Path]:
    """Render and publish the Community index, reading view, and Dataset Bundle."""
    bundle.document["id"] = document_id
    targets = {
        "community": task_dir / f"{file_id}_community.json",
        "content": task_dir / f"{file_id}_content.md",
        "datasets": task_dir / f"{file_id}_datasets",
    }
    content = bundle.render_markdown()
    community_payload = bundle.json_payload()
    dataset_csvs = bundle.render_dataset_csvs()
    schema_validation = validate_projection_payload("community", community_payload)
    if not schema_validation.valid:
        raise ValueError("Community schema validation failed: " + "; ".join(schema_validation.errors))
    conservation_issues = bundle.conservation_issues(payload=community_payload, dataset_csvs=dataset_csvs)
    if conservation_issues:
        raise ValueError("Community dataset conservation failed: " + "; ".join(conservation_issues))
    writer = ArtifactWriter(task_dir)
    writer.write_text(targets["community"].name, dumps_json(community_payload, ensure_ascii=False, indent=2))
    writer.write_text(targets["content"].name, content)
    for relative_path, csv_content in dataset_csvs.items():
        writer.write_text(relative_path, csv_content)
    writer.write_text(f"{file_id}_datasets/_audit_cells.csv", bundle.render_audit_csv())
    return targets


def write_outputs(
    result,
    output_dir: Path,
    *,
    file_path: str = "",
    file_id: str = "001",
    task_id: str | None = None,
    overwrite: bool = False,
    on_progress: Callable[[str, float, str], None] | None = None,
    artifact_dir: Path | None = None,
    include_mirror: bool = True,
    include_manifest: bool = True,
) -> tuple[str, dict[str, Path]]:
    """Write delivery projections and optional support artifacts.

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
    from docmirror.models.sealed import seal_parse_result

    sealed = seal_parse_result(result)
    manifest_view = sealed.to_read_view()
    file_path = file_path or getattr(manifest_view, "file_path", "") or ""
    projections = build_all_projections(
        sealed,
        file_path=file_path,
        on_progress=on_progress,
    )

    written: dict[str, Path] = {}
    writer = ArtifactWriter(task_dir)

    mirror_projection = projections.get("mirror")
    if mirror_projection:
        _inject_output_ids(mirror_projection, document_id=document_id, task_id=task_id, file_id=file_id)
    if include_mirror and mirror_projection:
        mirror_path = writer.write_json(f"{file_id}_mirror.json", mirror_projection)
        written["mirror"] = mirror_path

    for edition in ("community", "enterprise", "finance"):
        if edition == "community":
            bundle = projections.get("community_bundle")
            if bundle is None:
                logger.warning("[EditionOutputs] Community bundle was not built")
                continue
            written.update(
                _write_community_bundle_files(
                    bundle,
                    task_dir,
                    file_id=file_id,
                    document_id=document_id,
                )
            )
            continue
        payload = projections.get(edition)
        if not payload:
            continue
        _inject_output_ids(payload, document_id=document_id, task_id=task_id, file_id=file_id)
        out_path = writer.write_json(f"{file_id}_{edition}.json", payload)
        written[edition] = out_path

    # --- Write the standard manifest ---
    _manifest_entity = getattr(manifest_view, "entities", None)
    _manifest_doc_type = getattr(_manifest_entity, "document_type", "") if _manifest_entity else ""
    _manifest_status = getattr(manifest_view, "status", "")
    manifest = {
        "task_id": task_id,
        "document_id": document_id,
        "file_id": file_id,
        "status": _manifest_status.value if hasattr(_manifest_status, "value") else str(_manifest_status),
        "version": 2,
        "schemas": projection_schema_manifest(),
        "created_at": datetime.now().isoformat(),
        "artifacts": {edition: path.name for edition, path in written.items()},
        "edition_availability": build_edition_availability(
            written=written,
            projections=projections,
            document_type=_manifest_doc_type,
        ),
        "mirror_completeness": build_mirror_completeness(manifest_view),
    }
    if include_manifest:
        writer.write_json("manifest.json", manifest)

    if not sealed.verify_integrity():
        raise RuntimeError("Writer boundary violation: sealed ParseResult integrity failed")

    return task_id, written
