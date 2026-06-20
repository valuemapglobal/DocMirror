# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
CoreExtractor — orchestrates PDF → BaseResult extraction.

Purpose: Main extraction engine: opens PDFs, iterates pages, runs layout
segmentation, table extraction (layered tiers), OCR fallback for scanned
pages, logical table composition, and assembles frozen ``BaseResult``.

Main components: ``CoreExtractor``.

Upstream: ``entry.factory``, ``FitzEngine``, ``analyze.pre_analyzer``.

Downstream: ``pipeline.document_pipeline``, ``bridge.parse_result_bridge``,
``extraction.table_postprocessor``.
"""

from __future__ import annotations

import logging
import time
import uuid

# S2: Module-level alias — perf_counter avoids gettimeofday syscall
_clock = time.perf_counter
from pathlib import Path
from typing import Any

from docmirror.core.entry.exceptions import ExtractionError

from ...models.entities.domain import BaseResult
from ..extract.classifier import get_last_layer_timings
from ..pipeline.context import PageExtractionContext
from ..utils.vocabulary import _is_header_row
from ..utils.watermark import preprocess_document
from .entity_collector import collect_kv_entities
from .foundation import FitzEngine
from .image_converter import image_to_virtual_pdf
from .table_postprocessor import process_page_tables

logger = logging.getLogger(__name__)


class CoreExtractor:
    """
    Core extractor — generates immutable BaseResult from PDF.

    Usage::

        extractor = CoreExtractor()
        result = await extractor.extract(Path("sample.pdf"))
        # result is frozen BaseResult, immutable

    All low-level functions come from MultiModal.core submodules (self-contained).
    """

    def __init__(
        self,
        seal_detector_fn=None,
        layout_model_path: str | None = None,
        max_page_concurrency: int | None = None,
        formula_model_path: str | None = None,
        model_render_dpi: int = 200,
    ):
        """
        Args:
            seal_detector_fn: Optional seal detection callback function.
                Signature: (fitz_doc) -> Optional[Dict[str, Any]]
                When None, skips seal detection.
            layout_model_path: Optional DocLayout-YOLO ONNX model path.
                Set to "auto" to auto-download from HuggingFace.
                When None, uses rule-based fallback.
            max_page_concurrency: Page-level concurrency.
                pdfplumber/PyMuPDF shared doc object, current default is 1 (sequential).
                Set >1 to use ThreadPoolExecutor for parallel extraction.
            formula_model_path: Optional formula recognition ONNX model path (UniMERNet).
                When None, falls back to rapid_latex_ocr -> empty string.
            model_render_dpi: Page rendering DPI for DocLayout-YOLO model inference.
                Default 200; higher values improve layout detection precision but increase inference time.
        """
        from docmirror.configs.runtime.performance import resolve_max_page_concurrency

        self._seal_detector_fn = seal_detector_fn
        self._layout_detector = None
        self._max_page_concurrency = resolve_max_page_concurrency(max_page_concurrency)
        self._model_render_dpi = model_render_dpi

        # Formula recognition engine (Strategy pattern: UniMERNet ONNX > rapid_latex_ocr > empty)
        from ..ocr.formula_engine import FormulaEngine

        self._formula_engine = FormulaEngine(model_path=formula_model_path)

        if layout_model_path:
            try:
                from ..segment.layout_model import LayoutDetector

                # layout_model_path acts as model type name
                # "auto" -> default doclayout_docstructbench
                model_type = "doclayout_docstructbench" if layout_model_path == "auto" else layout_model_path
                self._layout_detector = LayoutDetector(model_type=model_type)
                logger.info("[DocMirror] Layout model enabled (RapidLayout)")
            except Exception as e:
                logger.warning(f"[DocMirror] Layout model init failed, falling back to rules: {e}")

    # Supported image formats
    _IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"})

    @staticmethod
    def _image_to_virtual_pdf(image_path: Path) -> fitz.Document:
        """Convert image to a virtual single-page PDF, pre-scaling large images to max 4096px."""
        return image_to_virtual_pdf(image_path)

    async def extract(self, file_path: Path, *, options: dict | None = None) -> BaseResult:
        """
        Main entry point: extract BaseResult from PDF or image.

        Delegates document-level orchestration to ``DocumentPipeline`` (CPA design 12).
        """
        from ..pipeline.document_pipeline import DocumentPipeline

        file_path = Path(file_path)
        doc_id = str(uuid.uuid4())
        logger.info(f"[DocMirror] ▶ extract | file={file_path.name}")
        try:
            return await DocumentPipeline(self).run(file_path, doc_id=doc_id, options=options or {})
        except ExtractionError as e:
            logger.error(f"[DocMirror] extraction error: {e}", exc_info=True)
            return BaseResult(
                document_id=doc_id,
                metadata={"error": str(e), "error_type": "ExtractionError", "parser": "DocMirror_CoreExtractor"},
                full_text="",
            )
        except Exception as e:
            logger.error(f"[DocMirror] unexpected error: {e}", exc_info=True)
            return BaseResult(
                document_id=doc_id,
                metadata={"error": str(e), "error_type": type(e).__name__, "parser": "DocMirror_CoreExtractor"},
                full_text="",
            )

    async def extract_parse_result(self, file_path: Path, *, options: dict | None = None) -> ParseResult:
        """
        Single bridge point: CoreExtractor → ParseResult (MOC Path B).

        Prefer this over ``extract()`` + manual ``ParseResultBridge.from_base_result()``
        in adapters (design 09 §5 Phase 1).
        """
        from docmirror.core.bridge.parse_result_bridge import ParseResultBridge

        base_result = await self.extract(file_path, options=options or {})
        return ParseResultBridge.from_base_result(base_result)

    async def _open_document(self, file_path: Path) -> fitz.Document:
        """Open a document (PDF or image). Returns the PyMuPDF document."""
        import asyncio

        is_image = file_path.suffix.lower() in self._IMAGE_SUFFIXES
        if is_image:
            fitz_doc = await asyncio.to_thread(self._image_to_virtual_pdf, file_path)
            logger.info("[DocMirror] Image input -> virtual PDF, marked as scanned document")
            return fitz_doc

        cleaned_path = await asyncio.to_thread(preprocess_document, file_path)
        fitz_doc = await asyncio.to_thread(FitzEngine.open, cleaned_path)
        has_text = await asyncio.to_thread(FitzEngine.has_text_layer, fitz_doc)
        if not has_text:
            logger.info("[DocMirror] Text layer missing, marked as scanned document")
        return fitz_doc

    async def _run_extraction(
        self, fitz_doc: fitz.Document, file_path: Path, doc_id: str, options: dict | None = None
    ) -> BaseResult:
        """Core extraction logic, extracted from try block.

        Steps:
          1. Pre-analysis
          2. CPU-bound parsing (in thread)
          3. Assemble BaseResult
        """
        import asyncio

        t0 = _clock()
        file_path = Path(file_path)
        is_image_input = file_path.suffix.lower() in self._IMAGE_SUFFIXES
        self._page_evidence_bundles = []

        # Step 1.5: Pre-analysis
        from docmirror.core.analyze.pre_analyzer import PreAnalyzer

        pre_analysis = await asyncio.to_thread(PreAnalyzer().analyze, fitz_doc)

        # Step 2-5: CPU-bound parsing (layout, page extraction, tables, post-processing)
        pages, full_text, extraction_layer, extraction_confidence, _perf, _page_perf = await asyncio.to_thread(
            self._process_pdf_sync,
            fitz_doc=fitz_doc,
            pre_analysis=pre_analysis,
            has_text=fitz_doc is not None,  # has_text is known from _open_document
            is_image_input=is_image_input,
            cleaned_path=None,  # _process_pdf_sync handles this internally
            file_path=file_path,
            options=options or {},
        )

        # Step 6: Assemble BaseResult
        elapsed = (_clock() - t0) * 1000
        total_blocks = sum(len(p.blocks) for p in pages)
        table_count = sum(1 for p in pages for b in p.blocks if b.block_type == "table")
        extracted_entities = self._collect_kv_entities(pages)

        # Seal detection (optional, DI)
        seal_info = None
        if self._seal_detector_fn:
            try:
                seal_info = self._seal_detector_fn(fitz_doc)
            except Exception as e:
                logger.debug(f"[DocMirror] Seal detection skip: {e}")

        # Extract logical tables from _perf before it's nested
        _logical_tables_data = _perf.pop("_logical_tables", None) if isinstance(_perf, dict) else None

        metadata: dict[str, Any] = {
            "file_name": file_path.name,
            "file_size": file_path.stat().st_size,  # L2 guarantees file exists
            "page_count": len(pages),
            "source_page_count": _perf.get("source_page_count"),
            "processed_page_numbers": _perf.get("selected_pages") or [p.page_number for p in pages],
            "document_scene": getattr(self, "_document_scene", None) or _perf.get("document_scene", "unknown"),
            "scene_confidence": getattr(self, "_scene_confidence", 0.0) or _perf.get("scene_confidence", 0.0),
            "layout_profile_id": _perf.get("layout_profile_id"),
            "quarantined_tables": _perf.get("quarantined_tables") or [],
            "parser": "DocMirror_CoreExtractor",
            "elapsed_ms": round(elapsed, 1),
            "block_count": total_blocks,
            "table_count": table_count,
            "has_text_layer": fitz_doc is not None,
            "scanned_pages": [p.page_number for p in pages if p.is_scanned],
            "pre_analysis": pre_analysis.to_dict(),
            "extracted_entities": extracted_entities,
            "perf_breakdown": _perf,
            "perf_per_page": _page_perf,
        }
        opts = dict(options or {})
        parse_control = opts.get("parse_control")
        parse_control_dict = opts.get("parse_control_dict")
        if parse_control_dict is None and parse_control is not None and hasattr(parse_control, "to_dict"):
            parse_control_dict = parse_control.to_dict()
        if parse_control_dict:
            metadata["parse_control"] = parse_control_dict
            metadata["parse_control_fingerprint"] = opts.get("parse_control_fingerprint") or (
                parse_control.fingerprint()
                if parse_control is not None and hasattr(parse_control, "fingerprint")
                else ""
            )
            pages_control = parse_control_dict.get("pages") if isinstance(parse_control_dict, dict) else {}
            if isinstance(pages_control, dict):
                metadata["selected_pages"] = pages_control
        if opts.get("doc_type_hint"):
            metadata["doc_type_hint"] = opts.get("doc_type_hint")
            metadata["doc_type_hint_strength"] = opts.get("doc_type_hint_strength") or "prefer"
        stage_timings = getattr(self, "_page_stage_timings", None)
        if stage_timings:
            metadata["perf_stage_timings"] = stage_timings

        # Pass logical tables to bridge layer via metadata
        if _logical_tables_data:
            metadata["_logical_tables"] = _logical_tables_data

        ltqg_summary = getattr(self, "_ltqg_summary", None)
        if ltqg_summary:
            metadata["ltqg"] = ltqg_summary

        quarantined_logical = getattr(self, "_quarantined_logical_tables", None)
        if quarantined_logical:
            metadata["quarantined_logical_tables"] = quarantined_logical

        section_tree = _perf.pop("_section_tree", None)
        if section_tree:
            metadata["sections"] = section_tree
        if seal_info:
            metadata["seal_info"] = seal_info
        page_evidence_bundles = getattr(self, "_page_evidence_bundles", None)
        if page_evidence_bundles:
            metadata["page_evidence_bundles"] = list(page_evidence_bundles)

        if table_count > 0:
            metadata["extraction_quality"] = self._assess_extraction_quality(
                pages, extraction_layer, extraction_confidence
            )

        metadata["structure"] = self._build_structure_metadata(
            pre_analysis=pre_analysis,
            fitz_doc=fitz_doc,
            table_count=table_count,
            extraction_layer=extraction_layer,
            layout_profile_id=_perf.get("layout_profile_id"),
            pipe_table_enrich=bool(_perf.get("pipe_table_enrich")),
            logical_table_count=len(_logical_tables_data) if _logical_tables_data else None,
            physical_table_count=table_count,
            dual_view=_perf.get("dual_view") if isinstance(_perf, dict) else None,
            ltqg_summary=_perf.get("ltqg") if isinstance(_perf, dict) else None,
        )

        result = BaseResult(
            document_id=doc_id,
            pages=tuple(pages),
            metadata=metadata,
            full_text=full_text,
        )

        logger.info(
            f"[DocMirror] ◀ extract | pages={len(pages)} | blocks={total_blocks} | "
            f"tables={table_count} | elapsed={elapsed:.0f}ms"
        )
        return result

    @staticmethod
    def _build_structure_metadata(
        *,
        pre_analysis,
        fitz_doc,
        table_count: int,
        extraction_layer: str,
        layout_profile_id: str | None,
        pipe_table_enrich: bool = False,
        logical_table_count: int | None = None,
        physical_table_count: int | None = None,
        dual_view: bool | None = None,
        ltqg_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build SPE dict for parser_info.structure (ADR-M13-02)."""
        from docmirror.core.analyze.structure_provenance import (
            apply_logical_tables_spe,
            apply_pipe_enrich_spe,
            build_structure_provenance,
        )
        from docmirror.core.analyze.structure_signals import build_sso_sample_text

        sample_text = build_sso_sample_text(fitz_doc) if fitz_doc is not None else ""

        def _with_logical_tables(spe_dict: dict[str, Any]) -> dict[str, Any]:
            return apply_logical_tables_spe(
                spe_dict,
                logical_table_count=logical_table_count,
                physical_table_count=physical_table_count,
                dual_view=dual_view,
                ltqg_summary=ltqg_summary,
            )

        structural = getattr(pre_analysis, "structure_spe", None)
        if structural:
            out = dict(structural)
            out["extraction_layer"] = extraction_layer
            out["layout_profile_id"] = layout_profile_id
            if pipe_table_enrich:
                return _with_logical_tables(apply_pipe_enrich_spe(out))
            if table_count > 0:
                out["table_extraction"] = "full"
                out["table_extraction_skipped_reason"] = None
            elif out.get("table_extraction") == "full" and table_count == 0:
                out["table_extraction_skipped_reason"] = (
                    out.get("table_extraction_skipped_reason") or "extraction_failed"
                )
            return _with_logical_tables(out)

        spe = build_structure_provenance(
            content_type=getattr(pre_analysis, "content_type", "unknown"),
            sample_text=sample_text,
            table_count=table_count,
            extraction_layer=extraction_layer,
            layout_profile_id=layout_profile_id,
            table_extraction="enrich_only" if pipe_table_enrich else None,
        )
        if pipe_table_enrich:
            return _with_logical_tables(apply_pipe_enrich_spe(spe.to_dict()))
        return _with_logical_tables(spe.to_dict())

    def _assess_extraction_quality(self, pages, extraction_layer: str, extraction_confidence: float) -> dict[str, Any]:
        """Assess extraction quality for the main table."""
        table_count = sum(1 for p in pages for b in p.blocks if b.block_type == "table")
        if table_count == 0:
            return {"extraction_layer": extraction_layer, "extraction_confidence": extraction_confidence}

        # Find main table (largest table block)
        main_table = None
        for p in pages:
            for b in p.blocks:
                if b.block_type == "table" and isinstance(b.raw_content, list):
                    if main_table is None or len(b.raw_content) > len(main_table):
                        main_table = b.raw_content

        header_detected = False
        data_row_count = 0
        col_count_stable = True
        empty_cell_ratio = 0.0

        if main_table and len(main_table) >= 2:
            header_detected = _is_header_row(main_table[0])
            data_row_count = len(main_table) - 1
            expected_cols = len(main_table[0])
            col_count_stable = all(len(row) == expected_cols for row in main_table)
            total_cells = sum(len(row) for row in main_table)
            empty_cells = sum(1 for row in main_table for c in row if not (c or "").strip())
            empty_cell_ratio = round(empty_cells / max(1, total_cells), 3)

        return {
            "extraction_layer": extraction_layer,
            "extraction_confidence": extraction_confidence,
            "header_detected": header_detected,
            "data_row_count": data_row_count,
            "col_count_stable": col_count_stable,
            "empty_cell_ratio": empty_cell_ratio,
            "layer_timings_ms": get_last_layer_timings(),
        }

    def _process_pdf_sync(
        self, fitz_doc, pre_analysis, has_text, is_image_input, cleaned_path, file_path, options=None
    ):
        """Delegate to ``PdfSyncProcessor`` (CPA design 12)."""
        from docmirror.core.pipeline.document_pipeline import DocumentPipeline
        from docmirror.core.pipeline.pdf_processor import PdfSyncProcessor

        return PdfSyncProcessor(self, DocumentPipeline(self)).process(
            fitz_doc, pre_analysis, has_text, is_image_input, cleaned_path, file_path, options=options or {}
        )

    def _extract_page(self, ctx: PageExtractionContext):
        """Backward-compatible delegate to ``PageExtractor.run``."""
        from docmirror.core.pipeline.page_extractor import PageExtractor

        return PageExtractor(self).run(ctx)

    def _extract_scanned_page(self, **kwargs):
        from docmirror.core.pipeline.page_extractor import PageExtractor

        return PageExtractor(self).extract_scanned_page(**kwargs)

    def _collect_kv_entities(self, pages):
        return collect_kv_entities(pages)

    def _post_process_tables(self, pages, extraction_profile=None):
        return process_page_tables(pages, extraction_profile=extraction_profile)
