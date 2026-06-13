# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Resolve LayoutProfile from text rules + plugin ExtractionHint (EFPA Phase 3.4)."""

from __future__ import annotations

import logging

from docmirror.core.layout.profile_registry import get_profile, match_layout_profile
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
        try:
            from docmirror.plugins import registry

            plugin = registry.get(scene_hint)
            if plugin:
                hints = plugin.get_extraction_hints() or {}
                lp_id = hints.get("layout_profile")
                if lp_id:
                    hinted = get_profile(str(lp_id))
                    if hinted.profile_id != "generic":
                        logger.debug(
                            "[LayoutProfile] Plugin hint override: %s → %s",
                            profile.profile_id,
                            hinted.profile_id,
                        )
                        return hinted
        except Exception as exc:
            logger.debug("[LayoutProfile] Plugin hint skip: %s", exc)

    return profile
