# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Format Capability Registry — L0 routing SSOT."""

from docmirror.configs.format.enhancement import (
    resolve_enhancement_profile,
    transport_to_content_model,
)
from docmirror.configs.format.loader import invalidate_format_cache
from docmirror.configs.format.models import (
    ExtractionBinding,
    FormatCapability,
    UNKNOWN_CAPABILITY,
)
from docmirror.configs.format.resolver import detect_transport, resolve_capability

__all__ = [
    "ExtractionBinding",
    "FormatCapability",
    "UNKNOWN_CAPABILITY",
    "detect_transport",
    "invalidate_format_cache",
    "resolve_capability",
    "resolve_enhancement_profile",
    "transport_to_content_model",
]
