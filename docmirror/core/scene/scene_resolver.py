# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Scene resolver — maps evidence to document scene and layout profile.

Purpose: Normalizes keyword matches and resolves ``SceneResolution`` including
layout profile ID for downstream profile binding.

Main components: ``resolve_document_scene``, ``scene_to_layout_profile_id``.

Upstream: ``EvidenceEngine`` output, ``PreAnalysisResult``.

Downstream: ``profile.resolver``, ``pipeline.document_profile``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from docmirror.configs.scene.loader import get_scene_specs

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SceneResolution:
    """Result of document-scene classification."""

    scene: str
    confidence: float
    matched_keyword: str = ""
    source: str = "scene_keywords"


def _normalize_for_keyword_match(text: str) -> str:
    """Collapse whitespace so PDF line-breaks do not split CJK keywords."""
    return re.sub(r"\s+", "", text or "")


def resolve_document_scene(
    text_sample: str,
    *,
    min_confidence: float = 0.75,
) -> SceneResolution:
    """Classify document scene from text using the shared scene keyword corpus."""
    text = text_sample or ""
    if not text.strip():
        return SceneResolution(scene="unknown", confidence=0.0)

    text_compact = _normalize_for_keyword_match(text)
    keywords_map = get_scene_specs()
    best: SceneResolution | None = None

    for scene, spec in keywords_map.items():
        includes = spec.get("include") or []
        excludes = spec.get("exclude") or []
        if excludes and any(kw in text or (kw and kw in text_compact) for kw in excludes):
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
        # EvidenceEngine / PreAnalyzer often classify ledgers as bank_reconciliation
        "bank_reconciliation": "borderless_ledger_bank",
    }
    return mapping.get(scene)
