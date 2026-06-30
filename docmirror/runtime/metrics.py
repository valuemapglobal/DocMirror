# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DRC Runtime Metrics — throughput, latency, memory, token, artifact size.

GA 1.0 §6.6, 10: Runtime metrics are collected per work unit and aggregated
into the task manifest. They provide the observed data for GA release gates
and are bucketed by format, doc_size, quality, runtime, profile, and domain.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class RuntimeMetrics:
    """Aggregate runtime metrics for a single task or work unit."""

    task_id: str = ""
    file_id: str | None = None

    # Timing
    wall_elapsed_ms: float = 0.0
    cpu_elapsed_ms: float = 0.0

    # Throughput
    pages_processed: int = 0
    pages_per_second: float = 0.0

    # Memory
    peak_rss_mb: float = 0.0
    current_rss_mb: float = 0.0

    # Token
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    actual_input_tokens: int = 0
    actual_output_tokens: int = 0

    # Artifact
    artifact_size_bytes: int = 0
    intermediate_artifact_size_bytes: int = 0

    # Fallback
    fallback_count: int = 0
    fallback_details: list[dict[str, str]] = field(default_factory=list)

    # Quality
    page_outcome_failed: int = 0
    page_outcome_low_quality: int = 0
    page_outcome_skipped: int = 0

    # Bucketing tags
    format: str = "unknown"  # pdf_text, pdf_scan, pdf_hybrid, image, office, archive
    doc_size: str = "small"  # small, medium, long, huge
    quality: str = "unknown"  # easy, medium, hard, broken, low_quality
    runtime_env: str = "gpu_available"  # cpu_only, gpu_available, vlm_enabled, vlm_disabled
    profile: str = "full"  # compact, full, forensic
    domain: str = "generic"  # generic, community_core, enterprise, finance

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "file_id": self.file_id,
            "timing": {
                "wall_elapsed_ms": self.wall_elapsed_ms,
                "cpu_elapsed_ms": self.cpu_elapsed_ms,
            },
            "throughput": {
                "pages_processed": self.pages_processed,
                "pages_per_second": self.pages_per_second,
            },
            "memory": {
                "peak_rss_mb": self.peak_rss_mb,
                "current_rss_mb": self.current_rss_mb,
            },
            "tokens": {
                "estimated_input": self.estimated_input_tokens,
                "estimated_output": self.estimated_output_tokens,
                "actual_input": self.actual_input_tokens,
                "actual_output": self.actual_output_tokens,
            },
            "artifacts": {
                "size_bytes": self.artifact_size_bytes,
                "intermediate_size_bytes": self.intermediate_artifact_size_bytes,
            },
            "fallbacks": {
                "count": self.fallback_count,
                "details": self.fallback_details,
            },
            "quality": {
                "failed_pages": self.page_outcome_failed,
                "low_quality_pages": self.page_outcome_low_quality,
                "skipped_pages": self.page_outcome_skipped,
            },
            "bucketing": {
                "format": self.format,
                "doc_size": self.doc_size,
                "quality": self.quality,
                "runtime": self.runtime_env,
                "profile": self.profile,
                "domain": self.domain,
            },
        }


class MetricsCollector:
    """Collects and aggregates runtime metrics across work units."""

    def __init__(
        self,
        task_id: str = "",
        *,
        format: str = "unknown",
        doc_size: str = "small",
        quality: str = "unknown",
        runtime_env: str = "gpu_available",
        profile: str = "full",
        domain: str = "generic",
    ) -> None:
        self._task_id = task_id
        self._start_time = time.perf_counter()
        self._start_cpu = time.process_time()
        self._format = format
        self._doc_size = doc_size
        self._quality = quality
        self._runtime_env = runtime_env
        self._profile = profile
        self._domain = domain
        self._pages_processed = 0
        self._fallback_count = 0
        self._fallback_details: list[dict[str, str]] = []
        self._page_failed = 0
        self._page_low_quality = 0
        self._page_skipped = 0
        self._artifact_bytes = 0
        self._intermediate_bytes = 0
        self._token_input = 0
        self._token_output = 0

    def record_page_outcome(
        self,
        *,
        page_number: int,
        status: Literal["succeeded", "failed", "low_quality", "skipped"] = "succeeded",
        elapsed_ms: float = 0.0,
    ) -> None:
        """Record a single page outcome for metrics."""
        if status == "succeeded":
            self._pages_processed += 1
        elif status == "failed":
            self._page_failed += 1
        elif status == "low_quality":
            self._pages_processed += 1
            self._page_low_quality += 1
        elif status == "skipped":
            self._page_skipped += 1

    def record_fallback(self, from_path: str, to_path: str, reason: str) -> None:
        """Record a runtime fallback event."""
        self._fallback_count += 1
        self._fallback_details.append(
            {
                "from": from_path,
                "to": to_path,
                "reason": reason,
            }
        )

    def record_artifact_size(self, bytes_written: int, *, intermediate: bool = False) -> None:
        """Track artifact bytes for size metrics."""
        if intermediate:
            self._intermediate_bytes += bytes_written
        else:
            self._artifact_bytes += bytes_written

    def record_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Record token usage."""
        self._token_input += input_tokens
        self._token_output += output_tokens

    def snapshot(self, file_id: str | None = None) -> RuntimeMetrics:
        """Take a snapshot of current metrics."""
        wall_elapsed = (time.perf_counter() - self._start_time) * 1000
        cpu_elapsed = (time.process_time() - self._start_cpu) * 1000
        pps = self._pages_processed / max(wall_elapsed / 1000, 0.001)

        mem = _get_memory_usage()

        return RuntimeMetrics(
            task_id=self._task_id,
            file_id=file_id,
            wall_elapsed_ms=wall_elapsed,
            cpu_elapsed_ms=cpu_elapsed,
            pages_processed=self._pages_processed,
            pages_per_second=pps,
            peak_rss_mb=mem.get("peak_rss_mb", 0.0),
            current_rss_mb=mem.get("current_rss_mb", 0.0),
            estimated_input_tokens=0,
            estimated_output_tokens=0,
            actual_input_tokens=self._token_input,
            actual_output_tokens=self._token_output,
            artifact_size_bytes=self._artifact_bytes,
            intermediate_artifact_size_bytes=self._intermediate_bytes,
            fallback_count=self._fallback_count,
            fallback_details=list(self._fallback_details),
            page_outcome_failed=self._page_failed,
            page_outcome_low_quality=self._page_low_quality,
            page_outcome_skipped=self._page_skipped,
            format=self._format,
            doc_size=self._doc_size,
            quality=self._quality,
            runtime_env=self._runtime_env,
            profile=self._profile,
            domain=self._domain,
        )


def _get_memory_usage() -> dict[str, float]:
    """Return current and peak RSS memory in MB, if available."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {
            "peak_rss_mb": usage.ru_maxrss / 1024.0 if usage.ru_maxrss else 0.0,
            "current_rss_mb": 0.0,  # Not available via resource on all platforms
        }
    except (ImportError, AttributeError):
        return {"peak_rss_mb": 0.0, "current_rss_mb": 0.0}


def estimate_tokens(text: str, *, chars_per_token: float = 3.5) -> int:
    """Rough token count estimation from text length."""
    if not text:
        return 0
    return max(1, int(len(text) / chars_per_token))


__all__ = [
    "MetricsCollector",
    "RuntimeMetrics",
    "estimate_tokens",
]
