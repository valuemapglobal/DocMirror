# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Document-level profile binding and logical table composition (CPA design 12 §4.1)."""

from __future__ import annotations

import logging
from typing import Any

from docmirror.core.profile.registry import match_layout_profile
from docmirror.core.profile.resolver import resolve_layout_profile
from docmirror.core.scene.scene_resolver import SceneResolution, resolve_document_scene
from docmirror.core.table.compose.composer import TableComposer, serialize_logical_tables_for_metadata
from docmirror.core.table.merge.merger import collect_quarantined_tables

logger = logging.getLogger(__name__)


def bind_extraction_profile(
    host: Any,
    *,
    full_text_raw: str,
    num_pages: int,
    pre_analysis: Any,
    title_text: str | None = None,
) -> Any:
    """Step 0: resolve scene + layout profile and attach to extractor host."""
    _title = title_text or full_text_raw[:5000]
    scene_resolution = resolve_document_scene(_title)
    if scene_resolution.scene == "unknown" and getattr(pre_analysis, "scene_hint", None) not in (
        None,
        "unknown",
    ):
        scene_resolution = SceneResolution(
            scene=pre_analysis.scene_hint,
            confidence=float(getattr(pre_analysis, "template_confidence", 0.0) or 0.85),
            source="pre_analyzer",
        )
    profile = resolve_layout_profile(
        text_sample=full_text_raw[:12000],
        num_pages=num_pages,
        scene_hint=getattr(pre_analysis, "scene_hint", None) or "unknown",
        content_type=getattr(pre_analysis, "content_type", None) or "unknown",
        resolved_scene=scene_resolution.scene,
        scene_confidence=scene_resolution.confidence,
    )
    host._extraction_profile = profile
    host._document_scene = scene_resolution.scene
    host._scene_confidence = scene_resolution.confidence
    host._extraction_audit = []
    logger.info(
        "[DocMirror] EPO profile=%s scene=%s (conf=%.2f) segmentation=%s bcs=%s",
        profile.profile_id,
        scene_resolution.scene,
        scene_resolution.confidence,
        profile.segmentation_mode,
        profile.enable_best_candidate_selection,
    )
    return profile


def compose_logical_tables(
    host: Any,
    pages: list,
    *,
    full_text: str,
    pre_analysis: Any,
) -> tuple[list | None, bool, list]:
    """Step 4.5: non-destructive logical table composition (dual-view)."""
    profile = getattr(host, "_extraction_profile", None) or match_layout_profile(
        text_sample=full_text,
        num_pages=len(pages),
        scene_hint=getattr(pre_analysis, "scene_hint", None),
        content_type=getattr(pre_analysis, "content_type", None),
    )
    if profile and profile.mirror_skip_cross_page_merge:
        logical = TableComposer.clone_physical_from_layouts(pages)
    else:
        logical = TableComposer.from_page_layouts(pages, profile=profile)
    payload = serialize_logical_tables_for_metadata(logical) if logical else None
    dual_view = bool(logical)
    if dual_view:
        logger.info(
            "[DocMirror] Logical table composition: %d logical tables from %d pages (dual-view)",
            len(logical),
            len(pages),
        )
    quarantined = collect_quarantined_tables(pages, profile=profile)
    if quarantined:
        logger.info(
            "[DocMirror] Quarantined %d standalone table(s) (col mismatch)",
            len(quarantined),
        )
    return payload, dual_view, quarantined


__all__ = ["bind_extraction_profile", "compose_logical_tables"]
