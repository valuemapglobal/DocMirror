# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Task manifest and batch execution helpers for the DocMirror REST API.

Provides ``initialize_task_manifest()``, ``run_batch_parse_task()``, and
supporting utilities, all driven by the shared ``task_result`` schemas.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from docmirror.server.task_result import task_result_from_manifest

logger = logging.getLogger(__name__)

_OUTPUT_ROOT = os.environ.get("DOCMIRROR_TASK_DIR", mkdtemp(prefix="docmirror_tasks_"))


def _task_output_root() -> Path:
    return Path(_OUTPUT_ROOT)


def initialize_task_manifest(
    output_root: Path,
    task_id: str,
    inputs: list[dict[str, str]],
    formats: list[str] | None = None,
    editions: list[str] | None = None,
) -> Path:
    """Create a task manifest stub on disk and return its path."""
    task_dir = output_root / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "task_id": task_id,
        "status": "created",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": inputs,
        "formats": formats or ["json"],
        "editions": editions or ["mirror", "community"],
        "results": [],
    }

    manifest_path = task_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


@dataclass
class SchedulerConfig:
    max_file_workers: int = 4


class ProgressEvent:
    def __init__(self, task_id: str, file_id: str, stage: str, status: str, message: str = ""):
        self.task_id = task_id
        self.file_id = file_id
        self.stage = stage
        self.status = status
        self.message = message


class EventLedger:
    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.events: list[dict] = []

    def update_manifest_v2(self, stage: str, inputs: list[dict]) -> None:
        pass

    def write_progress(self, event: ProgressEvent) -> None:
        self.events.append({
            "task_id": event.task_id,
            "file_id": event.file_id,
            "stage": event.stage,
            "status": event.status,
            "message": event.message,
        })


def write_four_files(
    mirror, output_root, file_path="", full_text="", task_id="", file_id="",
    mirror_level="standard", include_text=False, editions=None,
) -> tuple[str, int]:
    """Write mirror and edition outputs for a single file."""
    editions = editions or ["mirror", "community"]
    file_dir = output_root / task_id / file_id
    file_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    try:
        mirror_data = mirror.to_api_dict() if hasattr(mirror, "to_api_dict") else mirror
        (file_dir / "mirror.json").write_text(
            json.dumps(mirror_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        written += 1
    except Exception as e:
        logger.warning(f"Failed to write mirror for {file_id}: {e}")

    return task_id, written


async def run_batch_parse_task(
    files: list[tuple[Path, str]],
    output_root: Path,
    task_id: str,
    control: Any = None,
    include_text: bool = False,
) -> dict[str, Any]:
    """Run a batch parse task with per-file partial-failure isolation.

    GA 1.0 Step 10: per-file timeout (300s) via asyncio.wait_for.
    """
    from docmirror.core.entry.factory import perceive_document, PerceiveOptions
    from docmirror.errors.envelope import build_error_envelope

    inputs: list[dict] = []
    results: list[dict] = []

    ledger = EventLedger(output_root)
    scheduler_config = SchedulerConfig()
    semaphore = asyncio.Semaphore(scheduler_config.max_file_workers * 2)

    async def _process_one_file(idx: int, temp_path: Path, filename: str) -> None:
        async with semaphore:
            file_id = f"{idx:03d}"
            input_entry = {"file_id": file_id, "file_path": filename, "status": "running"}
            inputs.append(input_entry)
            ledger.update_manifest_v2(stage="parsing", inputs=inputs)
            ledger.write_progress(
                ProgressEvent(
                    task_id=task_id,
                    file_id=file_id,
                    stage="file_parse",
                    status="started",
                    message=f"Parsing file {filename}",
                )
            )
            try:
                result = await asyncio.wait_for(
                    perceive_document(temp_path, PerceiveOptions(control=control)),
                    timeout=300.0,  # GA 1.0 Step 10
                )
                mirror = result.mirror if hasattr(result, "mirror") else result
                _task_id, written = write_four_files(
                    mirror,
                    output_root,
                    file_path=filename,
                    full_text=getattr(mirror, "full_text", "") or "",
                    file_id=file_id,
                    task_id=task_id,
                    mirror_level=getattr(control.output, "mirror_level", "standard") if control else "standard",
                    include_text=include_text,
                    editions=getattr(control.output, "editions", ["mirror", "community"]) if control else ["mirror", "community"],
                )
                input_entry["status"] = "succeeded"
                results.append({"file_id": file_id, "file_name": filename, "status": "success"})
                ledger.write_progress(
                    ProgressEvent(task_id=task_id, file_id=file_id, stage="file_parse", status="completed")
                )
            except asyncio.TimeoutError:
                input_entry["status"] = "timeout"
                results.append({
                    "file_id": file_id, "file_name": filename, "status": "timeout",
                    "error": {"code": "TIMEOUT", "message": "Per-file parse exceeded 300s timeout", "recoverable": True},
                })
            except Exception as e:
                input_entry["status"] = "failed"
                envelope = build_error_envelope("PARSER_ERROR", str(e))
                results.append({
                    "file_id": file_id, "file_name": filename, "status": "error",
                    "error": envelope.to_dict() if hasattr(envelope, "to_dict") else {"message": str(e)},
                })

    await asyncio.gather(*[
        _process_one_file(i, path, name) for i, (path, name) in enumerate(files, start=1)
    ], return_exceptions=True)

    # Update manifest
    manifest_path = output_root / task_id / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "completed"
        manifest["results"] = results
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"task_id": task_id, "status": "completed", "results": results}
