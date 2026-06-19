# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Document profile binding — links pre-analysis to extraction profile.

Purpose: Selects and binds ``ExtractionProfile`` (ledger, borderless, BCS,
etc.) from full-text samples and pre-analysis, then triggers logical table
composition.

Main components: ``bind_extraction_profile``, ``compose_logical_tables``.

Upstream: ``analyze.pre_analyzer``, ``profile.resolver``.

Downstream: ``PagePipeline``, ``extract.template_injector``, ``table.pipeline``.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.core.profile.resolver import resolve_layout_profile
from docmirror.core.scene.scene_resolver import SceneResolution, resolve_document_scene
from docmirror.core.table.compose.export_pipeline import compose_logical_export_from_layouts

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
    profile = getattr(host, "_extraction_profile", None)
    export_result = compose_logical_export_from_layouts(
        pages,
        profile=profile,
        full_text=full_text,
        scene_hint=getattr(pre_analysis, "scene_hint", None),
        content_type=getattr(pre_analysis, "content_type", None),
    )

    if export_result.skipped_payload:
        host._quarantined_logical_tables = export_result.skipped_payload

    dual_view = bool(export_result.export_payload)
    if export_result.ltqg_summary is not None and export_result.ltqg_summary.enabled:
        host._ltqg_summary = export_result.ltqg_summary.to_dict()

    return export_result.export_payload, dual_view, export_result.quarantined_physical


__all__ = ["bind_extraction_profile", "compose_logical_tables"]
