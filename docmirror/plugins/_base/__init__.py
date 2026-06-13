"""Shared helpers for community plugin implementations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def collect_matched_keywords(text: str, keywords: Sequence[str]) -> list[str]:
    """Return scene keywords that actually appear in document text."""
    if not text or not keywords:
        return []
    return [kw for kw in keywords if kw and kw in text]


def build_classification_block(
    *,
    document_type: str,
    domain: str,
    archetype: str,
    match_method: str,
    text: str = "",
    scene_keywords: Sequence[str] = (),
    matched: bool = True,
    candidate_types: list[str] | None = None,
) -> dict[str, Any]:
    """Build user-facing classification block (debug-only matched_keywords)."""
    block: dict[str, Any] = {
        "matched": matched,
        "matched_document_type": document_type,
        "matched_domain": domain,
        "matched_archetype": archetype,
        "match_method": match_method,
        "candidate_types": candidate_types or [],
    }
    try:
        from docmirror.core.debug.artifact import is_debug_mode
    except ImportError:
        is_debug_mode = lambda: False  # noqa: E731
    if is_debug_mode():
        block["matched_keywords"] = collect_matched_keywords(text, scene_keywords)
    return block
