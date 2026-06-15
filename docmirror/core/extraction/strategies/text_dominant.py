# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prose/text-dominant extraction strategy — thin wrapper to generic CPS (Phase 4)."""

from __future__ import annotations

from docmirror.core.extraction.strategies.strategy_registry import (
    BaseExtractionStrategy,
    register_strategy,
)


@register_strategy("text_dominant")
class TextDominantStrategy(BaseExtractionStrategy):
    """Thin registry entry for prose-led documents (SSO ``prose_led``)."""

    def extract(self, fitz_doc, pre_analysis):
        from docmirror.core.pipeline.pdf_processor import reenter_generic_pipeline

        return reenter_generic_pipeline(fitz_doc, pre_analysis)
