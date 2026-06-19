# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read plugin enrichment from edition JSON (Architecture A).

Core ``ParseResult`` / ``001_mirror.json`` stay plugin-free. Edition payloads may
carry ``data.sections``, ``quality``, and ``enrichment`` blocks produced by PEC
and post-extract hooks.
"""

from __future__ import annotations

from typing import Any

_PREFERRED_EDITIONS = ("enterprise", "finance", "community")


def _edition_dict(editions: dict[str, dict[str, Any]] | None, name: str) -> dict[str, Any] | None:
    if not editions:
        return None
    payload = editions.get(name)
    return payload if isinstance(payload, dict) else None


def resolve_sections(
    parse_result: Any,
    editions: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Sections for RAG/graph: edition ``data.sections`` first, then Core ``sections``."""
    for name in _PREFERRED_EDITIONS:
        payload = _edition_dict(editions, name)
        if not payload:
            continue
        sections = (payload.get("data") or {}).get("sections")
        if sections:
            return [_as_section_dict(sec) for sec in sections]

    core_sections = getattr(parse_result, "sections", None) or []
    return [_as_section_dict(sec) for sec in core_sections]


def resolve_quality_trust(
    parse_result: Any,
    editions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Plugin trust metrics from edition ``quality``; Core ``trust`` as fallback."""
    for name in _PREFERRED_EDITIONS:
        payload = _edition_dict(editions, name)
        if not payload:
            continue
        quality = payload.get("quality") or payload.get("validation") or {}
        if quality.get("trust_score") is not None:
            return dict(quality)

    trust = getattr(parse_result, "trust", None)
    if trust is None:
        return None
    return {
        "trust_score": getattr(trust, "trust_score", None),
        "validation_score": getattr(trust, "validation_score", None),
        "validation_passed": getattr(trust, "validation_passed", None),
    }


def _as_section_dict(sec: Any) -> dict[str, Any]:
    if isinstance(sec, dict):
        return dict(sec)
    return {
        "id": getattr(sec, "id", None),
        "title": getattr(sec, "title", None) or getattr(sec, "name", None),
        "name": getattr(sec, "name", None) or getattr(sec, "title", None),
        "page_start": getattr(sec, "page_start", 1),
    }
