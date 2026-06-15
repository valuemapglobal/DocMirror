# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Generic Community Plugin
========================

Fallback structured output for classified document types outside the six
premium community domains. Mirror layer remains complete; this plugin maps
Mirror → generic v2.0 community JSON.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin
from docmirror.plugins._base.generic_mirror_adapter import build_generic_community_output


class GenericCommunityPlugin(DomainPlugin):
    """Universal community fallback for non-premium classified types."""

    @property
    def domain_name(self) -> str:
        return "generic"

    @property
    def display_name(self) -> str:
        return "Generic Community"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def scene_keywords(self) -> Sequence[str]:
        return ()

    def extract_from_mirror(self, parse_result, text: str = "") -> dict[str, Any]:
        detected_type = getattr(getattr(parse_result, "entities", None), "document_type", "") or "generic"
        if detected_type in ("", "unknown", "generic"):
            detected_type = "generic"
        return build_generic_community_output(parse_result, detected_type, text)


plugin = GenericCommunityPlugin()
