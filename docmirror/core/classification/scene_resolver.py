# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Unified document scene resolution — shared by PreAnalyzer, Extract EPO, and Middleware."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_SCENE_KEYWORDS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "scene_keywords.yaml"
)


@dataclass(frozen=True)
class SceneResolution:
    """Result of document-scene classification."""

    scene: str
    confidence: float
    matched_keyword: str = ""
    source: str = "scene_keywords"


@lru_cache(maxsize=1)
def _load_scene_keywords() -> dict[str, dict[str, list[str]]]:
    if not _SCENE_KEYWORDS_PATH.exists():
        return {}
    with open(_SCENE_KEYWORDS_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("scene_keywords", {})


def _normalize_for_keyword_match(text: str) -> str:
    """Collapse whitespace so PDF line-breaks do not split CJK keywords."""
    import re

    return re.sub(r"\s+", "", text or "")


def resolve_document_scene(
    text_sample: str,
    *,
    min_confidence: float = 0.75,
) -> SceneResolution:
    """Classify document scene from text using the same keyword corpus as EvidenceEngine.

    Scoring: longest keyword match wins; confidence scales with keyword length.
    Whitespace is collapsed for matching (PDF often breaks 对方户名 → 对方户\\n名).
    """
    text = text_sample or ""
    if not text.strip():
        return SceneResolution(scene="unknown", confidence=0.0)

    text_compact = _normalize_for_keyword_match(text)
    keywords_map = _load_scene_keywords()
    best: SceneResolution | None = None

    for scene, spec in keywords_map.items():
        includes = spec.get("include") or []
        excludes = spec.get("exclude") or []
        if excludes and any(
            kw in text or (kw and kw in text_compact) for kw in excludes
        ):
            continue
        for kw in includes:
            if not kw:
                continue
            if kw not in text and kw not in text_compact:
                continue
            conf = min(0.99, 0.78 + len(kw) * 0.015)
            if best is None or conf > best.confidence or (
                conf == best.confidence and len(kw) > len(best.matched_keyword)
            ):
                best = SceneResolution(
                    scene=scene,
                    confidence=conf,
                    matched_keyword=kw,
                )

    if best is None or best.confidence < min_confidence:
        return SceneResolution(scene="unknown", confidence=0.0)

    logger.debug(
        "[SceneResolver] scene=%s conf=%.2f keyword=%r",
        best.scene,
        best.confidence,
        best.matched_keyword,
    )
    return best


def scene_to_layout_profile_id(scene: str) -> str | None:
    """Map classified scene to borderless ledger layout profile when applicable."""
    mapping = {
        "wechat_payment": "borderless_ledger_wechat",
        "alipay_payment": "borderless_ledger_alipay",
        "bank_statement": "borderless_ledger_bank",
    }
    return mapping.get(scene)
