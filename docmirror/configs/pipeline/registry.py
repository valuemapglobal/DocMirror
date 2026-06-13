# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Pipeline config — resolves middleware lists from enhancement_profiles.yaml.
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
