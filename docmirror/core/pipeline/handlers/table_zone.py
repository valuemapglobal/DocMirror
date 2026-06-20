# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Table zone handler — layered table extraction for data_table zones.

Purpose: Crops table zones and runs ``extract_tables_layered`` with profile-
aware strategy selection and post-processing.

Main components: ``handle_data_table_zone``.

Upstream: ``data_table`` zones from segmentation.

Downstream: ``extract.engine``, ``extraction.table_postprocessor``.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from docmirror.core.extract.cell_normalizer import normalize_table_cells
from docmirror.core.extract.engine import detect_merged_cells, extract_tables_layered
from docmirror.core.geometry.table_attrs import build_table_geometry_attrs
from docmirror.core.ocr.fallback import analyze_scanned_page
from docmirror.core.segment.zones import _reconstruct_rows_from_chars
from docmirror.models.entities.domain import Block

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)
_clock = time.perf_counter


def handle_data_table_zone(
    extractor: PageExtractor,
    zone,
    _block_id: str,
    page_idx: int,
    page_plum,
    fitz_page,
    fitz_doc,
    reading_order: int,
    is_digital: bool,
    _watermark_filtered: bool,
    _router,
    global_table_template,
    extraction_profile=None,
) -> tuple[list[Block], str, float, float, bool]:
    """Handle a data_table-type zone → Block conversion + PID retry loop.

    Returns:
        (blocks, extraction_layer, extraction_confidence, table_ms, tables_extracted)
    """
    _tbl_t = _clock()
    result_blocks: list[Block] = []

    page_table_template = global_table_template if page_idx > 0 else None
    fast_continuation = bool(
        page_idx > 0
        and page_table_template is not None
        and extraction_profile
        and extraction_profile.is_borderless_ledger()
        and extraction_profile.should_use_bcs()
    )

    # P3-2: Detect merged cells (skip on ledger continuation — borderless rows)
    merged_cells = []
    if not fast_continuation:
        try:
            merged_cells = detect_merged_cells(page_plum, table_zone_bbox=zone.bbox)
        except Exception as exc:
            logger.debug(f"operation: suppressed {exc}")

    page_tables, extraction_layer, extraction_confidence = extract_tables_layered(
        page_plum,
        table_zone_bbox=zone.bbox,
        document_page_count=len(fitz_doc),
        fitz_page=fitz_page,
        watermark_filtered=_watermark_filtered,
        layer_hint=(
            extractor._host._page_state.winning_layer
            if hasattr(extractor._host, "_page_state") and extractor._host._page_state.should_use_hint()
            else None
        ),
        table_template=page_table_template,
        extraction_profile=extraction_profile,
        extraction_audit=getattr(extractor._host, "_extraction_audit", None),
        fast_continuation=fast_continuation,
        audit_page=page_idx + 1,
    )

    page_tables = normalize_table_cells(page_tables, extraction_profile)

    if getattr(extractor._host, "_extraction_audit", None) is not None:
        row_count = len(page_tables[0]) if page_tables and page_tables[0] else 0
        page_no = page_idx + 1
        audit_entry: dict = {
            "layer": extraction_layer,
            "row_count": row_count,
        }
        if row_count == 0:
            audit_entry["loss_reason"] = "no_table_extracted"
        elif row_count <= 1:
            audit_entry["loss_reason"] = "header_only"

        target = None
        for entry in reversed(extractor._host._extraction_audit):
            if entry.get("page") == page_no:
                target = entry
                break
        if target is not None:
            target.update(audit_entry)
        else:
            audit_entry["page"] = page_no
            extractor._host._extraction_audit.append(audit_entry)
    _table_ms = (_clock() - _tbl_t) * 1000
    zone_tables_extracted = False
    ro = reading_order

    for tbl in page_tables:
        if tbl and len(tbl) >= 1:
            zone_tables_extracted = True
            tbl_id = f"blk_{page_idx}_{ro}"
            metadata = {}
            if merged_cells:
                metadata["merged_cells"] = merged_cells
            metadata["extraction_layer"] = extraction_layer
            metadata["extraction_confidence"] = extraction_confidence
            if extraction_profile is not None:
                metadata["table_profile_id"] = getattr(extraction_profile, "profile_id", "")
            metadata["zone_type"] = getattr(zone, "type", "data_table")
            metadata = build_table_geometry_attrs(
                tbl,
                chars=list(getattr(zone, "chars", None) or []),
                table_bbox=zone.bbox,
                page_number=page_idx + 1,
                table_index=len(result_blocks),
                geometry_source=extraction_layer or "table_zone",
                geometry_confidence=extraction_confidence,
                base_attrs=metadata,
            )
            if (
                "geometry_coverage_ratio" in metadata
                and getattr(extractor._host, "_extraction_audit", None) is not None
            ):
                for entry in reversed(extractor._host._extraction_audit):
                    if entry.get("page") == page_idx + 1:
                        entry["geometry_coverage_ratio"] = metadata["geometry_coverage_ratio"]
                        break
            block = Block(
                block_id=tbl_id,
                block_type="table",
                bbox=zone.bbox,
                reading_order=ro,
                page=page_idx + 1,
                raw_content=tbl,
                attrs=metadata,
            )
            result_blocks.append(block)
            ro += 1

    # Perf #11: Update PageState with extraction results
    if zone_tables_extracted and page_tables:
        first_tbl = page_tables[0]
        if first_tbl and len(first_tbl) >= 2:
            if hasattr(extractor._host, "_page_state"):
                extractor._host._page_state.update(
                    header=first_tbl[0],
                    layer=extraction_layer,
                    confidence=extraction_confidence,
                )

    if not zone_tables_extracted:
        fallback_rows = _reconstruct_rows_from_chars(zone.chars)
        if fallback_rows:
            fb_id = f"blk_{page_idx}_{ro}"
            metadata = build_table_geometry_attrs(
                fallback_rows,
                chars=list(getattr(zone, "chars", None) or []),
                table_bbox=zone.bbox,
                page_number=page_idx + 1,
                table_index=len(result_blocks),
                geometry_source="char_reconstruct_fallback",
                geometry_confidence=0.0,
                base_attrs={
                    "extraction_layer": "char_reconstruct_fallback",
                    "extraction_confidence": 0.0,
                    "zone_type": getattr(zone, "type", "data_table"),
                },
            )
            block = Block(
                block_id=fb_id,
                block_type="table",
                bbox=zone.bbox,
                reading_order=ro,
                page=page_idx + 1,
                raw_content=fallback_rows,
                attrs=metadata,
            )
            result_blocks.append(block)
            ro += 1

    # ── PID Loop: Degradation Resampling ──
    logger.debug(
        f"Trace PID Before Block: router={bool(_router)}, zone_tables_extracted={zone_tables_extracted}, page_tables=[{len(page_tables) if page_tables else 0}], extraction_confidence={extraction_confidence}"
    )

    if (
        _router
        and zone_tables_extracted
        and page_tables
        and extraction_confidence < 0.85
        and not (extraction_profile and extraction_profile.skip_pid_resample)
    ):
        original_conf = extraction_confidence
        best_table = page_tables[0]

        # Retry 1: Parameter Shift Resampling (Digital only)
        if is_digital:
            logger.info(
                f"[DocMirror] PID Loop Retry 1: Triggering parameter shift resampling on page {page_idx} (conf={original_conf:.2f})"
            )
            re_tables, re_layer, re_conf = extract_tables_layered(
                page_plum,
                table_zone_bbox=zone.bbox,
                document_page_count=len(fitz_doc),
                fitz_page=fitz_page,
                watermark_filtered=_watermark_filtered,
                layer_hint=None,
                table_template=page_table_template,
                pid_resample=True,
                extraction_profile=extraction_profile,
                fast_continuation=fast_continuation,
            )
            if re_tables and re_conf > original_conf:
                logger.info(
                    f"[DocMirror] PID Loop Retry 1 Success: conf boosted to {re_conf:.2f}. Adopting new parameters."
                )
                best_table = re_tables[0]
                extraction_confidence = re_conf
                for i in range(len(result_blocks) - 1, -1, -1):
                    if result_blocks[i].block_type == "table":
                        result_blocks[i] = Block(
                            block_id=result_blocks[i].block_id,
                            block_type="table",
                            bbox=zone.bbox,
                            reading_order=result_blocks[i].reading_order,
                            page=page_idx + 1,
                            raw_content=best_table,
                        )
                        break

        # Retry 2: Visual Optical Degradation (scanned/non-digital only)
        # Skip OCR degradation for digital PDFs — the native text layer is
        # always more reliable than rendering to image + OCR.
        if (
            not is_digital
            and extraction_confidence < 0.85
            and _router.should_enhance_table(best_table, extraction_confidence)
        ):
            try:
                high_dpi = _router._high_dpi
                logger.warning(
                    f"[DocMirror] PID Loop Retry 2: Total degradation to Vision/OCR "
                    f"on page {page_idx} at {high_dpi} DPI "
                    f"(confidence={extraction_confidence:.2f})"
                )
                re_result = analyze_scanned_page(
                    fitz_page,
                    page_idx,
                    table_bbox=zone.bbox,
                    target_dpi=high_dpi,
                )
                if re_result and re_result.get("table"):
                    re_table = re_result["table"]
                    if len(re_table) >= len(best_table):
                        for i in range(len(result_blocks) - 1, -1, -1):
                            if result_blocks[i].block_type == "table":
                                result_blocks[i] = Block(
                                    block_id=result_blocks[i].block_id,
                                    block_type="table",
                                    bbox=zone.bbox,
                                    reading_order=result_blocks[i].reading_order,
                                    page=page_idx + 1,
                                    raw_content=re_table,
                                )
                                break
                        if hasattr(extractor._host, "_page_state"):
                            extractor._host._page_state.reset()
            except Exception as e:
                logger.debug(f"[DocMirror] Quality Router: OCR Degradation skipped: {e}")
        elif is_digital and extraction_confidence < 0.85:
            logger.debug(
                f"[DocMirror] PID Loop Retry 2: Skipped OCR degradation on page {page_idx} "
                f"(digital document, confidence={extraction_confidence:.2f})"
            )

    return result_blocks, extraction_layer, extraction_confidence, _table_ms, zone_tables_extracted
