# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Explicit edition projection and degradation annotations."""

from __future__ import annotations

from enum import Enum
from typing import Any


class CompositionReason(str, Enum):
    """Why an extended edition payload was derived from another edition."""

    INDEPENDENT_EXTRACT = "independent_extract"
    EXTRACT_FALLBACK = "extract_fallback"
    NO_PLUGIN = "no_plugin"
    MIRROR_ONLY = "mirror_only"


def annotate_composition(
    payload: dict[str, Any],
    *,
    edition: str,
    reason: CompositionReason,
    source_edition: str | None = None,
) -> dict[str, Any]:
    """Attach composition metadata to an edition payload."""
    block: dict[str, Any] = {
        "edition": edition,
        "reason": reason.value,
    }
    if source_edition:
        block["source_edition"] = source_edition
    payload.setdefault("composition", block)
    return payload


__all__ = [
    "CompositionReason",
    "annotate_composition",
]
