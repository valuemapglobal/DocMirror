# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Page worker — multiprocessing entry for digital page extraction.

Purpose: Picklable worker function that extracts one digital page in a child
process for parallel document parsing.

Main components: ``extract_single_page_digital_worker``.

Upstream: ``pipeline.pdf_processor`` parallel page pool.

Downstream: ``PagePipeline`` (in worker process).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docmirror.models.entities.domain import PageLayout
from docmirror.core.pipeline.context import PageExtractionContext
from docmirror.core.pipeline.page_pipeline import PagePipeline


def extract_single_page_digital_worker(
    args: tuple[Any, ...],
) -> tuple[int, PageLayout, list[str], str, float]:
    """
    Worker for thread-pool page extraction (Phase 2).
    Opens path in-thread, uses rule-based layout and no formula engine.
    """
    (
        path,
        page_idx,
        layout_al,
        strategy_params,
        page_quality,
        document_page_count,
        content_type,
        ext_ocr_thr,
        ext_ocr_prov,
        global_grid_x,
        global_table_template,
        extraction_profile,
    ) = args
    import fitz
    import pdfplumber

    from docmirror.core.extraction.extractor import CoreExtractor

    path = str(Path(path).resolve())
    extractor = CoreExtractor(layout_model_path=None)
    extractor._formula_engine = None
    if extraction_profile is not None:
        extractor._extraction_profile = extraction_profile
        extractor._extraction_audit = []
    fitz_doc = fitz.open(path)
    plum_doc = pdfplumber.open(path)
    try:
        page_plum = plum_doc.pages[page_idx]
        fitz_page = fitz_doc[page_idx]
        ctx = PageExtractionContext(
            page_plum=page_plum,
            fitz_page=fitz_page,
            fitz_doc=fitz_doc,
            page_idx=page_idx,
            layout_al=layout_al,
            cleaned_path=Path(path),
            is_digital=True,
            strategy_params=strategy_params or {},
            page_quality=page_quality,
            content_type=content_type,
            global_grid_x=global_grid_x,
            global_table_template=global_table_template,
            extraction_profile=extraction_profile,
        )
        page_layout, ocr_parts, extraction_layer, extraction_confidence = PagePipeline(extractor).run(ctx)
        return (page_idx, page_layout, ocr_parts, extraction_layer, extraction_confidence)
    finally:
        fitz_doc.close()
        plum_doc.close()


__all__ = ["extract_single_page_digital_worker"]
