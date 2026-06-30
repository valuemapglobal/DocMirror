# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DRC Work Unit Planner — decomposes a parse request into recoverable units.

GA 1.0 §6.2: Every task is decomposed into typed work units that can be
individually executed, checkpointed, retried, and reported on.

Work unit types:
  - input_intake: save input, probe format, compute digest
  - format_route: FCR routing decision
  - page_extract: single-page text/OCR/layout
  - page_enrich: table extraction, bbox, quality, evidence per page
  - cross_page_merge: cross-page paragraph/table merging
  - chunk_project: RAG chunk / Markdown fragment
  - edition_project: Community/Enterprise/Finance projection
  - evidence_project: Evidence bundle / visual debug
  - finalize: merge partial outputs, write manifest
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Literal

UnitType = Literal[
    "input_intake",
    "format_route",
    "page_extract",
    "page_enrich",
    "cross_page_merge",
    "chunk_project",
    "edition_project",
    "evidence_project",
    "finalize",
]

UnitStatus = Literal["pending", "running", "succeeded", "failed_retryable", "failed_final", "skipped"]


@dataclass
class WorkUnit:
    """A single recoverable work unit in a task's execution plan."""

    work_unit_id: str
    task_id: str
    file_id: str
    unit_type: UnitType = "page_extract"
    scope: dict[str, Any] = field(default_factory=dict)  # {"page": 7, "chunk": None, "edition": None}
    status: UnitStatus = "pending"
    attempt: int = 0
    input_digest: str = ""
    depends_on: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)  # {"mirror_fragment": "path/to/fragment.json"}
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    _concurrent_types: set[UnitType] = field(
        default_factory=lambda: {
            "page_extract",
            "page_enrich",
            "chunk_project",
            "evidence_project",
        },
        init=False,
        repr=False,
    )

    @property
    def is_concurrent(self) -> bool:
        return self.unit_type in self._concurrent_types

    @property
    def is_recoverable(self) -> bool:
        """All unit types are recoverable except some edge cases."""
        return self.status not in ("failed_final", "skipped")

    def mark_running(self) -> None:
        self.status = "running"
        self.attempt += 1

    def mark_succeeded(self, artifacts: dict[str, str] | None = None) -> None:
        self.status = "succeeded"
        if artifacts:
            self.artifacts.update(artifacts)

    def mark_failed(self, exc: Exception, retryable: bool = True) -> None:
        self.status = "failed_retryable" if retryable else "failed_final"
        self.errors.append(
            {
                "message": str(exc),
                "type": type(exc).__name__,
                "attempt": self.attempt,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )

    def mark_skipped(self, reason: str = "") -> None:
        self.status = "skipped"
        if reason:
            self.errors.append({"message": reason, "type": "skipped"})


@dataclass
class BatchJobEntry:
    """One file entry in a batch job ledger."""

    file_id: str
    file_path: str
    input_digest: str = ""
    status: UnitStatus = "pending"
    attempt: int = 0
    artifacts: dict[str, str] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    work_units: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BatchJobLedger:
    """Persistent ledger for batch jobs — tracks per-file status and recovery."""

    batch_id: str
    task_id: str
    status: str = "running"  # running, partial, success, failed
    files: list[BatchJobEntry] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def completed_file_ids(self) -> set[str]:
        return {f.file_id for f in self.files if f.status == "succeeded"}

    def failed_file_ids(self) -> set[str]:
        return {f.file_id for f in self.files if f.status in ("failed_retryable", "failed_final")}

    def pending_file_ids(self) -> set[str]:
        return {f.file_id for f in self.files if f.status == "pending"}

    def add_entry(self, entry: BatchJobEntry) -> None:
        """Add a file entry to the batch ledger."""
        for existing in self.files:
            if existing.file_id == entry.file_id:
                existing.status = entry.status
                existing.errors = entry.errors
                return
        self.files.append(entry)

    def get_entry(self, file_id: str) -> BatchJobEntry | None:
        """Get a file entry by file_id."""
        for entry in self.files:
            if entry.file_id == file_id:
                return entry
        return None

    def mark_running(self, file_id: str) -> None:
        """Mark a file entry as running."""
        self.mark_file(file_id, "running")

    def mark_succeeded(self, file_id: str, artifacts: dict[str, str] | None = None) -> None:
        """Mark a file entry as succeeded."""
        self.mark_file(file_id, "succeeded")
        if artifacts:
            entry = self.get_entry(file_id)
            if entry:
                entry.artifacts.update(artifacts)

    def compute_progress(self) -> dict[str, Any]:
        """Compute progress summary for the batch job."""
        total = len(self.files)
        succeeded = sum(1 for f in self.files if f.status == "succeeded")
        failed = sum(1 for f in self.files if f.status in ("failed_retryable", "failed_final"))
        running = sum(1 for f in self.files if f.status == "running")
        pending = sum(1 for f in self.files if f.status == "pending")
        return {"total": total, "succeeded": succeeded, "failed": failed, "running": running, "pending": pending}

    def mark_file(self, file_id: str, status: UnitStatus, errors: list[dict[str, Any]] | None = None) -> None:
        for entry in self.files:
            if entry.file_id == file_id:
                entry.status = status
                if errors:
                    entry.errors = errors
                return

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "task_id": self.task_id,
            "status": self.status,
            "files": [
                {
                    "file_id": f.file_id,
                    "file_path": f.file_path,
                    "input_digest": f.input_digest,
                    "status": f.status,
                    "attempt": f.attempt,
                    "artifacts": f.artifacts,
                    "errors": f.errors,
                }
                for f in self.files
            ],
            "artifacts": self.artifacts,
            "errors": self.errors,
        }


class WorkUnitPlanner:
    """Generates a work unit plan from document characteristics and runtime control.

    GA 1.0 §6.7: For small documents, the plan is simple (sync parse). For long
    documents, the planner generates page-extract, page-enrich, cross-page-merge,
    chunk-project, edition-project, and finalize work units.
    """

    @staticmethod
    def plan(
        task_id: str,
        file_id: str,
        input_digest: str,
        *,
        page_count: int = 1,
        editions: list[str] | None = None,
        profile: str = "full",
        doc_size: str = "small",
    ) -> list[WorkUnit]:
        """Generate work unit plan for a single file in a task."""
        units: list[WorkUnit] = []
        _e = editions or ["mirror", "community"]

        # 1. input_intake (always)
        intake = WorkUnit(
            work_unit_id=_uid(task_id, file_id, "intake"),
            task_id=task_id,
            file_id=file_id,
            unit_type="input_intake",
            input_digest=input_digest,
        )
        units.append(intake)

        # 2. format_route (always)
        route = WorkUnit(
            work_unit_id=_uid(task_id, file_id, "route"),
            task_id=task_id,
            file_id=file_id,
            unit_type="format_route",
            input_digest=input_digest,
            depends_on=[intake.work_unit_id],
        )
        units.append(route)

        prior = route.work_unit_id

        # 3. page_extract + page_enrich per page (long/huge docs get individual units)
        if doc_size in ("long", "huge"):
            for p in range(1, page_count + 1):
                extract = WorkUnit(
                    work_unit_id=_uid(task_id, file_id, f"extract_p{p}"),
                    task_id=task_id,
                    file_id=file_id,
                    unit_type="page_extract",
                    scope={"page": p},
                    input_digest=input_digest,
                    depends_on=[prior],
                )
                units.append(extract)

                enrich = WorkUnit(
                    work_unit_id=_uid(task_id, file_id, f"enrich_p{p}"),
                    task_id=task_id,
                    file_id=file_id,
                    unit_type="page_enrich",
                    scope={"page": p},
                    input_digest=input_digest,
                    depends_on=[extract.work_unit_id],
                )
                units.append(enrich)
                prior = enrich.work_unit_id
        else:
            # Small/medium: single extract + enrich batch
            extract = WorkUnit(
                work_unit_id=_uid(task_id, file_id, "extract"),
                task_id=task_id,
                file_id=file_id,
                unit_type="page_extract",
                scope={"pages": list(range(1, page_count + 1))},
                input_digest=input_digest,
                depends_on=[prior],
            )
            units.append(extract)

            enrich = WorkUnit(
                work_unit_id=_uid(task_id, file_id, "enrich"),
                task_id=task_id,
                file_id=file_id,
                unit_type="page_enrich",
                scope={"pages": list(range(1, page_count + 1))},
                input_digest=input_digest,
                depends_on=[extract.work_unit_id],
            )
            units.append(enrich)
            prior = enrich.work_unit_id

        # 4. cross_page_merge (if > 1 page)
        if page_count > 1:
            merge = WorkUnit(
                work_unit_id=_uid(task_id, file_id, "merge"),
                task_id=task_id,
                file_id=file_id,
                unit_type="cross_page_merge",
                input_digest=input_digest,
                depends_on=[prior],
            )
            units.append(merge)
            prior = merge.work_unit_id

        # 5. chunk_project (full/forensic profiles)
        if profile in ("full", "forensic"):
            chunk = WorkUnit(
                work_unit_id=_uid(task_id, file_id, "chunk"),
                task_id=task_id,
                file_id=file_id,
                unit_type="chunk_project",
                input_digest=input_digest,
                depends_on=[prior],
            )
            units.append(chunk)

        # 6. edition_project per edition
        for ed in _e:
            ep = WorkUnit(
                work_unit_id=_uid(task_id, file_id, f"ed_{ed}"),
                task_id=task_id,
                file_id=file_id,
                unit_type="edition_project",
                scope={"edition": ed},
                input_digest=input_digest,
                depends_on=[prior],
            )
            units.append(ep)

        # 7. evidence_project (forensic)
        if profile == "forensic":
            ev = WorkUnit(
                work_unit_id=_uid(task_id, file_id, "evidence"),
                task_id=task_id,
                file_id=file_id,
                unit_type="evidence_project",
                input_digest=input_digest,
                depends_on=[prior],
            )
            units.append(ev)

        # 8. finalize
        final = WorkUnit(
            work_unit_id=_uid(task_id, file_id, "finalize"),
            task_id=task_id,
            file_id=file_id,
            unit_type="finalize",
            input_digest=input_digest,
            depends_on=[u.work_unit_id for u in units],
        )
        units.append(final)

        return units


def _uid(task_id: str, file_id: str, suffix: str) -> str:
    return f"{task_id}/{file_id}/{suffix}"


def compute_input_digest(file_path: str | None = None, content: bytes | None = None) -> str:
    """Compute SHA-256 digest of a file or content blob."""
    if content is not None:
        return hashlib.sha256(content).hexdigest()
    if file_path:
        import os

        if os.path.isfile(file_path):
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
    return hashlib.sha256(b"").hexdigest()


__all__ = [
    "BatchJobEntry",
    "BatchJobLedger",
    "UnitStatus",
    "UnitType",
    "WorkUnit",
    "WorkUnitPlanner",
    "compute_input_digest",
]
