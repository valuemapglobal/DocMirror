# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Format Capability Registry (FCR) — L0 file-format routing SSOT.

Maps file extensions and MIME types to transport strings, content models, and
extraction bindings defined in ``format_capabilities.yaml``. Also resolves
enhancement profiles from ``enhancement_profiles.yaml``.

Public API::

    resolve_capability()        Path + MIME → ``FormatCapability`` dataclass
    detect_transport()          Backward-compatible transport string lookup
    resolve_enhancement_profile()  Content model × mode → middleware name list
    transport_to_content_model()   Transport → content model via profile fallback
    invalidate_format_cache()   Clear LRU caches after YAML edits

Dataclasses (``FormatCapability``, ``ExtractionBinding``, …) describe adapter
bindings, transcode specs, and fallback chains for each supported format.
"""

from docmirror.configs.format.enhancement import (
    resolve_enhancement_profile,
    transport_to_content_model,
)
from docmirror.configs.format.loader import invalidate_format_cache
from docmirror.configs.format.models import (
    UNKNOWN_CAPABILITY,
    ExtractionBinding,
    FormatCapability,
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
