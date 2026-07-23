# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Semantic extension contract for Core ``domain_specific``.

Structural facts live on ``ParseResult`` pages/tables; evolving semantic enrichments
(entity merge hints, scene confidence, cross-page links) belong in ``domain_specific``
and are projected selectively into Mirror JSON.
"""

from __future__ import annotations

from typing import Any

# Keys safe for Mirror ``data.document`` projection (stable structural semantics).
MIRROR_PROJECTED_DOMAIN_KEYS: frozenset[str] = frozenset(
    {
        "classification_provenance",
        "canonical_document_type",
        "extractor_scene_hint",
        "extractor_scene_confidence",
        "pre_analyzer_scene_hint",
        "structure_class",
        "layout_profile_id",
    }
)

# Keys kept edition-only or forensic (multi-round semantic updates).
EDITION_SEMANTIC_KEYS: frozenset[str] = frozenset(
    {
        "entity_merge_hints",
        "temporal_normalization",
        "table_semantic_corrections",
        "cross_page_entity_links",
        "reasoning_traces",
    }
)


def partition_domain_specific(domain_specific: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split domain_specific into mirror-projected vs edition-semantic buckets."""
    if not isinstance(domain_specific, dict):
        return {}, {}
    mirror: dict[str, Any] = {}
    semantic: dict[str, Any] = {}
    for key, value in domain_specific.items():
        if key in MIRROR_PROJECTED_DOMAIN_KEYS:
            mirror[key] = value
        elif key in EDITION_SEMANTIC_KEYS:
            semantic[key] = value
        else:
            mirror[key] = value
    return mirror, semantic


def validate_domain_specific_keys(domain_specific: dict[str, Any]) -> list[str]:
    """Return advisory warnings for unknown semantic keys."""
    warnings: list[str] = []
    known = MIRROR_PROJECTED_DOMAIN_KEYS | EDITION_SEMANTIC_KEYS
    for key in domain_specific:
        if key not in known and not key.startswith("_"):
            warnings.append(f"unknown_domain_specific_key:{key}")
    return warnings


__all__ = [
    "EDITION_SEMANTIC_KEYS",
    "MIRROR_PROJECTED_DOMAIN_KEYS",
    "partition_domain_specific",
    "validate_domain_specific_keys",
]
