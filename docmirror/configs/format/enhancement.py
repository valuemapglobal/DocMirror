# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enhancement profile resolution — delegates to MEP resolver."""

from __future__ import annotations

import logging

from docmirror.configs.format.loader import transport_to_content_model
from docmirror.configs.middleware.resolver import resolve_pipeline

logger = logging.getLogger(__name__)


def resolve_enhancement_profile(
    content_model: str,
    enhance_mode: str = "standard",
    result=None,
) -> list[str]:
    """Return ordered middleware names for content_model × enhance_mode."""
    return resolve_pipeline(content_model, enhance_mode, result)


__all__ = ["resolve_enhancement_profile", "transport_to_content_model"]
