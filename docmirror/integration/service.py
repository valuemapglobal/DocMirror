"""Shared integration service — CLI/SDK/REST common orchestration.

Every integration surface (Click CLI, FastAPI, Python SDK, Docker, RAG
loader, Agent tool) funnels through the functions in this module so that
request normalization, error handling, task lifecycle, and artifact
indexing are implemented exactly once.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
import time
from pathlib import Path
from typing import Any

from docmirror.integration.request import ParseRequest, InputRef
from docmirror.integration.errors import ErrorEnvelope
from docmirror.integration.observability import ObservabilityContext, build_observability_context
from docmirror.integration.artifacts import ArtifactManifest, load_artifact_manifest
from docmirror.core.entry.factory import PerceiveOptions, perceive_document
from docmirror.core.entry.options import normalize_parse_control

logger = logging.getLogger(__name__)


def _generate_task_id() -> str:
    """Generate a timestamped task id."""
    return (
        time.strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid.uuid4().hex[:8]
    )


async def orchestrate_parse(request: ParseRequest, output_dir: str | Path = "output") -> dict[str, Any]:
    """Execute a parse request through the shared pipeline (CLI/SDK/REST).

    Returns a dict compatible with TaskResult serialization.
    """
    output_root = Path(output_dir)
    request_id = request.extras.get("request_id") or _generate_task_id()
    task_id = _generate_task_id()
    task_dir = output_root / task_id

    obs = ObservabilityContext(
        request_id=request_id,
        version="1.0.0",
        profile=request.profile or "full",
        entry=request.extras.get("entry", "unknown"),
    )

    try:
        options = PerceiveOptions(
            mode=request.mode,
            profile=request.profile,
            formats=request.formats,
            editions=request.editions,
            pages=request.pages,
            max_pages=request.max_pages,
            geometry=request.geometry,
            mirror_level=request.mirror_level,
            ocr=request.ocr,
            cache_policy=request.cache_policy,
            doc_type=request.doc_type,
            doc_type_policy=request.doc_type_policy,
            include_text=request.include_text,
            run_id=task_id,
        )

        result = await perceive_document(
            file_path=request.input.file_path,
            data=request.input.data,
            file_name=request.input.file_name,
            options=options,
        )

        manifest = result.to_api_dict() if hasattr(result, "to_api_dict") else {}
        manifest["request_id"] = request_id
        manifest["task_id"] = task_id
        manifest["observability"] = obs.to_dict()

        return {
            "task_id": task_id,
            "request_id": request_id,
            "status": manifest.get("status", "success"),
            "artifacts": manifest.get("artifacts", {}),
            "errors": manifest.get("errors", []),
            "warnings": manifest.get("warnings", []),
            "observability": obs.to_dict(),
            "manifest": manifest,
        }
    except Exception as exc:
        logger.exception("Parse orchestration failed for request_id=%s", request_id)
        envelope = ErrorEnvelope.from_exception(exc, request_id=request_id)
        return {
            "task_id": task_id,
            "request_id": request_id,
            "status": "failed",
            "artifacts": {},
            "errors": [envelope.to_dict()],
            "warnings": [],
            "observability": obs.to_dict(),
            "manifest": {},
        }


def normalize_request_from_cli(kwargs: dict[str, Any]) -> ParseRequest:
    """Normalize CLI kwargs into a ParseRequest."""
    input_ref = InputRef(
        file_path=str(kwargs.get("file")),
        file_name=Path(kwargs.get("file", "document")).name,
    )
    return ParseRequest(
        input=input_ref,
        mode=kwargs.get("mode", "auto"),
        profile=kwargs.get("profile"),
        formats=kwargs.get("formats", ["json"]),
        editions=kwargs.get("editions", ["mirror", "community"]),
        pages=kwargs.get("pages"),
        max_pages=kwargs.get("max_pages"),
        geometry=kwargs.get("geometry"),
        ocr=kwargs.get("ocr", "auto"),
        cache_policy=kwargs.get("cache_policy", "read-write"),
        doc_type=kwargs.get("doc_type"),
        doc_type_policy=kwargs.get("doc_type_policy", "prefer"),
        extras={"entry": "cli"},
    )
