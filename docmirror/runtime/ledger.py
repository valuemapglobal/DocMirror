# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DRC Event Ledger — atomic append, manifest v2 update, and event accounting.

GA 1.0 §6.3-6.5: The Event Ledger writes progress events and fallback events
as ndjson, provides manifest v2 helpers, and ensures atomic writes for all
checkpoint and event files.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from docmirror.runtime.events import FallbackEvent, MetricEvent, ProgressEvent


class EventLedger:
    """Appends progress, fallback, and metric events to ndjson files atomically.

    All writes use temporary-file + rename semantics to avoid partial writes
    when the process is killed mid-write.
    """

    def __init__(self, task_dir: Path) -> None:
        self._task_dir = Path(task_dir)
        self._task_dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self._task_dir / "progress_events.ndjson"
        self._fallbacks_path = self._task_dir / "fallback_events.ndjson"
        self._metrics_path = self._task_dir / "metric_events.ndjson"
        self._work_units_path = self._task_dir / "work_units.jsonl"

    # ── Progress events ────────────────────────────────────────────

    def write_progress(self, event: ProgressEvent) -> None:
        """Atomically append a progress event."""
        _atomic_append(self._events_path, event.to_ndjson())

    def read_progress_events(self) -> list[dict[str, Any]]:
        """Read all progress events back as a list of dicts."""
        return _read_ndjson(self._events_path)

    # ── Fallback events ────────────────────────────────────────────

    def write_fallback(self, event: FallbackEvent) -> None:
        """Atomically append a fallback event."""
        _atomic_append(self._fallbacks_path, event.to_ndjson())

    def read_fallback_events(self) -> list[dict[str, Any]]:
        """Read all fallback events back as a list of dicts."""
        return _read_ndjson(self._fallbacks_path)

    # ── Metric events ──────────────────────────────────────────────

    def write_metric(self, event: MetricEvent) -> None:
        """Atomically append a metric event."""
        _atomic_append(self._metrics_path, event.to_ndjson())

    def read_metric_events(self) -> list[dict[str, Any]]:
        """Read all metric events back as a list of dicts."""
        return _read_ndjson(self._metrics_path)

    # ── Work unit journal ──────────────────────────────────────────

    def write_work_unit(self, unit: dict[str, Any]) -> None:
        """Atomically append a work unit state line."""
        _atomic_append(
            self._work_units_path,
            json.dumps(unit, ensure_ascii=False, default=str) + "\n",
        )

    def read_work_units(self) -> list[dict[str, Any]]:
        """Read all work unit entries back as a list of dicts."""
        return _read_ndjson(self._work_units_path)

    # ── Manifest v2 helpers ────────────────────────────────────────

    def update_manifest_v2(
        self,
        *,
        status: str | None = None,
        stage: str | None = None,
        progress: dict[str, Any] | None = None,
        runtime: dict[str, Any] | None = None,
        inputs: list[dict[str, Any]] | None = None,
        page_outcomes: list[dict[str, Any]] | None = None,
        fallbacks: list[dict[str, Any]] | None = None,
        metrics: dict[str, Any] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Read the current manifest, update selected fields, write back atomically."""
        manifest = self.read_manifest()

        # Bump version to 2 if still v1
        if manifest.get("version", 1) < 2:
            manifest["version"] = 2

        if status is not None:
            manifest["status"] = status
        if stage is not None:
            manifest["stage"] = stage
        if progress is not None:
            manifest["progress"] = progress
        if runtime is not None:
            existing = manifest.get("runtime", {})
            existing.update(runtime)
            manifest["runtime"] = existing
        if inputs is not None:
            manifest["inputs"] = inputs
        if page_outcomes is not None:
            existing = list(manifest.get("page_outcomes") or [])
            existing.extend(page_outcomes)
            manifest["page_outcomes"] = existing
        if fallbacks is not None:
            existing = list(manifest.get("fallbacks") or [])
            existing.extend(fallbacks)
            manifest["fallbacks"] = existing
        if metrics is not None:
            existing = manifest.get("metrics", {})
            existing.update(metrics)
            manifest["metrics"] = existing
        if errors is not None:
            existing = list(manifest.get("errors") or [])
            existing.extend(errors)
            manifest["errors"] = existing

        self.write_manifest(manifest)
        return manifest

    def read_manifest(self) -> dict[str, Any]:
        """Read the current manifest (v1 or v2), returning empty dict if missing."""
        path = self._task_dir / "manifest.json"
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        """Atomically write the manifest JSON."""
        path = self._task_dir / "manifest.json"
        _atomic_write(
            path,
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        )

    def compute_progress(self) -> dict[str, Any]:
        """Compute aggregate progress from work units and events."""
        work_units = self.read_work_units()
        total = len(work_units)
        completed = sum(1 for u in work_units if u.get("status") == "succeeded")
        failed = sum(1 for u in work_units if u.get("status") in ("failed_retryable", "failed_final"))
        running = sum(1 for u in work_units if u.get("status") == "running")
        percent = round(completed / max(total, 1) * 100, 2)
        return {
            "total_units": total,
            "completed_units": completed,
            "failed_units": failed,
            "running_units": running,
            "percent": percent,
        }


def _atomic_append(path: Path, content: str) -> None:
    """Append a line to a file atomically using temp + rename.

    For append operations, we use a simpler approach: open with O_APPEND
    and write in one syscall (short lines only). The content is typically
    a single ndjson line, well under PIPE_BUF.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Use os.open + os.write for atomic append on POSIX (PIPE_BUF guarantee)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: Path, content: str) -> None:
    """Write a file atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix="." + path.name + ".",
    )
    try:
        os.write(tmp_fd, content.encode("utf-8"))
        os.fsync(tmp_fd)
    finally:
        os.close(tmp_fd)
    os.replace(tmp_name, str(path))


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    """Read an ndjson file as a list of dicts."""
    if not path.is_file():
        return []
    results: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results


def build_manifest_v2(
    task_id: str,
    *,
    status: str = "running",
    stage: str = "intake",
    inputs: list[dict[str, Any]] | None = None,
    editions: list[str] | None = None,
    formats: list[str] | None = None,
    runtime_control: dict[str, Any] | None = None,
    request_id: str = "",
    profile: str = "full",
    progress: dict[str, Any] | None = None,
    entry: str = "unknown",
) -> dict[str, Any]:
    """Construct a manifest v2 dict with all baseline fields.

    Stable with v1: all v1 field names are preserved.
    """
    if editions is None:
        from docmirror.framework.edition_defaults import default_editions

        editions = list(default_editions())

    manifest: dict[str, Any] = {
        "version": 2,
        "task_id": task_id,
        "request_id": "",
        "status": status,
        "stage": stage,
        "progress": {
            "percent": progress.get("percent", 0.0) if progress else 0.0,
            "total_units": progress.get("total_units", 0) if progress else 0,
            "completed_units": progress.get("completed_units", 0) if progress else 0,
            "failed_units": 0,
            "running_units": 0,
        },
        "observability": {
            "request_id": "",
            "version": "1.0.0",
            "profile": "full",
            "entry": "unknown",
            "warnings": [],
        },
        "runtime": {
            "cost_profile": "full",
            "worker_budget": {},
            "token_budget": {},
        },
        "inputs": list(inputs or []),
        "editions": list(editions),
        "formats": list(formats or ["json"]),
        "artifacts": {},
        "intermediate_artifacts": {},
        "edition_availability": {},
        "pipeline_decision": {},
        "mirror_completeness": {},
        "quality_summary": {},
        "page_outcomes": [],
        "chunk_outcomes": [],
        "fallbacks": [],
        "metrics": {},
        "errors": [],
    }

    if runtime_control:
        manifest["runtime"] = {
            **manifest["runtime"],
            **runtime_control,
        }

    # DIC-W2-05: populate observability from call-site parameters
    manifest["request_id"] = request_id
    manifest["observability"] = {
        "request_id": request_id,
        "version": "1.0.0",
        "profile": profile,
        "entry": entry,
        "warnings": [],
    }

    return manifest


__all__ = [
    "EventLedger",
    "build_manifest_v2",
]
