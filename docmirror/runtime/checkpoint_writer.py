"""Checkpoint Writer — W4-03/04/05 of the Failure & Degradation Contract.

Writes intermediate stage artifacts so that in the event of a timeout or
resource exhaustion, already-completed pages and stages are not lost.
Provides retry profile suggestions based on what has been completed.

Usage::

    from docmirror.runtime.checkpoint_writer import CheckpointWriter

    cw = CheckpointWriter("/tmp/output/task_001")
    cw.write_page_checkpoint(page=3, data={"text": "...", "tables": []})
    cw.write_stage_complete("ocr", pages_done=10, pages_total=50)
    suggestion = cw.retry_suggestion(completed_pages=10, total_pages=50)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docmirror.models.outcome import OutcomeEvent
from docmirror.models.outcome_bridge import _make_outcome_event


@dataclass
class StageCheckpoint:
    """Checkpoint for a single processing stage."""

    stage: str                          # e.g. ocr, vlm, table, domain, export
    pages_done: int = 0
    pages_total: int = 0
    chunk_index: int = 0
    completed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class CheckpointWriter:
    """Manages intermediate checkpoints for a single parse task.

    Checkpoints are written to ``checkpoints/`` within the task output
    directory so they survive task restarts or timeout recovery.
    """

    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.checkpoint_dir = os.path.join(output_dir, "checkpoints")
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        self._manifest_path = os.path.join(self.checkpoint_dir, "checkpoint_manifest.json")
        self._manifest: dict[str, Any] = self._load_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        if os.path.exists(self._manifest_path):
            try:
                with open(self._manifest_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"stages": {}, "pages_completed": [], "version": 1}

    def _save_manifest(self) -> None:
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump(self._manifest, f, indent=2, default=str)

    def write_page_checkpoint(self, page: int, *, data: dict[str, Any]) -> str:
        """Persist raw page-level data as a checkpoint file."""
        path = os.path.join(self.checkpoint_dir, f"page_{page:04d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"page": page, "data": data, "checkpoint_version": 1}, f, indent=2, default=str)
        if page not in self._manifest["pages_completed"]:
            self._manifest["pages_completed"].append(page)
            self._save_manifest()
        return path

    def write_stage_complete(
        self, stage: str, *, pages_done: int = 0, pages_total: int = 0, chunk_index: int = 0, metadata: dict[str, Any] | None = None
    ) -> None:
        """Record stage completion in the checkpoint manifest."""
        import datetime
        self._manifest["stages"][stage] = {
            "pages_done": pages_done,
            "pages_total": pages_total,
            "chunk_index": chunk_index,
            "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        self._save_manifest()

    def get_completed_pages(self) -> list[int]:
        """Return sorted list of page numbers with saved checkpoints."""
        return sorted(self._manifest.get("pages_completed", []))

    def get_resume_hint(self) -> dict[str, Any]:
        """Return metadata for task resumption."""
        return {
            "completed_pages": self.get_completed_pages(),
            "last_stage": max(self._manifest.get("stages", {}).keys(), default=""),
            "stages": self._manifest.get("stages", {}),
            "resume_from_page": (max(self.get_completed_pages()) + 1 if self.get_completed_pages() else 1),
        }

    def retry_suggestion(
        self,
        *,
        completed_pages: int = 0,
        total_pages: int = 0,
        timeout_stage: str = "",
        profile: str = "full",
    ) -> OutcomeEvent:
        """Generate a retry suggestion based on what has been completed."""
        if total_pages > 0 and completed_pages >= total_pages:
            code = "TIMEOUT"
        elif completed_pages > 0:
            code = "STAGE_TIMEOUT"
        else:
            code = "RESOURCE_BUDGET_EXHAUSTED"

        # Build a smart suggestion based on progress and profile
        if completed_pages >= total_pages and total_pages > 0:
            suggestion = f"All pages completed but {timeout_stage or 'processing'} timed out in final stage. Increase timeout budget or use profile=forensic for validation."
        elif completed_pages > 0:
            suggestion = f"Pages 1-{completed_pages} completed (of {total_pages}). Retry with page_ranges={completed_pages + 1}-{total_pages} or use profile=compact for remaining pages."
        else:
            suggestion = "No pages completed. Retry with profile=compact or reduce document size."

        retained_pages = list(range(1, completed_pages + 1)) if completed_pages > 0 else []

        return _make_outcome_event(
            code,
            status="failure" if code == "RESOURCE_BUDGET_EXHAUSTED" else "partial",
            scope_override={"type": "document", "pages": retained_pages} if retained_pages else None,
            details={
                "completed_pages": completed_pages,
                "total_pages": total_pages,
                "timeout_stage": timeout_stage,
                "profile": profile,
                "checkpoint_dir": self.checkpoint_dir,
            },
            suggestion_override=suggestion if not timeout_stage else suggestion,
            source_component="runtime.checkpoint",
            evidence_refs=[f"page:{p}" for p in retained_pages],
        )

    def build_timeout_outcome(
        self,
        *,
        completed_pages: int = 0,
        total_pages: int = 0,
        stage: str = "",
        profile: str = "full",
    ) -> dict[str, Any]:
        """Build a full outcome envelope for a timeout/resource error."""
        event = self.retry_suggestion(
            completed_pages=completed_pages,
            total_pages=total_pages,
            timeout_stage=stage,
            profile=profile,
        )
        retained = {
            "pages": list(range(1, completed_pages + 1)) if completed_pages > 0 else [],
            "checkpoint": self.checkpoint_dir,
        }
        return {
            "status": event.status,
            "error": {
                "code": event.code,
                "canonical_code": event.canonical_code,
                "message": event.message,
                "scope": event.scope,
                "recoverable": event.recoverable,
                "retryable": event.retryable,
                "suggestion": event.suggestion,
                "docs_anchor": event.docs_anchor,
            },
            "retained_output": retained,
            "resume_hint": self.get_resume_hint(),
        }
