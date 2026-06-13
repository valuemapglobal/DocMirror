# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Runtime performance tuning — page concurrency and worker caps."""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_AUTO_SENTINEL = "auto"
_VALID_PAGE_EXECUTORS = frozenset({"thread", "process"})

# Set in page-level parallel workers so nested char ThreadPools are skipped (GIL).
_page_level_parallel: ContextVar[bool] = ContextVar("page_level_parallel", default=False)


def auto_page_concurrency(
    *,
    cpu_count: int | None = None,
    page_executor: str | None = None,
) -> int:
    """Default page concurrency.

    Thread pool (default): half of logical CPUs (GIL-bound work).
    Process pool: full logical CPU count (true parallelism, documented here).
    """
    if cpu_count is None:
        cpu_count = os.cpu_count() or 4
    executor = resolve_page_executor(page_executor)
    if executor == "process":
        return max(1, cpu_count * 2)
    return max(1, cpu_count // 2)


def page_level_parallel_active() -> bool:
    """True while extracting pages in parallel (thread or process pool)."""
    return _page_level_parallel.get()


@contextmanager
def page_level_parallel_context(active: bool = True) -> Iterator[None]:
    """Mark nested table char methods to run sequentially (no nested thread pool)."""
    token = _page_level_parallel.set(active)
    try:
        yield
    finally:
        _page_level_parallel.reset(token)


def _coerce_page_executor(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        val = raw.strip().lower()
        if val in _VALID_PAGE_EXECUTORS:
            return val
        logger.warning("[Performance] Invalid page_executor=%r; expected thread|process", raw)
    return None


def _yaml_page_executor_raw() -> Any:
    try:
        from docmirror.configs.yaml_loader import config_loader

        return config_loader.get("performance.page_executor")
    except Exception:
        return None


def resolve_page_executor(explicit: str | None = None) -> str:
    """
    Resolve page-level executor backend.

    Priority:
        1. ``explicit`` argument
        2. ``DOCMIRROR_PAGE_EXECUTOR`` env (``thread`` | ``process``)
        3. ``performance.page_executor`` in docmirror.yaml
        4. ``thread`` (safe default for API / nested pool behaviour)
    """
    if explicit is not None:
        coerced = _coerce_page_executor(explicit)
        if coerced is not None:
            return coerced

    env_raw = os.getenv("DOCMIRROR_PAGE_EXECUTOR")
    if env_raw is not None and env_raw.strip():
        coerced = _coerce_page_executor(env_raw)
        if coerced is not None:
            logger.debug("[Performance] page_executor=%s (env)", coerced)
            return coerced

    yaml_raw = _yaml_page_executor_raw()
    coerced = _coerce_page_executor(yaml_raw)
    if coerced is not None:
        logger.debug("[Performance] page_executor=%s (yaml)", coerced)
        return coerced

    return "thread"


def _coerce_concurrency_value(raw: Any) -> int | str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        stripped = raw.strip().lower()
        if stripped in ("", _AUTO_SENTINEL):
            return _AUTO_SENTINEL
        try:
            return max(1, int(stripped))
        except ValueError:
            logger.warning("[Performance] Invalid max_page_concurrency=%r; using auto", raw)
            return _AUTO_SENTINEL
    if isinstance(raw, int):
        return max(1, raw)
    return None


def _yaml_concurrency_raw() -> Any:
    try:
        from docmirror.configs.yaml_loader import config_loader

        return config_loader.get("performance.max_page_concurrency")
    except Exception:
        return None


def resolve_max_page_concurrency(explicit: int | None = None) -> int:
    """
    Resolve effective page-level concurrency.

    Priority:
        1. ``explicit`` argument (call-site override)
        2. ``DOCMIRROR_MAX_PAGE_CONCURRENCY`` env (``auto`` or int)
        3. ``performance.max_page_concurrency`` in docmirror.yaml
        4. ``auto`` (half of CPU count)
    """
    if explicit is not None:
        return max(1, explicit)

    env_raw = os.getenv("DOCMIRROR_MAX_PAGE_CONCURRENCY")
    if env_raw is not None and env_raw.strip():
        coerced = _coerce_concurrency_value(env_raw)
        if coerced == _AUTO_SENTINEL:
            value = auto_page_concurrency(page_executor=resolve_page_executor())
            logger.debug("[Performance] max_page_concurrency=auto (env) -> %d", value)
            return value
        if isinstance(coerced, int):
            return coerced

    yaml_raw = _yaml_concurrency_raw()
    if yaml_raw is not None:
        coerced = _coerce_concurrency_value(yaml_raw)
        if coerced == _AUTO_SENTINEL:
            value = auto_page_concurrency(page_executor=resolve_page_executor())
            logger.debug("[Performance] max_page_concurrency=auto (yaml) -> %d", value)
            return value
        if isinstance(coerced, int):
            return coerced

    value = auto_page_concurrency(page_executor=resolve_page_executor())
    logger.debug("[Performance] max_page_concurrency=auto (default) -> %d", value)
    return value


def effective_page_workers(
    max_page_concurrency: int,
    *,
    num_pages: int,
    cpu_count: int | None = None,
) -> int:
    """Cap parallel page workers by concurrency, page count, and CPU."""
    if max_page_concurrency <= 1 or num_pages <= 1:
        return 1
    cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 4)
    return min(max_page_concurrency, num_pages, cpus)


_process_worker_sem: threading.Semaphore | None = None
_process_worker_cap: int | None = None
_process_worker_sem_lock = threading.Lock()


def _coerce_positive_int(raw: Any, *, name: str) -> int | None:
    if raw is None:
        return None
    try:
        return max(1, int(str(raw).strip()))
    except (TypeError, ValueError):
        logger.warning("[Performance] Invalid %s=%r; ignored", name, raw)
        return None


def _yaml_max_process_workers_raw() -> Any:
    try:
        from docmirror.configs.yaml_loader import config_loader

        return config_loader.get("performance.max_process_workers")
    except Exception:
        return None


def resolve_max_process_workers(*, cpu_count: int | None = None) -> int:
    """
    Global cap on process-pool workers across concurrent extractions (API safety).

    Priority:
        1. ``DOCMIRROR_MAX_PROCESS_WORKERS`` env
        2. ``performance.max_process_workers`` in docmirror.yaml
        3. logical CPU count
    """
    cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 4)

    env_val = _coerce_positive_int(os.getenv("DOCMIRROR_MAX_PROCESS_WORKERS"), name="max_process_workers")
    if env_val is not None:
        return env_val

    yaml_val = _coerce_positive_int(_yaml_max_process_workers_raw(), name="max_process_workers")
    if yaml_val is not None:
        return yaml_val

    return max(1, cpus * 2)


def _process_worker_semaphore() -> threading.Semaphore:
    """Lazy global semaphore sized to :func:`resolve_max_process_workers`."""
    global _process_worker_sem, _process_worker_cap
    cap = resolve_max_process_workers()
    with _process_worker_sem_lock:
        if _process_worker_sem is None or _process_worker_cap != cap:
            _process_worker_sem = threading.Semaphore(cap)
            _process_worker_cap = cap
        return _process_worker_sem


def effective_process_pool_workers(
    requested: int,
    *,
    cpu_count: int | None = None,
) -> int:
    """Per-pool worker count: min(requested, CPUs, global process cap)."""
    if requested <= 1:
        return 1
    cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 4)
    global_cap = resolve_max_process_workers(cpu_count=cpus)
    return max(1, min(requested, global_cap))


@contextmanager
def process_worker_allocation(requested: int) -> Iterator[int]:
    """
    Acquire up to ``requested`` global process-worker slots for one pool.

    Non-blocking partial acquire first; blocks for at least one slot if none free.
    Releases all acquired slots on exit.
    """
    requested = max(1, requested)
    sem = _process_worker_semaphore()
    granted = 0
    for _ in range(requested):
        if sem.acquire(blocking=False):
            granted += 1
        else:
            break
    if granted == 0:
        sem.acquire(blocking=True)
        granted = 1
    try:
        yield granted
    finally:
        for _ in range(granted):
            sem.release()
