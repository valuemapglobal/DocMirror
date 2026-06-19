# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Scanned page handler — full-page OCR path for image-only pages.

Purpose: Routes scanned or low-text pages through ``ocr.pipeline.run_scanned_page``
and assembles OCR-derived blocks.

Main components: ``extract_scanned_page``.

Upstream: Quality router scanned/digital-low-text decision.

Downstream: ``ocr.pipeline``, ``ocr.scanned.analyze_page``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from docmirror.models.entities.domain import Block, PageLayout
from docmirror.core.extraction.html_utils import parse_html_tables_to_key_value, strip_html_to_plain_text
from docmirror.core.ocr.fallback import ocr_extract_universal

_strip_html_to_plain_text = strip_html_to_plain_text
_parse_html_tables_to_key_value = parse_html_tables_to_key_value

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)

def extract_scanned_page(extractor: PageExtractor,
    *,
    fitz_page,
    page_idx: int,
    page_quality: int | None = None,
    external_ocr_threshold: int | None = None,
    external_ocr_provider: Any | None = None,
    global_grid_x: list[float] | None = None,  # noqa: ARG001 — reserved for future grid-aware OCR
) -> PageLayout:
    """Single-page OCR extraction for scanned documents.

    Uses ``ocr_extract_universal`` which auto-detects content type:
    - Table documents → existing table block pipeline
    - General documents → text blocks in reading order with real bboxes

    When ``page_quality`` is below ``external_ocr_threshold`` and
    ``external_ocr_provider`` is set, OCR is delegated to the external
    provider (e.g. cloud OCR for 99% recognition on poor-quality scans).
    """
    width = fitz_page.rect.width
    height = fitz_page.rect.height
    blocks: list[Block] = []
    reading_order = 0

    try:
        ocr_result = ocr_extract_universal(
            fitz_page,
            page_idx,
            page_quality=page_quality,
            external_ocr_threshold=external_ocr_threshold,
            external_ocr_provider=external_ocr_provider,
        )

        if ocr_result and isinstance(ocr_result, dict):
            content_type = ocr_result.get("content_type", "table")

            if content_type == "table":
                # ── Table document: existing logic ──
                header_text = ocr_result.get("header_text", "").strip()
                if header_text:
                    blocks.append(
                        Block(
                            block_id=f"blk_{page_idx}_{reading_order}",
                            block_type="text",
                            bbox=(0, 0, width, height * 0.1),
                            reading_order=reading_order,
                            page=page_idx + 1,
                            raw_content=header_text,
                        )
                    )
                    reading_order += 1

                table_data = ocr_result.get("table", [])
                if table_data and len(table_data) >= 2:
                    blocks.append(
                        Block(
                            block_id=f"blk_{page_idx}_{reading_order}",
                            block_type="table",
                            bbox=(0, height * 0.1, width, height * 0.9),
                            reading_order=reading_order,
                            page=page_idx + 1,
                            raw_content=table_data,
                        )
                    )
                    reading_order += 1
                elif table_data:
                    text_lines = [" | ".join(str(c) for c in row if c) for row in table_data if any(c for c in row)]
                    if text_lines:
                        blocks.append(
                            Block(
                                block_id=f"blk_{page_idx}_{reading_order}",
                                block_type="text",
                                bbox=(0, height * 0.1, width, height * 0.9),
                                reading_order=reading_order,
                                page=page_idx + 1,
                                raw_content="\n".join(text_lines),
                            )
                        )
                        reading_order += 1

                footer_text = ocr_result.get("footer_text", "").strip()
                if footer_text:
                    blocks.append(
                        Block(
                            block_id=f"blk_{page_idx}_{reading_order}",
                            block_type="text",
                            bbox=(0, height * 0.9, width, height),
                            reading_order=reading_order,
                            page=page_idx + 1,
                            raw_content=footer_text,
                        )
                    )
                    reading_order += 1

                logger.info(
                    f"[DocMirror] OCR page {page_idx} (table): "
                    f"header={bool(header_text)} "
                    f"table={len(table_data)}rows "
                    f"footer={bool(footer_text)}"
                )

            else:
                # ── General document: text blocks per line ──
                lines = ocr_result.get("lines", [])
                raw_tokens = ocr_result.get("tokens", [])
                page_image = ocr_result.get("_page_image")
                ocr_page_h = ocr_result.get("page_h", 1)
                ocr_page_w = ocr_result.get("page_w", 1)

                # Scale OCR pixel coords → PDF point coords
                sx = width / max(ocr_page_w, 1)
                sy = height / max(ocr_page_h, 1)

                full_text_parts: list[str] = []
                scaled_lines: list[dict[str, Any]] = []
                scaled_tokens: list[Any] = []
                if raw_tokens:
                    try:
                        from docmirror.core.ocr.micro_grid.models import OCRToken

                        for token in raw_tokens:
                            tb = token.get("bbox") if isinstance(token, dict) else getattr(token, "bbox", None)
                            if not tb or len(tb) != 4:
                                continue
                            tx0, ty0, tx1, ty1 = (float(tb[0]), float(tb[1]), float(tb[2]), float(tb[3]))
                            text = str(token.get("text") if isinstance(token, dict) else getattr(token, "text", "") or "").strip()
                            if not text:
                                continue
                            raw_bbox = token.get("raw_bbox") if isinstance(token, dict) else getattr(token, "raw_bbox", None)
                            scaled_tokens.append(
                                OCRToken(
                                    token_id=str(
                                        token.get("token_id")
                                        if isinstance(token, dict)
                                        else getattr(token, "token_id", f"ocr_p{page_idx + 1}_t{len(scaled_tokens)}")
                                    ),
                                    text=text,
                                    bbox=(tx0 * sx, ty0 * sy, tx1 * sx, ty1 * sy),
                                    confidence=float(
                                        token.get("confidence", 1.0)
                                        if isinstance(token, dict)
                                        else getattr(token, "confidence", 1.0)
                                    ),
                                    page=page_idx + 1,
                                    source=str(
                                        token.get("source", "rapidocr") if isinstance(token, dict) else getattr(token, "source", "rapidocr")
                                    ),
                                    coordinate_system="pdf_points_top_left",
                                    raw_bbox=tuple(raw_bbox) if raw_bbox and len(raw_bbox) == 4 else (tx0, ty0, tx1, ty1),
                                    raw_coordinate_system=str(
                                        token.get("raw_coordinate_system", "image_pixels")
                                        if isinstance(token, dict)
                                        else getattr(token, "raw_coordinate_system", "image_pixels")
                                    ),
                                )
                            )
                    except Exception as exc:
                        logger.debug("[DocMirror] OCR token geometry projection skipped: %s", exc)

                for line in lines:
                    text = line.get("text", "").strip()
                    if not text:
                        continue
                    full_text_parts.append(text)
                    ox0, oy0, ox1, oy1 = line.get("bbox", (0, 0, 0, 0))
                    bbox = (ox0 * sx, oy0 * sy, ox1 * sx, oy1 * sy)
                    scaled_lines.append({
                        "content": text,
                        "bbox": list(bbox),
                        "confidence": float(line.get("confidence", 1.0) or 1.0),
                    })
                    # If content is HTML (e.g. external OCR), store plain text in block.
                    # Drop table segments so tables appear only in key_value block, not duplicated as text.
                    if "<table" in text.lower() or "<td" in text.lower():
                        text = _strip_html_to_plain_text(text, drop_tables=True)
                    blocks.append(
                        Block(
                            block_id=f"blk_{page_idx}_{reading_order}",
                            block_type="text",
                            bbox=bbox,
                            reading_order=reading_order,
                            page=page_idx + 1,
                            raw_content=text,
                        )
                    )
                    reading_order += 1

                if scaled_lines:
                    from docmirror.core.ocr.page_canvas.detect import detect_page_region_candidates
                    from docmirror.core.ocr.page_canvas.evidence_bundles import upsert_page_evidence_bundle

                    region_detect = {
                        "region_detect_candidates": [
                            {
                                "candidate_id": cand.candidate_id,
                                "kind": cand.kind,
                                "bbox": list(cand.bbox),
                                "score": cand.score,
                                "reason_codes": list(cand.reason_codes),
                            }
                            for cand in detect_page_region_candidates(
                                scaled_lines,
                                tokens=scaled_tokens,
                                page=page_idx + 1,
                                page_width=width,
                                page_height=height,
                            )
                        ],
                    }
                    micro_grid_evidence = {
                        "page": page_idx + 1,
                        "page_width": width,
                        "page_height": height,
                        "lines": scaled_lines,
                        "tokens": [token.to_dict() for token in scaled_tokens],
                        "source": "scanned_page_ocr",
                    }
                    local_structure_evidence = None
                    try:
                        from docmirror.core.ocr.local_structure import extract_local_structure_evidence

                        local_structure = extract_local_structure_evidence(
                            scaled_lines,
                            tokens=scaled_tokens,
                            page=page_idx + 1,
                            page_width=width,
                            page_height=height,
                            page_image=page_image,
                            enable_region_ocr=page_image is not None,
                        )
                        if local_structure.get("candidates") or local_structure.get("structures"):
                            local_structure_evidence = {
                                "page": page_idx + 1,
                                "page_width": width,
                                "page_height": height,
                                "lines": scaled_lines,
                                "tokens": [token.to_dict() for token in scaled_tokens],
                                "source": "scanned_page_ocr",
                                "candidates": local_structure.get("candidates") or [],
                                "structures": local_structure.get("structures") or [],
                                "audit": local_structure.get("audit") or {},
                            }
                    except Exception as exc:
                        logger.debug("[DocMirror] scanned local structure evidence skipped: %s", exc)

                    upsert_page_evidence_bundle(
                        extractor._host,
                        page=page_idx + 1,
                        page_width=width,
                        page_height=height,
                        micro_grid_evidence=micro_grid_evidence,
                        local_structure_evidence=local_structure_evidence,
                        region_detect=region_detect,
                    )
                    try:
                        from docmirror.core.ocr.micro_grid.materialize import extract_micro_grid_structures
                        from docmirror.core.ocr.page_canvas.evidence_bundles import merge_micro_grid_structures_into_host

                        micro_grids = extract_micro_grid_structures(
                            scaled_lines,
                            tokens=scaled_tokens,
                            page=page_idx + 1,
                            page_width=width,
                            page_height=height,
                            page_image=page_image,
                            enable_cell_ocr=False,
                        )
                        if micro_grids:
                            merge_micro_grid_structures_into_host(extractor._host, micro_grids)
                    except Exception as exc:
                        logger.debug("[DocMirror] scanned micro-grid materialize skipped: %s", exc)

                    try:
                        from docmirror.core.ocr.page_canvas.morphology_orchestrator import write_detect_audit_to_bundle

                        bundles = getattr(extractor._host, "_page_evidence_bundles", [])
                        page_bundle = next(
                            (b for b in bundles if isinstance(b, dict) and int(b.get("page") or 0) == page_idx + 1),
                            None,
                        )
                        if page_bundle is not None:
                            write_detect_audit_to_bundle(page_bundle)
                    except Exception as exc:
                        logger.debug("[DocMirror] scanned MO detect audit skipped: %s", exc)

                # When external OCR returns HTML <table>, parse to key_value block
                full_text = "\n\n".join(full_text_parts)
                kv = _parse_html_tables_to_key_value(full_text)
                if kv:
                    blocks.append(
                        Block(
                            block_id=f"blk_{page_idx}_{reading_order}",
                            block_type="key_value",
                            bbox=(0, 0, width, height),
                            reading_order=reading_order,
                            page=page_idx + 1,
                            raw_content=kv,
                        )
                    )
                    reading_order += 1
                    logger.debug(
                        f"[DocMirror] OCR page {page_idx} (general): parsed table → key_value with {len(kv)} pairs"
                    )

                logger.info(f"[DocMirror] OCR page {page_idx} (general): {len(lines)} text lines extracted")

    except Exception as e:
        logger.warning(f"[DocMirror] OCR failed on page {page_idx}: {e}")

    return PageLayout(
        page_number=page_idx + 1,
        blocks=tuple(blocks),
        is_scanned=True,
    )
