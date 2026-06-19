# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Track reads of deprecated mirror JSON paths (PCM migration)."""

from __future__ import annotations

import logging
import os
from collections import Counter

_logger = logging.getLogger(__name__)
_LEGACY_ACCESS_COUNTS: Counter[str] = Counter()


def record_legacy_mirror_access(path: str, *, count: int = 1) -> None:
    if not path or count <= 0:
        return
    _LEGACY_ACCESS_COUNTS[path] += count
    if _legacy_access_debug_enabled():
        _logger.info("PCM legacy mirror access: %s (+%d)", path, count)


def legacy_access_counts() -> dict[str, int]:
    return dict(_LEGACY_ACCESS_COUNTS)


def reset_legacy_access_counts() -> None:
    _LEGACY_ACCESS_COUNTS.clear()


def log_legacy_access_summary(*, force: bool = False) -> dict[str, int]:
    """Emit debug summary of deprecated JSON path reads since process start."""
    counts = legacy_access_counts()
    if not counts:
        return {}
    if force or _legacy_access_debug_enabled() or _logger.isEnabledFor(logging.DEBUG):
        _logger.debug("PCM legacy mirror access summary: %s", counts)
    return counts


def _legacy_access_debug_enabled() -> bool:
    val = os.environ.get("DOCMIRROR_PCM_LEGACY_ACCESS_DEBUG", "").strip().lower()
    return val in {"1", "true", "yes", "on"}
