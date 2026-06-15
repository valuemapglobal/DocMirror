# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Enhancement profile resolution — bridge from FCR to MEP pipeline.

Thin delegation layer that maps a ``content_model`` and ``enhance_mode`` to an
ordered list of middleware names by calling ``middleware.resolver.resolve_pipeline``.

Also re-exports ``transport_to_content_model`` from ``format.loader`` for callers
that only know the transport string (e.g. ``pdf``, ``xlsx``) and need the
content model key used in ``enhancement_profiles.yaml``.
"""

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
