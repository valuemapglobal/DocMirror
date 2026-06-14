# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""CPS page stage: zone → block extraction and assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from docmirror.models.entities.domain import Block
from docmirror.core.table.pipeline.kv_summary import _extract_summary_entities

if TYPE_CHECKING:
    from docmirror.core.pipeline.context import PageExtractionContext
    from docmirror.core.pipeline.page_extractor import PageExtractor


def run_assemble_zones(
    extractor: PageExtractor,
    *,
    ctx: PageExtractionContext,
    zones,
    page_plum,
    style_map: dict,
    content_type: str,
    watermark_filtered: bool,
    router,
    global_table_template,
    extraction_profile,
    width: float,
    height: float,
) -> tuple[list[Block], int, bool, str, float, list[str], dict[str, list[str]], float, float]:
    """Convert segmented zones into blocks (extract + assemble substage)."""
    fitz_page = ctx.fitz_page
    fitz_doc = ctx.fitz_doc
    page_idx = ctx.page_idx
    layout_al = ctx.layout_al
    is_digital = ctx.is_digital

    blocks: list[Block] = []
    reading_order = 0
    page_has_table = False
    extraction_layer = "unknown"
    extraction_confidence = 0.0
    ocr_text_parts: list[str] = []
    _formula_ms = 0.0
    _table_ms = 0.0
    semantic_zones: dict[str, list[str]] = {
        "title_area": [],
        "metadata_area": [],
        "table_area": [],
        "text_area": [],
        "footer": [],
        "pagination": [],
    }

    for zone in zones:
        block_id = f"blk_{page_idx}_{reading_order}"

        if zone.type == "footer":
            block = Block(
                block_id=block_id,
                block_type="footer",
                bbox=zone.bbox,
                reading_order=reading_order,
                page=page_idx + 1,
                raw_content=zone.text,
            )
            blocks.append(block)
            if any(c.isdigit() for c in zone.text) and len(zone.text) < 10:
                semantic_zones["pagination"].append(block_id)
            else:
                semantic_zones["footer"].append(block_id)
            reading_order += 1
            continue

        if zone.type == "title":
            h_level = extractor._infer_heading_level(zone.text, style_map)
            block = Block(
                block_id=block_id,
                block_type="title",
                bbox=zone.bbox,
                reading_order=reading_order,
                page=page_idx + 1,
                raw_content=zone.text,
                spans=extractor._build_spans(zone.text, zone.bbox, style_map),
                heading_level=h_level,
            )
            blocks.append(block)
            semantic_zones["title_area"].append(block_id)
            reading_order += 1
            continue

        if zone.type == "summary":
            pairs: dict[str, str] = {}
            _extract_summary_entities(zone.chars, pairs)
            if pairs:
                block = Block(
                    block_id=block_id,
                    block_type="key_value",
                    bbox=zone.bbox,
                    reading_order=reading_order,
                    page=page_idx + 1,
                    raw_content=pairs,
                )
                blocks.append(block)
                semantic_zones["metadata_area"].append(block_id)
                reading_order += 1
            continue

        if zone.type == "formula":
            fml_block, fml_ms = extractor._handle_formula_zone(
                zone,
                block_id,
                page_idx,
                fitz_page,
                width,
                height,
                content_type,
                reading_order,
            )
            _formula_ms += fml_ms
            if fml_block:
                blocks.append(fml_block)
                reading_order += 1
            continue

        if zone.type == "data_table":
            tbl_blocks, extraction_layer, extraction_confidence, tbl_ms, zone_tables_extracted = (
                extractor._handle_data_table_zone(
                    zone,
                    block_id,
                    page_idx,
                    page_plum,
                    fitz_page,
                    fitz_doc,
                    reading_order,
                    is_digital,
                    watermark_filtered,
                    router,
                    global_table_template,
                    extraction_profile,
                )
            )
            _table_ms += tbl_ms
            if zone_tables_extracted:
                page_has_table = True
            for b in tbl_blocks:
                blocks.append(b)
                if b.block_type == "table":
                    semantic_zones["table_area"].append(b.block_id)
            reading_order += len(tbl_blocks)
            continue

        text_block = extractor._handle_text_zone(
            zone,
            block_id,
            page_idx,
            fitz_page,
            layout_al,
            style_map,
            reading_order,
        )
        if text_block:
            blocks.append(text_block)
            semantic_zones["text_area"].append(block_id)
            reading_order += 1

    return (
        blocks,
        reading_order,
        page_has_table,
        extraction_layer,
        extraction_confidence,
        ocr_text_parts,
        semantic_zones,
        _formula_ms,
        _table_ms,
    )


__all__ = ["run_assemble_zones"]
