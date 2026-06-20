# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Page finalize stage — provenance, confidence, and PageLayout assembly.

Purpose: Stamps block provenance, merges OCR parts, computes page confidence,
and returns the finalized ``PageLayout``.

Main components: ``run_finalize``.

Upstream: Assembled blocks from ``page_assemble``.

Downstream: ``CoreExtractor`` page aggregation, ``provenance_stamps``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docmirror.core.geometry.table_attrs import build_table_geometry_attrs
from docmirror.core.ocr.fallback import analyze_scanned_page
from docmirror.models.entities.domain import Block, PageLayout

if TYPE_CHECKING:
    from docmirror.core.pipeline.context import PageExtractionContext
    from docmirror.core.pipeline.page_extractor import PageExtractor


def run_finalize(
    extractor: PageExtractor,
    *,
    ctx: PageExtractionContext,
    blocks: list[Block],
    reading_order: int,
    page_has_table: bool,
    extraction_layer: str,
    extraction_confidence: float,
    ocr_text_parts: list[str],
    semantic_zones: dict[str, list[str]],
    page_plum,
    zones,
    watermark_filtered: bool,
    router,
    global_table_template,
    width: float,
    height: float,
) -> tuple[PageLayout, list[str], str, float]:
    """Finalize page: images, fallbacks, layout assembly."""
    fitz_page = ctx.fitz_page
    fitz_doc = ctx.fitz_doc
    page_idx = ctx.page_idx
    layout_al = ctx.layout_al
    is_digital = ctx.is_digital

    img_blocks, reading_order = extractor._extract_page_images(fitz_page, fitz_doc, page_idx, blocks, reading_order)
    blocks.extend(img_blocks)

    if not page_has_table and layout_al.has_table and not layout_al.is_scanned:
        fb_blocks, extraction_layer, extraction_confidence = extractor._fallback_table_extraction(
            page_plum,
            fitz_page,
            fitz_doc,
            page_idx,
            layout_al,
            reading_order,
            is_digital,
            watermark_filtered,
            router,
            global_table_template,
        )
        for b in fb_blocks:
            blocks.append(b)
            semantic_zones["table_area"].append(b.block_id)
        reading_order += len(fb_blocks)

    if layout_al.is_scanned and not page_has_table and not zones:
        ocr_result = analyze_scanned_page(fitz_doc[page_idx], page_idx)
        if ocr_result:
            ocr_id = f"blk_{page_idx}_{reading_order}"
            table = ocr_result["table"]
            table_bbox = tuple(ocr_result.get("table_bbox") or (0.0, 0.0, width, height))
            attrs = build_table_geometry_attrs(
                table,
                chars=list(getattr(page_plum, "chars", None) or []),
                table_bbox=table_bbox,
                page_number=page_idx + 1,
                table_index=0,
                geometry_source="ocr_table_fallback",
                geometry_confidence=ocr_result.get("confidence"),
                base_attrs={
                    "extraction_layer": "ocr_table_fallback",
                    "extraction_confidence": ocr_result.get("confidence"),
                    "zone_type": "ocr_table_fallback",
                },
            )
            blocks.append(
                Block(
                    block_id=ocr_id,
                    block_type="table",
                    bbox=table_bbox,
                    reading_order=reading_order,
                    page=page_idx + 1,
                    raw_content=table,
                    attrs=attrs,
                )
            )
            semantic_zones["table_area"].append(ocr_id)
            reading_order += 1
            if ocr_result.get("header_text"):
                ocr_text_parts.append(ocr_result["header_text"])

    page_layout = PageLayout(
        page_number=page_idx + 1,
        width=width,
        height=height,
        blocks=tuple(blocks),
        semantic_zones=semantic_zones,
        is_scanned=layout_al.is_scanned,
    )
    return page_layout, ocr_text_parts, extraction_layer, extraction_confidence
