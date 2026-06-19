# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Pipeline profiler — per-stage timing utilities.

Purpose: Context managers and merge helpers for recording prepare/segment/
assemble/finalize durations on each page.

Main components: ``stage_timer``, ``merge_page_stage_timings``.

Upstream: ``PagePipeline`` stage wrappers.

Downstream: Debug metrics, ``ParseResult`` timing metadata.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any
from collections.abc import Iterator

_clock = time.perf_counter


@contextmanager
def stage_timer(bucket: dict[str, float], key: str) -> Iterator[None]:
    """Record elapsed ms under ``key`` in ``bucket``."""
    t0 = _clock()
    try:
        yield
    finally:
        bucket[key] = bucket.get(key, 0.0) + (_clock() - t0) * 1000


def merge_page_stage_timings(page_perf: dict[str, Any], stages: dict[str, float]) -> None:
    """Attach CPS stage breakdown to a per-page perf entry."""
    page_perf["stages_ms"] = {k: round(v, 2) for k, v in stages.items()}


__all__ = ["merge_page_stage_timings", "stage_timer"]
