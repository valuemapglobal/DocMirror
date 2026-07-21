"""
Shared helpers for community plugin implementations.

Provides classification block construction and keyword matching utilities used
when serializing edition JSON from plugin extract output.

Pipeline role: the runner and ``generic_community_adapter`` call
``build_classification_block`` to populate the user-facing classification section;
plugins pass scene keywords for optional debug-only ``matched_keywords``.

Key exports: ``collect_matched_keywords``, ``build_classification_block``.
"""

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
        from docmirror.runtime.debug_artifact import is_debug_mode
    except ImportError:
        is_debug_mode = lambda: False  # noqa: E731
    if is_debug_mode():
        block["matched_keywords"] = collect_matched_keywords(text, scene_keywords)
    return block
