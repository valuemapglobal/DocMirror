# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Layout profile model for document-scoped extraction hints (EFPA CCC)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LayoutProfileMatchRules(BaseModel):
    """Lightweight rules for auto profile selection."""

    text_any: list[str] = Field(default_factory=list)
    text_all: list[str] = Field(default_factory=list)
    min_pages: int = 0
    content_type: str | None = None
    scene_hint: str | None = None


class LayoutProfile(BaseModel):
    """Document layout profile — drives extraction without hardcoding in CoreExtractor."""

    profile_id: str = "generic"
    inherits: str | None = None
    strategy: str | None = None  # e.g. section_driven (informational)

    sidebar_x_ratio: float | None = None
    global_column_anchors: list[float] | None = None
    expected_header_columns: list[str] = Field(default_factory=list)

    preferred_table_methods: list[str] = Field(default_factory=list)
    disabled_table_methods: list[str] = Field(default_factory=list)

    force_cross_page_merge: bool = True
    mirror_skip_cross_page_merge: bool = False

    document_type_hint: str | None = None

    match: LayoutProfileMatchRules | None = None

    def to_extraction_hint_dict(self) -> dict[str, Any]:
        """Map to resolver / TableExtractionHint compatible dict."""
        return {
            "preferred_methods": list(self.preferred_table_methods),
            "disabled_methods": list(self.disabled_table_methods),
            "profile_id": self.profile_id,
        }

    def table_preferred_layers(self) -> tuple[str, ...]:
        """Layers for TableExtractionHint.preferred_layers."""
        return tuple(self.preferred_table_methods)

    def table_disabled_layers(self) -> tuple[str, ...]:
        return tuple(self.disabled_table_methods)
