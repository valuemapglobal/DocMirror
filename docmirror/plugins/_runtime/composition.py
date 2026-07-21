# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Explicit edition projection and degradation annotations."""

from __future__ import annotations

import copy
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


def apply_extract_fallback(
    base_payload: dict[str, Any],
    *,
    edition: str,
    plugin: Any | None = None,
) -> dict[str, Any]:
    """Mark a ParseResult-derived base projection as extract fallback."""
    cloned = copy.deepcopy(base_payload)
    cloned["edition"] = edition
    cloned.setdefault("metadata", {})["parser"] = f"docmirror-{edition}"
    if plugin is not None:
        cloned.setdefault("plugins", {})[plugin.domain_name] = {
            "display_name": plugin.display_name,
            "edition": plugin.edition,
        }
    return annotate_composition(
        cloned,
        edition=edition,
        reason=CompositionReason.EXTRACT_FALLBACK,
        source_edition="parse_result",
    )


__all__ = [
    "CompositionReason",
    "annotate_composition",
    "apply_extract_fallback",
]
