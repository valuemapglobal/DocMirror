# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enhancement profile resolution by content_model."""

from __future__ import annotations

import logging
import os

from docmirror.configs.format.loader import load_enhancement_profiles

logger = logging.getLogger(__name__)


def resolve_enhancement_profile(
    content_model: str,
    enhance_mode: str = "standard",
) -> list[str]:
    """Return ordered middleware names for content_model × enhance_mode."""
    profiles, _ = load_enhancement_profiles()
    model_cfg = profiles.get(content_model, profiles.get("opaque_binary", {}))
    middlewares = list(model_cfg.get(enhance_mode, model_cfg.get("standard", [])))

    if os.environ.get("DOCMIRROR_ENABLE_SLM") == "1":
        middlewares.append("SLMEntityExtractor")

    logger.debug(
        "[EnhancementProfile] content_model=%s mode=%s → %d middlewares",
        content_model,
        enhance_mode,
        len(middlewares),
    )
    return middlewares


def transport_to_content_model(transport: str) -> str:
    """Map transport to content_model via enhancement_profiles transport_fallback."""
    _, fallback = load_enhancement_profiles()
    return fallback.get(transport, "opaque_binary")
