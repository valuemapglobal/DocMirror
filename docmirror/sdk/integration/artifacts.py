"""Artifact manifest reader and download helpers.

Provides ``ArtifactManifest`` (a typed view of manifest.json artifacts)
and helper functions for reading artifact contents from a task directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ArtifactManifest:
    """Typed view of the artifact index in a manifest.json."""

    def __init__(self, manifest: dict[str, Any]):
        self._manifest = manifest
        self._artifacts: dict[str, str] = manifest.get("artifacts") or {}

    @property
    def task_id(self) -> str:
        return self._manifest.get("task_id", "")

    @property
    def request_id(self) -> str:
        return self._manifest.get("request_id", "")

    @property
    def status(self) -> str:
        return self._manifest.get("status", "")

    def list_artifacts(self) -> dict[str, str]:
        """Return a dict of {role: filename}."""
        return dict(self._artifacts)

    def has(self, role: str) -> bool:
        """Check whether an artifact role exists."""
        return role in self._artifacts

    def get_path(self, role: str, task_dir: str | Path) -> Path | None:
        """Resolve an artifact role to an absolute path."""
        filename = self._artifacts.get(role)
        if not filename:
            return None
        path = Path(task_dir) / filename
        return path if path.is_file() else None

    def read_text(self, role: str, task_dir: str | Path) -> str | None:
        """Read the text content of an artifact."""
        path = self.get_path(role, task_dir)
        if path is None:
            return None
        return path.read_text(encoding="utf-8")

    def read_json(self, role: str, task_dir: str | Path) -> Any:
        """Read and parse a JSON artifact."""
        text = self.read_text(role, task_dir)
        return json.loads(text) if text else None


def load_artifact_manifest(manifest_path: str | Path) -> ArtifactManifest:
    """Load and parse a manifest.json into an ArtifactManifest."""
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    return ArtifactManifest(data)


def load_chunks_from_manifest(task_dir: str | Path) -> list[dict[str, Any]]:
    """Load the chunks artifact from a task directory."""
    task_path = Path(task_dir)
    manifest_path = task_path / "manifest.json"
    if not manifest_path.is_file():
        return []

    manifest = load_artifact_manifest(manifest_path)

    # Try chunks artifact by name
    for role in ("chunks", "006_chunks"):
        chunks_path = manifest.get_path(role, task_path)
        if chunks_path:
            data = json.loads(chunks_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("chunks", [])

    return []
