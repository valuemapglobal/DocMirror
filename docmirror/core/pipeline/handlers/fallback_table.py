# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Fallback table handler — last-resort table extraction for failed zones.

Purpose: When primary table engines fail, attempts projection/signal-based
recovery on the zone crop.

Main components: ``fallback_table_extraction``.

Upstream: ``page_assemble`` when table handler errors or low confidence.

Downstream: ``table.projection``, ``extract.signal_processor``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from docmirror.core.extract.engine import extract_tables_layered
from docmirror.core.geometry.pdfplumber_native import native_cell_bboxes_for_table
from docmirror.core.geometry.table_attrs import build_table_geometry_attrs
from docmirror.core.ocr.fallback import analyze_scanned_page
from docmirror.models.entities.domain import Block

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)


def _fallback_table_bbox(layout_al, page_plum, table_idx: int) -> tuple[float, float, float, float]:
    table_regions = [r for r in getattr(layout_al, "regions", []) if getattr(r, "type", "") == "table"]
    if table_idx < len(table_regions) and getattr(table_regions[table_idx], "bbox", None):
        return tuple(float(v) for v in table_regions[table_idx].bbox)
    width = float(getattr(page_plum, "width", 0.0) or 0.0)
    height = float(getattr(page_plum, "height", 0.0) or 0.0)
    return (0.0, 0.0, width, height)


def _page_chars(page_plum) -> list[dict]:
    return list(getattr(page_plum, "chars", None) or [])


def _stamp_geometry_audit(extractor: PageExtractor, page_no: int, attrs: dict) -> None:
    if "geometry_coverage_ratio" not in attrs or getattr(extractor._host, "_extraction_audit", None) is None:
        return
    for entry in reversed(extractor._host._extraction_audit):
        if entry.get("page") == page_no:
            entry["geometry_coverage_ratio"] = attrs["geometry_coverage_ratio"]
            return
    extractor._host._extraction_audit.append(
        {"page": page_no, "geometry_coverage_ratio": attrs["geometry_coverage_ratio"]}
    )


def fallback_table_extraction(
    extractor: PageExtractor,
    page_plum,
    fitz_page,
    fitz_doc,
    page_idx: int,
    layout_al,
    reading_order: int,
    is_digital: bool,
    _watermark_filtered: bool,
    _router,
    global_table_template,
) -> tuple[list[Block], str, float]:
    """Fallback path: layout analysis found table but zone detection didn't.

    Returns:
        (blocks, extraction_layer, extraction_confidence)
    """
    logger.info(
        f"[Extractor] Page {page_idx}: Detected Legacy fallback (Rule-based recovery for {layout_al.table_count} layout table zones)"
    )
    result_blocks: list[Block] = []
    page_table_template = global_table_template if page_idx > 0 else None
    page_tables, extraction_layer, extraction_confidence = extract_tables_layered(
        page_plum,
        document_page_count=len(fitz_doc),
        fitz_page=fitz_page,
        watermark_filtered=_watermark_filtered,
        layer_hint=(
            extractor._host._page_state.winning_layer
            if hasattr(extractor._host, "_page_state") and extractor._host._page_state.should_use_hint()
            else None
        ),
        table_template=page_table_template,
    )

    # ── PID Loop (Fallback Path) ──
    if page_tables and extraction_confidence < 0.85:
        # Retry 1: Parameter Shift Resampling (Digital only)
        if is_digital:
            logger.info(
                f"[DocMirror] PID Loop Retry 1 (Fallback): Triggering parameter shift resampling on page {page_idx} (conf={extraction_confidence:.2f})"
            )
            re_tables, re_layer, re_conf = extract_tables_layered(
                page_plum,
                document_page_count=len(fitz_doc),
                fitz_page=fitz_page,
                watermark_filtered=_watermark_filtered,
                layer_hint=None,
                table_template=page_table_template,
                pid_resample=True,
            )
            if re_tables and re_conf > extraction_confidence:
                logger.info(
                    f"[DocMirror] PID Loop Retry 1 Success (Fallback): conf boosted to {re_conf:.2f}. Adopting new parameters."
                )
                page_tables = re_tables
                extraction_confidence = re_conf
                extraction_layer = re_layer

        # Retry 2: Visual Optical Degradation (scanned/non-digital only)
        # Skip OCR degradation for digital PDFs — the native text layer is
        # always more reliable than rendering to image + OCR.
        if (
            not is_digital
            and extraction_confidence < 0.85
            and _router
            and _router.should_enhance_table(page_tables[0] if page_tables else [], extraction_confidence)
        ):
            try:
                high_dpi = _router._high_dpi
                logger.warning(
                    f"[DocMirror] PID Loop Retry 2 (Fallback): Total degradation to Vision/OCR "
                    f"on page {page_idx} at {high_dpi} DPI "
                    f"(confidence={extraction_confidence:.2f})"
                )
                re_result = analyze_scanned_page(
                    fitz_page,
                    page_idx,
                    target_dpi=high_dpi,
                )
                if re_result and re_result.get("table"):
                    re_table = re_result["table"]
                    if len(re_table) >= len(page_tables[0] if page_tables else []):
                        page_tables = [re_table]
                        if hasattr(extractor._host, "_page_state"):
                            extractor._host._page_state.reset()
            except Exception as e:
                logger.debug(f"[DocMirror] Quality Router: OCR Degradation (Fallback) skipped: {e}")
        elif is_digital and extraction_confidence < 0.85:
            logger.debug(
                f"[DocMirror] PID Loop Retry 2 (Fallback): Skipped OCR degradation on page {page_idx} "
                f"(digital document, confidence={extraction_confidence:.2f})"
            )

    ro = reading_order
    for tbl_idx, tbl in enumerate(page_tables):
        if tbl and len(tbl) >= 1:
            tbl_id = f"blk_{page_idx}_{ro}"
            table_bbox = _fallback_table_bbox(layout_al, page_plum, tbl_idx)
            attrs = build_table_geometry_attrs(
                tbl,
                chars=_page_chars(page_plum),
                table_bbox=table_bbox,
                native_cell_bboxes=native_cell_bboxes_for_table(
                    page_plum,
                    tbl,
                    table_bbox=table_bbox,
                    table_index=tbl_idx,
                )
                if extraction_layer in {"pdfplumber_default", "text_fallback"}
                else None,
                page_number=page_idx + 1,
                table_index=tbl_idx,
                geometry_source=extraction_layer or "fallback_table",
                geometry_confidence=extraction_confidence,
                base_attrs={
                    "extraction_layer": extraction_layer,
                    "extraction_confidence": extraction_confidence,
                    "zone_type": "fallback_table",
                },
            )
            _stamp_geometry_audit(extractor, page_idx + 1, attrs)
            result_blocks.append(
                Block(
                    block_id=tbl_id,
                    block_type="table",
                    bbox=table_bbox,
                    reading_order=ro,
                    page=page_idx + 1,
                    raw_content=tbl,
                    attrs=attrs,
                )
            )
            ro += 1

    return result_blocks, extraction_layer, extraction_confidence
