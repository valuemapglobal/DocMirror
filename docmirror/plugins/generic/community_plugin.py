# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Generic community fallback plugin.

Universal community plugin for classified document types outside the six premium
domains. Delegates ``recognize`` to ``build_generic_community_output``,
mapping Mirror entities, KV pairs, tables, outlines and repeated text rows into
an adaptive v2.0 envelope with ``community_generic_fallback`` warning.

Pipeline role: last community extract attempt before ``mirror_only`` for
enterprise-only types; gated by ``community.is_community_generic_enabled`` and
``state.is_domain_enabled("generic")``.

Key exports: ``GenericCommunityPlugin``, ``plugin``.

Dependencies: ``DomainPlugin``, ``generic_community_adapter.build_generic_community_output``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins._base.generic_community_adapter import build_generic_community_output
from docmirror.plugins._runtime.plugin_registry import DomainPlugin


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

    def recognize(self, parse_result, text: str = "") -> dict[str, Any]:
        detected_type = getattr(getattr(parse_result, "entities", None), "document_type", "") or "generic"
        if detected_type in ("", "unknown", "generic"):
            detected_type = "generic"
        return build_generic_community_output(parse_result, detected_type, text)


plugin = GenericCommunityPlugin()
