# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Explicit edition composition rules (Architecture A).

Extended editions (enterprise/finance) may reuse community output only through
documented composition reasons — not implicit serial dependency.
"""

from __future__ import annotations

import copy
from enum import Enum
from typing import Any


class CompositionReason(str, Enum):
    """Why an extended edition payload was derived from another edition."""

    INDEPENDENT_EXTRACT = "independent_extract"
    LICENSE_DEGRADE = "license_degrade"
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


def apply_license_degrade(
    community_payload: dict[str, Any],
    *,
    edition: str,
    plugin: Any,
    license_warning: str = "_license_warning",
) -> dict[str, Any]:
    """Wrap community baseline for unlicensed extended edition."""
    degraded = copy.deepcopy(community_payload)
    degraded["edition"] = edition
    degraded.setdefault("status", {}).setdefault("warnings", [])
    warnings = degraded["status"]["warnings"]
    if license_warning not in warnings:
        warnings.insert(0, license_warning)
    warnings.append(
        f"license_required:edition={edition},domain={getattr(plugin, 'domain_name', '')}"
    )
    degraded.setdefault("plugin", {})["license_required"] = True
    meta = degraded.setdefault("metadata", {})
    meta["parser"] = f"docmirror-{edition}"
    return annotate_composition(
        degraded,
        edition=edition,
        reason=CompositionReason.LICENSE_DEGRADE,
        source_edition="community",
    )


def apply_extract_fallback(
    community_payload: dict[str, Any],
    *,
    edition: str,
    plugin: Any | None = None,
) -> dict[str, Any]:
    """Clone community output when extended extract is unavailable."""
    cloned = copy.deepcopy(community_payload)
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
        source_edition="community",
    )


__all__ = [
    "CompositionReason",
    "annotate_composition",
    "apply_extract_fallback",
    "apply_license_degrade",
]
