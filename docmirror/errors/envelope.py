# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unified Error Envelope — CLI/API/Task consistent error contract.

The ErrorEnvelope provides a standardised structure for every failure path in
DocMirror, including error code, recoverability, user suggestion, and support
context. All entrypoints (CLI, REST API, Task SDK) render this same envelope.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docmirror.models.errors import get_error_meta

logger = logging.getLogger(__name__)


@dataclass
class ErrorEnvelope:
    """Standardised error structure for all user-facing failure paths."""

    code: str = "UNKNOWN"
    message: str = "An unexpected error occurred."
    recoverable: bool = False
    suggestion: str = ""
    support: dict[str, Any] = field(default_factory=lambda: {
        "docs": "",
        "capability_id": "",
        "support_status": "",
    })
    artifact_path: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
            "suggestion": self.suggestion,
            "support": dict(self.support),
            "artifact_path": self.artifact_path,
            "meta": dict(self.meta),
        }


def build_error_envelope(
    code: str,
    message: str = "",
    *,
    suggestion: str = "",
    capability_id: str = "",
    support_status: str = "",
    artifact_path: str = "",
    meta: dict[str, Any] | None = None,
) -> ErrorEnvelope:
    """Build an ErrorEnvelope from an error code and optional context."""
    error_meta = get_error_meta(code)
    return ErrorEnvelope(
        code=code,
        message=message or error_meta.get("user_message", ""),
        recoverable=error_meta.get("recoverable", False),
        suggestion=suggestion or "",
        support={
            "docs": "docs/guide/supported-formats.md",
            "capability_id": capability_id,
            "support_status": support_status,
        },
        artifact_path=artifact_path,
        meta=meta or {},
    )


def render_cli_error(envelope: ErrorEnvelope) -> str:
    """Render error envelope as user-facing CLI text."""
    lines = [f"[bold red]Error:[/bold red] {envelope.message}"]
    if envelope.code:
        lines.append(f"  Code: {envelope.code}")
    if envelope.recoverable:
        lines.append("  This error may be recoverable.")
    if envelope.suggestion:
        lines.append(f"  Suggestion: {envelope.suggestion}")
    if envelope.support.get("capability_id"):
        lines.append(f"  Format: {envelope.support['capability_id']} ({envelope.support.get('support_status', '')})")
    if envelope.artifact_path:
        lines.append(f"  Artifact: {envelope.artifact_path}")
    return "\n".join(lines)


def write_failure_artifacts(
    envelope: ErrorEnvelope,
    task_dir: Path,
    *,
    quality_report: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> Path:
    """Write failure artifacts to task_dir: error.json, manifest.json, quality_report.json."""
    task_dir.mkdir(parents=True, exist_ok=True)

    # error.json
    error_path = task_dir / "error.json"
    error_data = envelope.to_dict()
    with open(error_path, "w", encoding="utf-8") as f:
        json.dump(error_data, f, indent=2, ensure_ascii=False)
    logger.info("[ErrorEnvelope] Wrote error artifact: %s", error_path)

    # manifest.json
    manifest_path = task_dir / "manifest.json"
    manifest_data = {
        "version": 1,
        "success": False,
        "error": error_data,
        "status": "failure",
    }
    if manifest:
        manifest_data.update(manifest)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    # quality_report.json
    if quality_report:
        quality_path = task_dir / "quality_report.json"
        with open(quality_path, "w", encoding="utf-8") as f:
            json.dump(quality_report, f, indent=2, ensure_ascii=False)

    return task_dir
