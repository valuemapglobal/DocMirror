# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Page-level pipeline — prepare → segment → assemble → finalize.

Purpose: Runs the four canonical page stages with timing, producing a
``PageLayout``, OCR text parts, layer label, and confidence score.

Main components: ``PagePipeline``.

Upstream: ``CoreExtractor`` page loop, ``PageExtractionContext``.

Downstream: ``pipeline.stages.*``, ``physical.models.PageLayout``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from docmirror.core.pipeline.page_extractor import PageExtractor
from docmirror.core.pipeline.profiler import merge_page_stage_timings, stage_timer
from docmirror.core.pipeline.stages.page_assemble import run_assemble_zones
from docmirror.core.pipeline.stages.page_finalize import run_finalize
from docmirror.core.pipeline.stages.page_prepare import run_prepare
from docmirror.core.pipeline.stages.page_segment import run_segment

if TYPE_CHECKING:
    from docmirror.core.extraction.extractor import CoreExtractor
    from docmirror.core.pipeline.context import PageExtractionContext


class PagePipeline:
    """Runs prepare → segment → assemble → finalize for one page."""

    STAGES = ("prepare", "segment", "assemble", "finalize")

    def __init__(self, extractor: CoreExtractor) -> None:
        self._extractor = extractor

    def run(self, ctx: PageExtractionContext) -> tuple[Any, list[str], str, float]:
        """Run page extraction; returns (PageLayout, ocr_parts, layer, confidence)."""
        pe = PageExtractor(self._extractor)
        stages_ms: dict[str, float] = {}

        with stage_timer(stages_ms, "prepare"):
            page_plum, watermark_filtered, router = run_prepare(pe, ctx)
        with stage_timer(stages_ms, "segment"):
            zones, _used_template, _seg_ms = run_segment(pe, ctx, page_plum)

        width = ctx.fitz_page.rect.width
        height = ctx.fitz_page.rect.height
        _ledger_continuation = bool(
            ctx.page_idx > 0
            and ctx.global_table_template is not None
            and ctx.extraction_profile
            and ctx.extraction_profile.is_borderless_ledger()
            and ctx.extraction_profile.should_use_bcs()
        )
        style_map = {} if _ledger_continuation else pe._extract_page_styles(ctx.fitz_page)

        with stage_timer(stages_ms, "assemble"):
            (
                blocks,
                reading_order,
                page_has_table,
                extraction_layer,
                extraction_confidence,
                ocr_text_parts,
                semantic_zones,
                _formula_ms,
                _table_ms,
            ) = run_assemble_zones(
                pe,
                ctx=ctx,
                zones=zones,
                page_plum=page_plum,
                style_map=style_map,
                content_type=ctx.content_type,
                watermark_filtered=watermark_filtered,
                router=router,
                global_table_template=ctx.global_table_template,
                extraction_profile=ctx.extraction_profile,
                width=width,
                height=height,
            )

        with stage_timer(stages_ms, "finalize"):
            result = run_finalize(
                pe,
                ctx=ctx,
                blocks=blocks,
                reading_order=reading_order,
                page_has_table=page_has_table,
                extraction_layer=extraction_layer,
                extraction_confidence=extraction_confidence,
                ocr_text_parts=ocr_text_parts,
                semantic_zones=semantic_zones,
                page_plum=page_plum,
                zones=zones,
                watermark_filtered=watermark_filtered,
                router=router,
                global_table_template=ctx.global_table_template,
                width=width,
                height=height,
            )

        stage_entry = {"page": ctx.page_idx, "stages_ms": stages_ms}
        audit = getattr(self._extractor, "_page_stage_timings", None)
        if audit is not None:
            audit.append(stage_entry)
        else:
            self._extractor._page_stage_timings = [stage_entry]

        return result


__all__ = ["PagePipeline"]
