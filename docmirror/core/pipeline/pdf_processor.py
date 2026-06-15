# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
PDF sync processor — synchronous multi-page extraction with optional parallelism.

Purpose: Drives the page iteration loop, attaches stage timings, and
coordinates worker pools for large digital PDFs.

Main components: ``PdfSyncProcessor``, ``_attach_stage_timings``.

Upstream: ``CoreExtractor.extract_sync``.

Downstream: ``PagePipeline``, ``page_worker``.
"""

from __future__ import annotations

import contextvars
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from docmirror.models.entities.domain import Block, PageLayout
from docmirror.core.segment.zones import (
    analyze_document_layout,
    analyze_document_layout_parallel,
    segment_page_into_zones,
)
from docmirror.core.extract.engine import extract_tables_layered
from docmirror.core.extract.grid_tensor import build_global_grid_tensor
from docmirror.core.extract.segmentation import segment_page_for_extraction
from docmirror.core.extract.template_injector import build_global_template
from docmirror.core.pipeline.context import DocumentPipelineContext, PageExtractionContext
from docmirror.core.pipeline.document_pipeline import DocumentPipeline
from docmirror.core.pipeline.page_extractor import PageExtractor
from docmirror.core.pipeline.page_pipeline import PagePipeline
from docmirror.core.pipeline.profiler import merge_page_stage_timings
from docmirror.core.pipeline.page_worker import extract_single_page_digital_worker

if TYPE_CHECKING:
    from docmirror.core.extraction.extractor import CoreExtractor

logger = logging.getLogger(__name__)
_clock = time.perf_counter

_active_pdf_processor: contextvars.ContextVar["PdfSyncProcessor | None"] = contextvars.ContextVar(
    "active_pdf_processor",
    default=None,
)


def reenter_generic_pipeline(fitz_doc, pre_analysis):
    """Re-enter generic CPS from a thin strategy wrapper (Phase 4)."""
    from docmirror.core.extraction.strategies.strategy_registry import _bypass_content_type

    proc = _active_pdf_processor.get()
    if proc is None:
        raise RuntimeError("reenter_generic_pipeline called without active PdfSyncProcessor")
    has_text, is_image_input, cleaned_path, file_path = proc._process_ctx
    token = _bypass_content_type.set(pre_analysis.content_type)
    try:
        return proc.process(
            fitz_doc,
            pre_analysis,
            has_text,
            is_image_input,
            cleaned_path,
            file_path,
        )
    finally:
        _bypass_content_type.reset(token)


class PdfSyncProcessor:
    """CPU-bound PDF processing (formerly CoreExtractor._process_pdf_sync)."""

    def __init__(self, host: "CoreExtractor", doc_pipeline: DocumentPipeline | None = None) -> None:
        self._host = host
        self._doc_pipeline = doc_pipeline or DocumentPipeline(host)

    def process(
        self,
        fitz_doc,
        pre_analysis,
        has_text: bool,
        is_image_input: bool,
        cleaned_path,
        file_path,
    ):
        """CPU-bound core: layout analysis → per-page extraction → post-processing.

        Runs in a thread via ``asyncio.to_thread()`` to avoid blocking the
        event loop.  Extracted from the ``extract()`` method to de-nest the
        closure and enable independent testing.

        Returns:
            ``(pages, full_text, extraction_layer, extraction_confidence,
            _perf, _page_perf)`` 6-tuple.
        """
        # === Strategy Registry: route by structural content_type ===
        from docmirror.core.extraction.strategies.strategy_registry import get_strategy

        # Import to trigger @register_strategy decorators
        import docmirror.core.extraction.strategies.section_driven  # noqa: F401
        import docmirror.core.extraction.strategies.table_led  # noqa: F401
        import docmirror.core.extraction.strategies.scanned  # noqa: F401
        import docmirror.core.extraction.strategies.mixed  # noqa: F401
        import docmirror.core.extraction.strategies.text_dominant  # noqa: F401

        self._process_ctx = (has_text, is_image_input, cleaned_path, file_path)
        proc_token = _active_pdf_processor.set(self)
        try:
            strategy = get_strategy(pre_analysis.content_type)
            if strategy is not None:
                logger.info(
                    f"[DocMirror] Strategy Registry → {strategy.__class__.__name__} "
                    f"(content_type={pre_analysis.content_type})"
                )
                return strategy.extract(fitz_doc, pre_analysis)

            # === Generic pipeline (unchanged) ===
            return self._run_generic_pipeline(
                fitz_doc,
                pre_analysis,
                has_text,
                is_image_input,
                cleaned_path,
                file_path,
            )
        finally:
            _active_pdf_processor.reset(proc_token)

    def _run_generic_pipeline(
        self,
        fitz_doc,
        pre_analysis,
        has_text: bool,
        is_image_input: bool,
        cleaned_path,
        file_path,
    ):
        """Generic CPS path (table/scanned/mixed documents)."""
        # ── Per-step timing instrumentation ──
        _perf: dict[str, float] = {}
        _page_perf: list = []  # per-page timing breakdown
        self._host._page_stage_timings = []

        # Derived: plumber_path for pdfplumber
        plumber_path = cleaned_path if cleaned_path else file_path

        # === Step 2: Layout analysis (parallel when max_page_concurrency > 1 and path available) ===
        _t = _clock()
        num_pages = len(fitz_doc)
        use_parallel_layout = (
            self._host._max_page_concurrency > 1 and not is_image_input and cleaned_path is not None and num_pages >= 4
        )
        if use_parallel_layout:
            layout_path = str(Path(cleaned_path).resolve())
            env_layout = int(os.environ.get("DOCMIRROR_LAYOUT_MAX_WORKERS", "0"))
            layout_workers = (
                min(num_pages, env_layout)
                if env_layout > 0
                else min(self._host._max_page_concurrency, num_pages, os.cpu_count() or 4)
            )
            if layout_workers <= 1:
                page_layouts_al = analyze_document_layout(fitz_doc)
            else:
                page_layouts_al = analyze_document_layout_parallel(layout_path, num_pages, max_workers=layout_workers)
        else:
            page_layouts_al = analyze_document_layout(fitz_doc)
        _perf["layout_analysis_ms"] = (_clock() - _t) * 1000

        # Extract full text (with per-page caching to avoid redundant calls)
        _page_text_cache: dict[int, str] = {}
        full_text_parts = []
        for p_idx, page in enumerate(fitz_doc):
            txt = page.get_text()
            _page_text_cache[p_idx] = txt
            full_text_parts.append(txt)
        full_text_raw = "\n\n".join(full_text_parts)
        # Delay NFKC: only normalize at assembly time, not eagerly
        full_text = full_text_raw

        # === Step 1.5: Global scene + layout profile (DocumentPipeline Step 0) ===
        _title_text = _page_text_cache.get(0, "") or full_text_raw[:5000]
        pipeline_ctx = DocumentPipelineContext(
            file_path=Path(file_path),
            pre_analysis=pre_analysis,
            fitz_doc=fitz_doc,
        )
        self._host._pipeline_ctx = pipeline_ctx
        _extraction_profile = self._doc_pipeline.bind_profile(
            full_text_raw=full_text_raw,
            num_pages=num_pages,
            pre_analysis=pre_analysis,
            title_text=_title_text,
        )
        pipeline_ctx.profile = _extraction_profile
        _scene_resolution_scene = getattr(self._host, "_document_scene", "unknown")
        _scene_resolution_conf = getattr(self._host, "_scene_confidence", 0.0)
        _perf["layout_profile_id"] = _extraction_profile.profile_id
        _perf["document_scene"] = _scene_resolution_scene
        _perf["scene_confidence"] = _scene_resolution_conf

        # === Step 3: Per-page extraction -- Zone -> Block ===
        # P0: Per-page hybrid routing — each page individually assessed
        # P1: Smart early-exit — honor DOCMIRROR_MAX_PAGES at core layer
        pages: list[PageLayout] = []
        ocr_text_parts: list[str] = []
        extraction_layer: str = "unknown"  # last strategy layer used by extract_tables_layered
        extraction_confidence: float = 0.0  # last extraction confidence

        max_pages = int(os.environ.get("DOCMIRROR_MAX_PAGES", "0"))

        # Per-page text presence detection (>50 chars = has text layer)
        # Use cached text from above
        _TEXT_THRESHOLD = 50
        page_has_text = []
        for p_idx in range(len(fitz_doc)):
            txt = _page_text_cache.get(p_idx, "")
            page_has_text.append(len(txt.strip()) > _TEXT_THRESHOLD)

        hybrid_doc = has_text and not all(page_has_text)
        if hybrid_doc:
            scanned_indices = [i for i, v in enumerate(page_has_text) if not v]
            logger.info(
                f"[DocMirror] Hybrid document detected: "
                f"{len(scanned_indices)} scanned pages out of {len(page_has_text)}"
            )

        # Open pdfplumber once for all digital pages
        import pdfplumber

        plumber_doc = None
        if has_text or hybrid_doc:
            plumber_doc = pdfplumber.open(str(plumber_path))

        # External OCR: resolve once for all scanned pages (quality < threshold → delegate)
        from docmirror.configs.runtime.settings import default_settings
        from docmirror.core.ocr.fallback import _resolve_external_ocr_provider

        _ext_ocr_threshold = getattr(default_settings, "external_ocr_quality_threshold", None)
        _ext_ocr_provider = _resolve_external_ocr_provider(getattr(default_settings, "external_ocr_provider", None))

        # -- Phase 1.5: Build Global Grid Tensor (skip for borderless oracle profiles — saves ~10s on 219pp) --
        global_grid_x = None
        if plumber_doc and _extraction_profile.needs_global_grid_tensor():
            try:
                _gt0 = _clock()
                # Extract chars from all digital pages (limit to first 50)
                max_tensor_pages = min(len(plumber_doc.pages), 50)
                all_chars = []
                max_w = 0
                for pid in range(max_tensor_pages):
                    if page_has_text[pid]:
                        p = plumber_doc.pages[pid]
                        all_chars.append(p.chars)
                        if getattr(p, "width", 0) > max_w:
                            max_w = p.width
                if all_chars and max_w > 0:
                    global_grid_x = build_global_grid_tensor(all_chars, max_w, resolution=1.0)
                logger.debug(f"[DocMirror] Global grid tensor built in {(_clock() - _gt0) * 1000:.1f}ms")
            except Exception as e:
                logger.warning(f"[DocMirror] Failed to build global grid tensor: {e}")

        # -- Phase 1.8: Golden Page Template Sampling (Graph-Propagated Injection) --
        global_table_template = None
        if (
            plumber_doc
            and len(fitz_doc) >= 3
            and _extraction_profile.enable_grid_template
        ):
            try:
                sample_idx = 1 if len(fitz_doc) > 1 else 0
                if page_has_text[sample_idx]:
                    sp_t0 = _clock()
                    sample_plum = plumber_doc.pages[sample_idx]
                    sample_fitz = fitz_doc[sample_idx]
                    sample_zones = segment_page_for_extraction(
                        sample_plum, sample_idx, _extraction_profile
                    )

                    table_zone = None
                    for z in sample_zones:
                        if z.type == "data_table":
                            table_zone = z
                            break

                    if table_zone:
                        stabs, slayer, sconf = extract_tables_layered(
                            sample_plum,
                            table_zone_bbox=table_zone.bbox,
                            document_page_count=len(fitz_doc),
                            fitz_page=sample_fitz,
                            extraction_profile=_extraction_profile,
                        )
                        if stabs and len(stabs[0]) >= 2 and (
                            sconf >= 0.85 or _extraction_profile.is_borderless_ledger()
                        ):
                            logger.info(
                                "[DocMirror] Golden Page Sampling: page %d layer=%s conf=%.2f → GlobalTableTemplate",
                                sample_idx,
                                slayer,
                                sconf,
                            )
                            crop_x0, crop_x1 = 0, sample_plum.width
                            y0, y1 = table_zone.bbox[1], table_zone.bbox[3]
                            work_page = sample_plum.crop((crop_x0, y0, crop_x1, y1))
                            global_table_template = build_global_template(work_page, stabs[0])

                    logger.debug(
                        "[DocMirror] Golden Page Sampling finished in %.1fms",
                        (_clock() - sp_t0) * 1000,
                    )
            except Exception as e:
                logger.warning(f"[DocMirror] Golden Page Template Sampling failed: {e}")
        elif (
            plumber_doc
            and len(fitz_doc) >= 3
            and _extraction_profile.profile_id == "generic"
        ):
            # Legacy template sampling — generic docs only (EPO profiles use enable_grid_template branch)
            try:
                # Sample the very middle page
                sample_idx = len(fitz_doc) // 2
                if page_has_text[sample_idx]:
                    sp_t0 = _clock()
                    sample_plum = plumber_doc.pages[sample_idx]
                    sample_fitz = fitz_doc[sample_idx]

                    # Do a quick full layout segmentation on the sample page to get the table zone
                    # segment_page_into_zones already imported at module level
                    sample_zones = segment_page_into_zones(sample_plum, sample_idx)

                    table_zone = None
                    for z in sample_zones:
                        if z.type == "data_table":
                            table_zone = z
                            break

                    if table_zone:
                        stabs, slayer, sconf = extract_tables_layered(
                            sample_plum,
                            table_zone_bbox=table_zone.bbox,
                            document_page_count=len(fitz_doc),
                            fitz_page=sample_fitz,
                        )
                        if sconf >= 0.85 and stabs and len(stabs[0]) >= 2:
                            logger.info(
                                f"[DocMirror] Golden Page Sampling: page {sample_idx} yielded confidence {sconf:.2f}. Building GlobalTableTemplate."
                            )
                            crop_x0, crop_x1 = 0, sample_plum.width
                            y0, y1 = table_zone.bbox[1], table_zone.bbox[3]
                            work_page = sample_plum.crop((crop_x0, y0, crop_x1, y1))
                            global_table_template = build_global_template(work_page, stabs[0])

                    logger.debug(f"[DocMirror] Golden Page Sampling finished in {(_clock() - sp_t0) * 1000:.1f}ms")
            except Exception as e:
                logger.warning(f"[DocMirror] Golden Page Template Sampling failed: {e}")

        num_digital = sum(1 for i in range(len(page_has_text)) if page_has_text[i])
        use_page_concurrency = self._host._max_page_concurrency > 1 and plumber_doc is not None and num_digital >= 2
        if use_page_concurrency and _extraction_profile.is_borderless_ledger():
            logger.info(
                "[DocMirror] EPO: sequential extraction for profile=%s (audit + template consistency)",
                _extraction_profile.profile_id,
            )
            use_page_concurrency = False
        max_workers = min(self._host._max_page_concurrency, 4, len(fitz_doc)) if use_page_concurrency else 1

        try:
            if use_page_concurrency:
                # Phase 2: parallel digital page extraction (thread pool)
                results_by_idx = {}  # page_idx -> future or (page_layout, ocr_parts)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    for page_idx, layout_al in enumerate(page_layouts_al):
                        if max_pages > 0 and page_idx >= max_pages:
                            break
                        _pt = _clock()
                        try:
                            if page_has_text[page_idx] and plumber_doc:
                                future = executor.submit(
                                    extract_single_page_digital_worker,
                                    (
                                        str(Path(plumber_path).resolve()),
                                        page_idx,
                                        layout_al,
                                        pre_analysis.strategy_params,
                                        dict(pre_analysis.page_quality_map).get(
                                            page_idx, pre_analysis.avg_image_quality
                                        ),
                                        len(fitz_doc),
                                        pre_analysis.content_type,
                                        _ext_ocr_threshold,
                                        _ext_ocr_provider,
                                        global_grid_x,
                                        global_table_template,
                                        _extraction_profile,
                                    ),
                                )
                                results_by_idx[page_idx] = future
                            else:
                                fitz_page = fitz_doc[page_idx]
                                page_qual = dict(pre_analysis.page_quality_map).get(
                                    page_idx, pre_analysis.avg_image_quality
                                )
                                page_layout = PageExtractor(self._host).extract_scanned_page(
                                    fitz_page=fitz_page,
                                    page_idx=page_idx,
                                    page_quality=page_qual,
                                    external_ocr_threshold=_ext_ocr_threshold,
                                    external_ocr_provider=_ext_ocr_provider,
                                    global_grid_x=global_grid_x,
                                )
                                ocr_parts = []
                                for blk in page_layout.blocks:
                                    if blk.block_type == "text" and blk.raw_content:
                                        ocr_parts.append(str(blk.raw_content))
                                results_by_idx[page_idx] = (page_layout, ocr_parts)
                        except Exception as page_exc:
                            logger.error(
                                f"[DocMirror] ❌ Page {page_idx} extraction FAILED: {page_exc}",
                                exc_info=True,
                            )
                        _page_entry = {"page": page_idx, "total": (_clock() - _pt) * 1000}
                        _attach_stage_timings(self._host, page_idx, _page_entry)
                        _page_perf.append(_page_entry)
                # Collect results in page order
                last_layer, last_conf = "unknown", 0.0
                for page_idx in sorted(results_by_idx.keys()):
                    r = results_by_idx[page_idx]
                    if hasattr(r, "result"):
                        _, page_layout, ocr_parts, last_layer, last_conf = r.result()
                        pages.append(page_layout)
                        ocr_text_parts.extend(ocr_parts)
                    else:
                        page_layout, ocr_parts = r
                        pages.append(page_layout)
                        ocr_text_parts.extend(ocr_parts)
                extraction_layer = last_layer
                extraction_confidence = last_conf
            else:
                # Sequential path (original)
                _zone_template = None  # Perf #9: populated from page 0 via self
                self._host._zone_template = None  # Reset for each document
                # Perf #11: PageState for cross-page layer hint + header forwarding
                from ..table.page_state import PageState

                _page_state = PageState()
                self._host._page_state = _page_state
                for page_idx, layout_al in enumerate(page_layouts_al):
                    if max_pages > 0 and page_idx >= max_pages:
                        logger.info(f"[DocMirror] Early exit at page {page_idx} (DOCMIRROR_MAX_PAGES={max_pages})")
                        break
                    fitz_page = fitz_doc[page_idx]
                    _pt = _clock()
                    try:
                        if page_has_text[page_idx] and plumber_doc:
                            page_plum = plumber_doc.pages[page_idx]
                            # Perf #9: pass template for pages after page 0
                            _pass_template = (
                                self._host._zone_template if pre_analysis.layout_homogeneous and page_idx > 0 else None
                            )
                            ctx = PageExtractionContext(
                                page_plum=page_plum,
                                fitz_page=fitz_page,
                                fitz_doc=fitz_doc,
                                page_idx=page_idx,
                                layout_al=layout_al,
                                cleaned_path=plumber_path,
                                is_digital=True,
                                strategy_params=pre_analysis.strategy_params,
                                page_quality=dict(pre_analysis.page_quality_map).get(
                                    page_idx, pre_analysis.avg_image_quality
                                ),
                                content_type=pre_analysis.content_type,
                                zone_template=_pass_template,
                                global_grid_x=global_grid_x,
                                global_table_template=global_table_template,
                                extraction_profile=_extraction_profile,
                            )
                            page_layout, page_ocr_parts, extraction_layer, extraction_confidence = PagePipeline(
                                self._host
                            ).run(ctx)
                            pages.append(page_layout)
                            ocr_text_parts.extend(page_ocr_parts)
                        else:
                            # Scanned page → OCR extraction (optional external handoff if quality too low)
                            page_qual = dict(pre_analysis.page_quality_map).get(
                                page_idx, pre_analysis.avg_image_quality
                            )
                            page_layout = PageExtractor(self._host).extract_scanned_page(
                                fitz_page=fitz_page,
                                page_idx=page_idx,
                                page_quality=page_qual,
                                external_ocr_threshold=_ext_ocr_threshold,
                                external_ocr_provider=_ext_ocr_provider,
                                global_grid_x=global_grid_x,
                            )
                            pages.append(page_layout)
                            for blk in page_layout.blocks:
                                if blk.block_type == "text" and blk.raw_content:
                                    ocr_text_parts.append(str(blk.raw_content))
                    except Exception as page_exc:
                        logger.error(
                            f"[DocMirror] ❌ Page {page_idx} extraction FAILED: {page_exc}",
                            exc_info=True,
                        )
                    _page_entry = {"page": page_idx, "total": (_clock() - _pt) * 1000}
                    _attach_stage_timings(self._host, page_idx, _page_entry)
                    _page_perf.append(_page_entry)
        finally:
            if plumber_doc:
                plumber_doc.close()

            # Merge OCR text into full text
            if ocr_text_parts:
                full_text = full_text + "\n\n" + "\n\n".join(ocr_text_parts)

            # ═══ Step 4: Table post-processing (header detection + cleanup) ═══
            # Run BEFORE merge so each page's table has a confirmed header row
            _t = _clock()
            pages = self._host._post_process_tables(pages, extraction_profile=_extraction_profile)
            _perf["table_postprocess_ms"] = (_clock() - _t) * 1000

            # ═══ Step 4.5: Non-destructive logical table composition (DocumentPipeline) ═══
            _t = _clock()
            _logical_tables_payload = None
            _dual_view = False
            try:
                _logical_tables_payload, _dual_view, _quarantined = self._doc_pipeline.compose_logical_tables(
                    pages,
                    full_text=full_text,
                    pre_analysis=pre_analysis,
                )
                if _quarantined:
                    _perf["quarantined_tables"] = _quarantined
            except Exception as _ce:
                logger.debug("[DocMirror] Logical table composition skipped: %s", _ce)
                _quarantined = []
            _perf["composition_ms"] = (_clock() - _t) * 1000
            if _logical_tables_payload is not None:
                _perf["_logical_tables"] = _logical_tables_payload

            # ═══ Step 5: Cross-page merge — removed (dual-view only; CPA design 12 / ADR-CPA-13) ═══
            _t = _clock()
            if _dual_view:
                logger.info(
                    "[DocMirror] Dual-view mode: preserving per-page physical tables "
                    "(destructive merge disabled)"
                )
                _perf["dual_view"] = True
                _perf["cross_page_merge_ms"] = 0
            else:
                logger.warning(
                    "[DocMirror] Logical composition unavailable — preserving physical pages "
                    "(legacy destructive merge disabled)"
                )
                _perf["dual_view"] = False
                _perf["cross_page_merge_ms"] = 0

            # ═══ Step 5.5/5.6: Post-merge structure fix — skip in dual-view (physical fidelity) ═══
            if _dual_view:
                logger.info(
                    "[DocMirror] Dual-view: skipping fix_table_structures / infer_missing_headers "
                    "(preserve per-page physical rows for borderless ledgers)"
                )
            else:
                pages = self.fix_table_structures(pages)
                pages = self.infer_missing_headers(pages)

            # ── Log performance breakdown ──
            _logical_payload = _perf.pop("_logical_tables", None)
            logger.info(
                "[DocMirror] ⏱ Pipeline timing breakdown:\n"
                + "\n".join(
                    f"    {k}: {v:.0f}ms"
                    for k, v in _perf.items()
                    if isinstance(v, (int, float))
                )
            )
            if _logical_payload is not None:
                _perf["_logical_tables"] = _logical_payload

            _audit = getattr(self._host, "_extraction_audit", None)
            if _audit:
                _profile_id = (
                    self._host._extraction_profile.profile_id
                    if getattr(self._host, "_extraction_profile", None)
                    else None
                )
                _quarantine = _perf.get("quarantined_tables") or []
                _primary_logical = 0
                if _logical_tables_payload:
                    _primary_logical = max(
                        int(lt.get("row_count") or 0) for lt in _logical_tables_payload
                    )
                _perf["extraction_audit"] = {
                    "profile_id": _profile_id,
                    "pages": list(_audit),
                    "quarantined_pages": [
                        {
                            "page": q.get("page"),
                            "row_count": q.get("row_count"),
                            "reason": q.get("reason", "col_count_mismatch"),
                            "loss_reason": "col_count_mismatch",
                            "action": q.get("action", "standalone_physical_table"),
                        }
                        for q in _quarantine
                    ],
                    "total_physical_rows": sum(
                        len(b.raw_content)
                        for pg in pages
                        for b in pg.blocks
                        if b.block_type == "table" and isinstance(b.raw_content, list)
                    ),
                    "primary_logical_rows": _primary_logical,
                }

            if _page_perf:
                for pp in _page_perf:
                    parts = []
                    for k, v in pp.items():
                        if k == "page":
                            continue
                        if k == "stages_ms" and isinstance(v, dict):
                            parts.append(
                                "stages="
                                + ",".join(f"{sk}={sv:.0f}ms" for sk, sv in v.items())
                            )
                        elif isinstance(v, (int, float)):
                            parts.append(f"{k}={v:.0f}ms")
                    logger.debug(
                        f"[DocMirror] ⏱ Page {pp['page']}: " + " | ".join(parts)
                    )

            return pages, full_text, extraction_layer, extraction_confidence, _perf, _page_perf

    def fix_table_structures(self, pages: list) -> list:
        """Step 5.5: Apply table structure fix to all table blocks.

        Run AFTER cross-page merge so column removal doesn't cause col-count
        mismatches that prevent merging.
        """
        from docmirror.core.table.table_structure_fix import fix_table_structure

        fixed_pages = []
        for pg in pages:
            new_blocks = []
            for block in pg.blocks:
                if block.block_type == "table" and isinstance(block.raw_content, list) and len(block.raw_content) >= 2:
                    fixed = fix_table_structure(block.raw_content)
                    new_blocks.append(
                        Block(
                            block_id=block.block_id,
                            block_type=block.block_type,
                            bbox=block.bbox,
                            reading_order=block.reading_order,
                            page=block.page,
                            raw_content=fixed,
                        )
                    )
                else:
                    new_blocks.append(block)
            fixed_pages.append(
                PageLayout(
                    page_number=pg.page_number,
                    width=pg.width,
                    height=pg.height,
                    blocks=tuple(new_blocks),
                    semantic_zones=pg.semantic_zones,
                    is_scanned=pg.is_scanned,
                )
            )
        return fixed_pages

    def infer_missing_headers(self, pages: list) -> list:
        """Step 5.6: Infer and prepend missing table headers from text blocks.

        When a merged table starts with a data row (no header), scans
        text blocks from earlier pages for a vocabulary-matching header
        line and prepends it.
        """
        from ..utils.vocabulary import _is_data_row, _score_header_by_vocabulary

        for pg in pages:
            for block in pg.blocks:
                if block.block_type != "table" or not isinstance(block.raw_content, list):
                    continue
                rc = block.raw_content
                if not rc or len(rc) < 2:
                    continue
                if _is_header_row(rc[0]):
                    continue

                logger.warning(
                    f"[Extractor] Page {pg.page_number}: Table block missing header, searching for header in text..."
                )
                candidate_header = None
                best_vocab = 0
                for prev_pg in pages:
                    if prev_pg.page_number > pg.page_number:
                        break
                    for tb in prev_pg.blocks:
                        if tb.block_type == "text" and isinstance(tb.raw_content, str):
                            words = [w.strip() for w in tb.raw_content.split() if w.strip()]
                            if len(words) >= 3:
                                vs = _score_header_by_vocabulary(words)
                                if vs > best_vocab and vs >= 3:
                                    best_vocab = vs
                                    candidate_header = words
                if candidate_header:
                    logger.info(
                        f"[Merger] Page {pg.page_number}: Prepending inferred header (vocabulary score: {best_vocab})"
                    )
                    ncols = len(rc[0])
                    if len(candidate_header) == ncols:
                        aligned = candidate_header
                    elif len(candidate_header) > ncols:
                        aligned = candidate_header[:ncols]
                    else:
                        aligned = candidate_header + [""] * (ncols - len(candidate_header))
                    rc_new = [aligned] + list(rc)
                    new_blocks = []
                    for b in pg.blocks:
                        if b is block:
                            new_blocks.append(
                                Block(
                                    block_id=b.block_id,
                                    block_type=b.block_type,
                                    bbox=b.bbox,
                                    reading_order=b.reading_order,
                                    page=b.page,
                                    raw_content=rc_new,
                                )
                            )
                        else:
                            new_blocks.append(b)
                    idx = pages.index(pg)
                    pages[idx] = PageLayout(
                        page_number=pg.page_number,
                        width=pg.width,
                        height=pg.height,
                        blocks=tuple(new_blocks),
                        semantic_zones=pg.semantic_zones,
                        is_scanned=pg.is_scanned,
                    )
                    logger.info(
                        f"[DocMirror] header inferred from text: vocab={best_vocab}, words={len(candidate_header)}"
                    )
                    break
        return pages


def _attach_stage_timings(host: Any, page_idx: int, page_entry: dict[str, Any]) -> None:
    """Merge CPS stage breakdown from PagePipeline into per-page perf."""
    audit = getattr(host, "_page_stage_timings", None) or []
    for item in audit:
        if item.get("page") == page_idx:
            merge_page_stage_timings(page_entry, item.get("stages_ms", {}))
            return


__all__ = ["PdfSyncProcessor"]
