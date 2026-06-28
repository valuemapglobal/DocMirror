# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Profile resolver — maps document signals to layout profile ID.

Purpose: Combines pre-analysis, scene, and title cues to select the active
layout/extraction profile for a document run.

Main components: ``resolve_layout_profile``.

Upstream: ``PreAnalysisResult``, ``scene.scene_resolver``.

Downstream: ``bind_extraction_profile``, ``ExtractionProfile`` binding.
"""

from __future__ import annotations

import logging

from docmirror.framework.extension_points import get_profile_hint_provider
from docmirror.layout.profile.registry import get_profile, match_layout_profile
from docmirror.models.entities.layout_profile import LayoutProfile

logger = logging.getLogger(__name__)


def resolve_layout_profile(
    *,
    text_sample: str,
    num_pages: int,
    content_type: str = "unknown",
    scene_hint: str = "unknown",
    force_profile: str | None = None,
    resolved_scene: str | None = None,
    scene_confidence: float = 0.0,
) -> LayoutProfile:
    """Match profile by SceneResolver + rules, then allow registered plugin hint to override."""
    profile = match_layout_profile(
        text_sample=text_sample,
        num_pages=num_pages,
        content_type=content_type,
        scene_hint=scene_hint,
        force_profile=force_profile,
        resolved_scene=resolved_scene,
        scene_confidence=scene_confidence,
    )

    if scene_hint and scene_hint not in ("unknown", "generic"):
        provider = get_profile_hint_provider()
        if provider is not None:
            try:
                lp_id = provider(scene_hint)
                if lp_id:
                    hinted = get_profile(str(lp_id))
                    if hinted.profile_id != "generic":
                        logger.debug(
                            "[LayoutProfile] Extension hint override: %s → %s",
                            profile.profile_id,
                            hinted.profile_id,
                        )
                        return hinted
            except Exception as exc:
                logger.debug("[LayoutProfile] Extension hint skip: %s", exc)

    return profile
