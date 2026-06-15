# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Pipeline configuration — resolve middleware lists from enhancement profiles.

``get_pipeline_config`` is the high-level API used by the dispatcher and
orchestrator to determine which middlewares run for a given document.

Resolution path::

    1. Map ``file_type`` transport → ``content_model`` via ``transport_fallback``
       (unless ``content_model`` is provided explicitly from FCR)
    2. Call ``resolve_enhancement_profile(content_model, enhance_mode)``
    3. Return ordered middleware name list

Prefer passing ``content_model`` from the Format Capability Registry when
available; the transport-only path uses ``enhancement_profiles.yaml`` fallback
mapping and may be less precise for compound formats.
"""

from __future__ import annotations

import logging

from docmirror.configs.format.enhancement import (
    resolve_enhancement_profile,
    transport_to_content_model,
)

logger = logging.getLogger(__name__)


def get_pipeline_config(
    file_type: str,
    enhance_mode: str = "standard",
    *,
    content_model: str = "",
) -> list[str]:
    """
    Return ordered middleware names for a transport or content model.

    Prefer ``content_model`` when provided (FCR path); otherwise map
    ``file_type`` via ``enhancement_profiles.yaml`` → ``transport_fallback``.
    """
    model = content_model or transport_to_content_model(file_type)
    middlewares = resolve_enhancement_profile(model, enhance_mode)

    logger.info(
        "[Config] Pipeline: transport=%s content_model=%s mode=%s → %d middlewares",
        file_type,
        model,
        enhance_mode,
        len(middlewares),
    )
    return middlewares
