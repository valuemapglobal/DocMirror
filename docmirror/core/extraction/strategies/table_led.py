# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Table-led extraction strategy — thin wrapper to generic CPS (Phase 4 / ADR-M13-03).

SSO routes ``table_dominant`` here; implementation delegates to ``PdfSyncProcessor``
generic pipeline without changing extract behavior.
"""

from __future__ import annotations

from docmirror.core.extraction.strategies.strategy_registry import (
    BaseExtractionStrategy,
    register_strategy,
)


@register_strategy("table_dominant")
class TableLedStrategy(BaseExtractionStrategy):
    """Thin registry entry for table-led documents."""

    def extract(self, fitz_doc, pre_analysis):
        from docmirror.core.pipeline.pdf_processor import reenter_generic_pipeline

        return reenter_generic_pipeline(fitz_doc, pre_analysis)
