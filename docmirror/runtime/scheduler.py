# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DRC Runtime Scheduler — worker budget, parallel execution, retry, backpressure.

GA 1.0 §6.2: The scheduler dispatches work units respecting WorkerBudget
constraints, handles retry with backoff, and isolates failures so one bad
unit cannot take down the whole task.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from docmirror.runtime.control import RetryControl, RuntimeControl
from docmirror.runtime.events import ProgressEvent
from docmirror.runtime.ledger import EventLedger
from docmirror.runtime.work_units import WorkUnit

logger = logging.getLogger(__name__)


@dataclass
class SchedulerConfig:
    """Configuration for the Runtime Scheduler."""

    max_file_workers: int = 2
    max_page_workers: int = 4
    retry: RetryControl = field(default_factory=RetryControl)
    runtime_control: RuntimeControl | None = None


class RuntimeScheduler:
    """Dispatches work units respecting budget and retry constraints.

    Maintains a semaphore for concurrency control and tracks per-unit
    progress through the EventLedger.
    """

    def __init__(
        self,
        config: SchedulerConfig,
        ledger: EventLedger,
        *,
        task_id: str = "",
    ) -> None:
        self._config = config
        self._ledger = ledger
        self._task_id = task_id
        self._semaphore = asyncio.Semaphore(config.max_file_workers)
        self._page_semaphore = asyncio.Semaphore(config.max_page_workers)

    # ── Single work unit execution ─────────────────────────────────

    async def execute_unit(
        self,
        unit: WorkUnit,
        handler: Callable[[WorkUnit], Coroutine[Any, Any, dict[str, Any]]],
        *,
        file_id: str = "001",
    ) -> dict[str, Any]:
        """Execute one work unit with retry and progress events.

        Returns the handler's result dict on success, or an error dict on
        final failure.
        """
        max_attempts = self._config.retry.max_attempts
        delay = self._config.retry.delay_seconds

        for attempt in range(1, max_attempts + 1):
            unit.attempt = attempt
            unit.mark_running()

            # Emit started event
            self._ledger.write_progress(
                ProgressEvent(
                    task_id=self._task_id,
                    file_id=file_id,
                    work_unit_id=unit.work_unit_id,
                    stage=unit.unit_type,
                    status="started",
                    message=f"{unit.unit_type} started (attempt {attempt})",
                )
            )
            self._ledger.write_work_unit(_unit_to_dict(unit))

            try:
                # Apply semaphore for concurrent units
                if unit.is_concurrent:
                    async with self._page_semaphore:
                        result = await handler(unit)
                else:
                    async with self._semaphore:
                        result = await handler(unit)

                unit.mark_succeeded(result.get("artifacts"))
                self._ledger.write_progress(
                    ProgressEvent(
                        task_id=self._task_id,
                        file_id=file_id,
                        work_unit_id=unit.work_unit_id,
                        stage=unit.unit_type,
                        status="succeeded",
                        message=f"{unit.unit_type} succeeded",
                        metrics=result.get("metrics", {}),
                    )
                )
                self._ledger.write_work_unit(_unit_to_dict(unit))
                return result

            except Exception as exc:
                retryable = attempt < max_attempts
                unit.mark_failed(exc, retryable=retryable)
                self._ledger.write_progress(
                    ProgressEvent(
                        task_id=self._task_id,
                        file_id=file_id,
                        work_unit_id=unit.work_unit_id,
                        stage=unit.unit_type,
                        status="failed_retryable" if retryable else "failed_final",
                        message=f"{unit.unit_type} failed: {exc}",
                    )
                )
                self._ledger.write_work_unit(_unit_to_dict(unit))

                if not retryable:
                    return {"status": "failed_final", "error": str(exc)}

                logger.warning(
                    "Work unit %s failed (attempt %d/%d): %s — retrying in %.1fs",
                    unit.work_unit_id,
                    attempt,
                    max_attempts,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= 2  # exponential backoff

        return {"status": "failed_final", "error": "max_attempts_exceeded"}

    # ── Batch work unit execution ──────────────────────────────────

    async def execute_plan(
        self,
        units: list[WorkUnit],
        handler: Callable[[WorkUnit], Coroutine[Any, Any, dict[str, Any]]],
        *,
        file_id: str = "001",
    ) -> dict[str, Any]:
        """Execute a full work unit plan respecting dependency order.

        Units with no dependencies run first (concurrently where possible).
        Dependent units wait for their dependencies to succeed.
        """
        results: dict[str, dict[str, Any]] = {}
        pending = list(units)

        while pending:
            # Find units whose dependencies are all satisfied
            ready = [
                u
                for u in pending
                if all(dep in results and results[dep].get("status") == "succeeded" for dep in u.depends_on)
            ]

            if not ready:
                # Deadlock: remaining units have unfinishable dependencies
                for u in pending:
                    u.mark_failed(
                        RuntimeError("dependency_failed"),
                        retryable=False,
                    )
                break

            # Execute ready units concurrently
            tasks = []
            for unit in ready:
                tasks.append(self.execute_unit(unit, handler, file_id=file_id))

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for unit, result in zip(ready, batch_results):
                if isinstance(result, Exception):
                    results[unit.work_unit_id] = {
                        "status": "failed_final",
                        "error": str(result),
                    }
                else:
                    results[unit.work_unit_id] = result
                pending.remove(unit)

        # Compute aggregate status
        all_succeeded = all(r.get("status") == "succeeded" for r in results.values())
        any_succeeded = any(r.get("status") == "succeeded" for r in results.values())

        return {
            "status": "success" if all_succeeded else ("partial" if any_succeeded else "failed"),
            "unit_results": results,
        }


def _unit_to_dict(unit: WorkUnit) -> dict[str, Any]:
    """Serialize a WorkUnit to a dict for JSONL writing."""
    return {
        "work_unit_id": unit.work_unit_id,
        "task_id": unit.task_id,
        "file_id": unit.file_id,
        "unit_type": unit.unit_type,
        "scope": unit.scope,
        "status": unit.status,
        "attempt": unit.attempt,
        "input_digest": unit.input_digest,
        "depends_on": unit.depends_on,
        "artifacts": unit.artifacts,
        "metrics": unit.metrics,
        "errors": unit.errors,
    }


__all__ = [
    "RuntimeScheduler",
    "SchedulerConfig",
]
