# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Document Runtime Contract (DRC) — RuntimeControl, CostProfile, CheckpointControl.

GA 1.0 §6.1: RuntimeControl sits alongside ParseControl and expresses "how to run"
independently of "how to parse". Cost profiles (compact/full/forensic) control
output granularity, evidence depth, token budgets, and artifact size targets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CostProfileType = Literal["compact", "full", "forensic"]
TaskMode = Literal["sync", "async", "auto"]
MirrorLevel = Literal["standard", "forensic"]


@dataclass(frozen=True)
class CheckpointControl:
    """Controls checkpoint behavior: whether to write and where."""

    enabled: bool = True
    directory: str = "checkpoints"

    def fingerprint(self) -> str:
        import hashlib, json

        data = json.dumps({"enabled": self.enabled, "directory": self.directory}, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ProgressControl:
    """Controls progress event emission."""

    emit_events: bool = True
    events_path: str = "progress_events.ndjson"

    def fingerprint(self) -> str:
        import hashlib, json

        data = json.dumps({"emit_events": self.emit_events, "events_path": self.events_path}, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class StreamingControl:
    """Controls streaming behavior for page/chunk artifacts."""

    page_artifacts: bool = False
    chunk_artifacts: bool = False
    page_artifacts_dir: str = "pages"
    chunk_artifacts_dir: str = "chunks"

    def fingerprint(self) -> str:
        import hashlib, json

        data = json.dumps(
            {
                "page_artifacts": self.page_artifacts,
                "chunk_artifacts": self.chunk_artifacts,
                "page_artifacts_dir": self.page_artifacts_dir,
                "chunk_artifacts_dir": self.chunk_artifacts_dir,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class RetryControl:
    """Controls work unit retry behavior."""

    max_attempts: int = 2
    delay_seconds: float = 0.5

    def fingerprint(self) -> str:
        import hashlib, json

        data = json.dumps(
            {"max_attempts": self.max_attempts, "delay_seconds": self.delay_seconds},
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class LongDocumentControl:
    """Controls long document auto-planning behavior."""

    auto_split: bool = True
    small_doc_pages: int = 10
    long_doc_pages: int = 50
    huge_doc_pages: int = 200
    large_file_mb: int = 100
    ocr_heavy_ratio: float = 0.5

    def fingerprint(self) -> str:
        import hashlib, json

        data = json.dumps(
            {
                "auto_split": self.auto_split,
                "small_doc_pages": self.small_doc_pages,
                "long_doc_pages": self.long_doc_pages,
                "huge_doc_pages": self.huge_doc_pages,
                "large_file_mb": self.large_file_mb,
                "ocr_heavy_ratio": self.ocr_heavy_ratio,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class TokenBudget:
    """Token budget estimate for a work unit or task."""

    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    hard_limit: int = 200_000
    used_input_tokens: int = 0
    used_output_tokens: int = 0

    def remaining(self) -> int:
        used = self.used_input_tokens + self.used_output_tokens
        return max(0, self.hard_limit - used)

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "hard_limit": self.hard_limit,
            "used_input_tokens": self.used_input_tokens,
            "used_output_tokens": self.used_output_tokens,
        }


@dataclass(frozen=True)
class RuntimeControl:
    """Top-level runtime contract — controls how a task is executed.

    Sits alongside ``ParseControl`` (which controls how a document is parsed).
    Together they form the complete execution contract for any entry point
    (CLI, API, SDK, batch).
    """

    cost_profile: CostProfileType = "full"
    task_mode: TaskMode = "auto"
    checkpoint: CheckpointControl = field(default_factory=CheckpointControl)
    progress: ProgressControl = field(default_factory=ProgressControl)
    streaming: StreamingControl = field(default_factory=StreamingControl)
    retry: RetryControl = field(default_factory=RetryControl)
    long_document: LongDocumentControl = field(default_factory=LongDocumentControl)
    token_budget: TokenBudget | None = None

    # ── Factory / helpers ──────────────────────────────────────────────

    @classmethod
    def compact(cls) -> RuntimeControl:
        """Compact preset: minimal output, fast path."""
        return cls(
            cost_profile="compact",
            streaming=StreamingControl(page_artifacts=False, chunk_artifacts=False),
            token_budget=TokenBudget(hard_limit=100_000),
        )

    @classmethod
    def full(cls) -> RuntimeControl:
        """Full preset: balanced output (default)."""
        return cls(
            cost_profile="full",
            streaming=StreamingControl(page_artifacts=True, chunk_artifacts=False),
            token_budget=TokenBudget(hard_limit=200_000),
        )

    @classmethod
    def forensic(cls) -> RuntimeControl:
        """Forensic preset: maximum evidence retention."""
        return cls(
            cost_profile="forensic",
            streaming=StreamingControl(page_artifacts=True, chunk_artifacts=True),
            token_budget=TokenBudget(hard_limit=500_000),
            progress=ProgressControl(emit_events=True),
        )

    @classmethod
    def from_profile(cls, profile: str) -> RuntimeControl:
        """Resolve a RuntimeControl from a profile string."""
        if profile == "compact":
            return cls.compact()
        if profile == "forensic":
            return cls.forensic()
        return cls.full()

    def fingerprint(self) -> str:
        import hashlib, json

        data = json.dumps(
            {
                "cost_profile": self.cost_profile,
                "task_mode": self.task_mode,
                "checkpoint": self.checkpoint.fingerprint(),
                "progress": self.progress.fingerprint(),
                "streaming": self.streaming.fingerprint(),
                "retry": self.retry.fingerprint(),
                "long_document": self.long_document.fingerprint(),
                "token_budget": self.token_budget.to_dict() if self.token_budget else None,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_profile": self.cost_profile,
            "task_mode": self.task_mode,
            "checkpoint": {
                "enabled": self.checkpoint.enabled,
                "directory": self.checkpoint.directory,
            },
            "progress": {
                "emit_events": self.progress.emit_events,
                "events_path": self.progress.events_path,
            },
            "streaming": {
                "page_artifacts": self.streaming.page_artifacts,
                "chunk_artifacts": self.streaming.chunk_artifacts,
                "page_artifacts_dir": self.streaming.page_artifacts_dir,
                "chunk_artifacts_dir": self.streaming.chunk_artifacts_dir,
            },
            "retry": {
                "max_attempts": self.retry.max_attempts,
                "delay_seconds": self.retry.delay_seconds,
            },
            "long_document": {
                "auto_split": self.long_document.auto_split,
                "small_doc_pages": self.long_document.small_doc_pages,
                "long_doc_pages": self.long_document.long_doc_pages,
                "huge_doc_pages": self.long_document.huge_doc_pages,
                "large_file_mb": self.long_document.large_file_mb,
                "ocr_heavy_ratio": self.long_document.ocr_heavy_ratio,
            },
            "token_budget": self.token_budget.to_dict() if self.token_budget else None,
        }


def classify_document_size(
    page_count: int,
    file_size_bytes: int,
    *,
    control: RuntimeControl | None = None,
) -> Literal["small", "medium", "long", "huge"]:
    """Classify document size based on page count and file size.

    Uses ``LongDocumentControl`` thresholds (defaults if no control provided).
    """
    ldc = control.long_document if control else LongDocumentControl()
    if page_count >= ldc.huge_doc_pages or file_size_bytes >= ldc.large_file_mb * 1024 * 1024 * 2:
        return "huge"
    if page_count >= ldc.long_doc_pages or file_size_bytes >= ldc.large_file_mb * 1024 * 1024:
        return "long"
    if page_count > ldc.small_doc_pages:
        return "medium"
    return "small"


def resolve_task_mode(
    doc_size: str,
    *,
    control: RuntimeControl | None = None,
) -> TaskMode:
    """Determine whether a document should run sync, async, or auto.

    Small docs → sync; long/huge docs → async; auto → heuristics.
    """
    if control and control.task_mode != "auto":
        return control.task_mode
    if doc_size in ("long", "huge"):
        return "async"
    return "sync"


__all__ = [
    "CheckpointControl",
    "CostProfileType",
    "LongDocumentControl",
    "MirrorLevel",
    "ProgressControl",
    "RetryControl",
    "RuntimeControl",
    "StreamingControl",
    "TaskMode",
    "TokenBudget",
    "classify_document_size",
    "resolve_task_mode",
]
