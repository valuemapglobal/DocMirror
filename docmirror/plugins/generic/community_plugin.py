# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Generic community fallback plugin.

Universal community plugin for classified document types outside the six premium
domains. Maps canonical entities, KV pairs, tables, outlines and repeated text
rows into a deterministic ``ProjectionData``.

Pipeline role: last community extract attempt before ``mirror_only`` for
enterprise-only types; gated by ``community.is_community_generic_enabled`` and
``state.is_domain_enabled("generic")``.

Key exports: ``GenericCommunityPlugin``, ``plugin``.

Dependencies: ``generic_projection.build_generic_projection`` and a sealed read view.
"""

from __future__ import annotations

from collections.abc import Sequence

from docmirror.plugins._base.generic_projection import build_generic_projection
from docmirror.plugins._base.projector import CommunityProjector, ProjectionData


class GenericCommunityPlugin(CommunityProjector):
    """Universal community fallback for non-premium classified types."""

    @property
    def domain_name(self) -> str:
        return "generic"

    @property
    def display_name(self) -> str:
        return "Generic Community"

    @property
    def projector_id(self) -> str:
        return self.domain_name

    @property
    def scene_keywords(self) -> Sequence[str]:
        return ()

    def derive(self, parse_result, text: str = "") -> ProjectionData:
        detected_type = getattr(getattr(parse_result, "entities", None), "document_type", "") or "generic"
        if detected_type in ("", "unknown"):
            detected_type = "generic"
        return build_generic_projection(parse_result, detected_type, text)


plugin = GenericCommunityPlugin()
