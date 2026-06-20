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

from docmirror.core.extract.engine import extract_tables_layered
from docmirror.core.extract.grid_tensor import build_global_grid_tensor
from docmirror.core.extract.segmentation import segment_page_for_extraction
from docmirror.core.extract.template_injector import build_global_template
from docmirror.core.pipeline.context import DocumentPipelineContext, PageExtractionContext
from docmirror.core.pipeline.document_pipeline import DocumentPipeline
from docmirror.core.pipeline.page_extractor import PageExtractor
from docmirror.core.pipeline.page_pipeline import PagePipeline
from docmirror.core.pipeline.pdf_processor_table_fixup import fix_table_structures, infer_missing_headers
from docmirror.core.pipeline.profiler import merge_page_stage_timings
from docmirror.core.segment.zones import (
    analyze_document_layout,
    analyze_document_layout_parallel,
    segment_page_into_zones,
)
from docmirror.models.entities.domain import PageLayout

if TYPE_CHECKING:
    from docmirror.core.extraction.extractor import CoreExtractor

logger = logging.getLogger(__name__)
_clock = time.perf_counter

_active_pdf_processor: contextvars.ContextVar[PdfSyncProcessor | None] = contextvars.ContextVar(
    "active_pdf_processor",
    default=None,
)


def reenter_generic_pipeline(fitz_doc, pre_analysis):
    """Re-enter generic CPS from a thin strategy wrapper (Phase 4)."""
    from docmirror.core.extraction.strategies.strategy_registry import _bypass_content_type

    proc = _active_pdf_processor.get()
    if proc is None:
        raise RuntimeError("reenter_generic_pipeline called without active PdfSyncProcessor")
    has_text, is_image_input, cleaned_path, file_path, options = proc._process_ctx
    token = _bypass_content_type.set(pre_analysis.content_type)
    try:
        return proc.process(
            fitz_doc,
            pre_analysis,
            has_text,
            is_image_input,
            cleaned_path,
            file_path,
            options=options,
        )
    finally:
        _bypass_content_type.reset(token)


class PdfSyncProcessor:
    """CPU-bound PDF processing (formerly CoreExtractor._process_pdf_sync)."""

    def __init__(self, host: CoreExtractor, doc_pipeline: DocumentPipeline | None = None) -> None:
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
        *,
        options: dict | None = None,
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
        import docmirror.core.extraction.strategies.mixed  # noqa: F401
        import docmirror.core.extraction.strategies.scanned  # noqa: F401

        # Import to trigger @register_strategy decorators
        import docmirror.core.extraction.strategies.section_driven  # noqa: F401
        import docmirror.core.extraction.strategies.table_led  # noqa: F401
        import docmirror.core.extraction.strategies.text_dominant  # noqa: F401
        from docmirror.core.extraction.strategies.strategy_registry import get_strategy

        self._process_ctx = (has_text, is_image_input, cleaned_path, file_path, dict(options or {}))
        proc_token = _active_pdf_processor.set(self)
        try:
            parse_control = (options or {}).get("parse_control")
            force_generic = bool(
                parse_control is not None and hasattr(parse_control, "pages") and not parse_control.pages.is_all_pages
            )
            strategy = get_strategy(pre_analysis.content_type)
            if strategy is not None and not force_generic:
                logger.info(
                    f"[DocMirror] Strategy Registry → {strategy.__class__.__name__} "
                    f"(content_type={pre_analysis.content_type})"
                )
                return strategy.extract(fitz_doc, pre_analysis)
            if strategy is not None and force_generic:
                logger.info("[DocMirror] Page selection active → generic pipeline for exact page slicing")

            # === Generic pipeline (unchanged) ===
            return self._run_generic_pipeline(
                fitz_doc,
                pre_analysis,
                has_text,
                is_image_input,
                cleaned_path,
                file_path,
                options=options,
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
        *,
        options: dict | None = None,
    ):
        """Generic CPS path (table/scanned/mixed documents)."""
        # ── Per-step timing instrumentation ──
        _perf: dict[str, float] = {}
        _page_perf: list = []  # per-page timing breakdown
        self._host._page_stage_timings = []

        # Derived: plumber_path for pdfplumber
        plumber_path = cleaned_path if cleaned_path else file_path

        options = dict(options or {})
        parse_control = options.get("parse_control")
        source_page_count = len(fitz_doc)
        if parse_control is not None and hasattr(parse_control, "pages"):
            selected_page_indices = list(parse_control.pages.resolve(source_page_count))
        else:
            max_pages_opt = options.get("max_pages")
            max_pages = (
                int(max_pages_opt or 0)
                if max_pages_opt is not None
                else int(os.environ.get("DOCMIRROR_MAX_PAGES", "0"))
            )
            selected_page_indices = list(
                range(source_page_count if max_pages <= 0 else min(source_page_count, max_pages))
            )
        selected_page_set = set(selected_page_indices)
        if not selected_page_indices and source_page_count:
            logger.warning("[DocMirror] Page selection resolved to zero pages")

        # === Step 2: Layout analysis (parallel when max_page_concurrency > 1 and path available) ===
        _t = _clock()
        num_pages = len(selected_page_indices)
        use_parallel_layout = (
            self._host._max_page_concurrency > 1 and not is_image_input and cleaned_path is not None and num_pages >= 4
        )
        if use_parallel_layout:
            layout_path = str(Path(cleaned_path).resolve())
            env_layout = int(os.environ.get("DOCMIRROR_LAYOUT_MAX_WORKERS", "0"))
            explicit_layout_workers = None
            if parse_control is not None:
                workers_raw = getattr(getattr(parse_control, "resource", None), "workers", None)
                if isinstance(workers_raw, int):
                    explicit_layout_workers = max(1, workers_raw)
            layout_workers = (
                min(num_pages, explicit_layout_workers)
                if explicit_layout_workers is not None
                else min(num_pages, env_layout)
                if env_layout > 0
                else min(self._host._max_page_concurrency, num_pages, os.cpu_count() or 4)
            )
            if layout_workers <= 1:
                page_layouts_al = analyze_document_layout(fitz_doc, page_indices=selected_page_indices)
            else:
                page_layouts_al = analyze_document_layout_parallel(
                    layout_path,
                    source_page_count,
                    max_workers=layout_workers,
                    page_indices=selected_page_indices,
                )
        else:
            page_layouts_al = analyze_document_layout(fitz_doc, page_indices=selected_page_indices)
        _perf["layout_analysis_ms"] = (_clock() - _t) * 1000
        _perf["source_page_count"] = source_page_count
        _perf["selected_pages"] = [i + 1 for i in selected_page_indices]

        # Extract full text (with per-page caching to avoid redundant calls)
        _page_text_cache: dict[int, str] = {}
        full_text_parts = []
        for p_idx in selected_page_indices:
            page = fitz_doc[p_idx]
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
            options=options,
        )
        self._host._pipeline_ctx = pipeline_ctx
        _extraction_profile = self._doc_pipeline.bind_profile(
            full_text_raw=full_text_raw,
            num_pages=source_page_count,
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

        # Per-page text presence detection (>50 chars = has text layer)
        # Use cached text from above
        _TEXT_THRESHOLD = 50
        page_has_text = []
        for p_idx in range(len(fitz_doc)):
            txt = _page_text_cache.get(p_idx, "")
            page_has_text.append(len(txt.strip()) > _TEXT_THRESHOLD)

        selected_has_text = [page_has_text[i] for i in selected_page_indices]
        hybrid_doc = has_text and bool(selected_has_text) and not all(selected_has_text)
        if hybrid_doc:
            scanned_indices = [i for i in selected_page_indices if not page_has_text[i]]
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
                max_tensor_pages = min(len(selected_page_indices), 50)
                all_chars = []
                max_w = 0
                for pid in selected_page_indices[:max_tensor_pages]:
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
        if plumber_doc and len(fitz_doc) >= 3 and _extraction_profile.enable_grid_template:
            try:
                sample_idx = (
                    selected_page_indices[min(1, len(selected_page_indices) - 1)] if selected_page_indices else 0
                )
                if page_has_text[sample_idx]:
                    sp_t0 = _clock()
                    sample_plum = plumber_doc.pages[sample_idx]
                    sample_fitz = fitz_doc[sample_idx]
                    sample_zones = segment_page_for_extraction(sample_plum, sample_idx, _extraction_profile)

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
                        if (
                            stabs
                            and len(stabs[0]) >= 2
                            and (sconf >= 0.85 or _extraction_profile.is_borderless_ledger())
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
        elif plumber_doc and len(fitz_doc) >= 3 and _extraction_profile.profile_id == "generic":
            # Legacy template sampling — generic docs only (EPO profiles use enable_grid_template branch)
            try:
                # Sample the very middle page
                sample_idx = (
                    selected_page_indices[len(selected_page_indices) // 2]
                    if selected_page_indices
                    else len(fitz_doc) // 2
                )
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

        num_digital = sum(1 for i in selected_page_indices if page_has_text[i])
        use_page_concurrency = self._host._max_page_concurrency > 1 and plumber_doc is not None and num_digital >= 2
        if use_page_concurrency and _extraction_profile.is_borderless_ledger():
            logger.info(
                "[DocMirror] EPO: sequential extraction for profile=%s (audit + template consistency)",
                _extraction_profile.profile_id,
            )
            use_page_concurrency = False
        max_workers = (
            min(self._host._max_page_concurrency, 4, len(selected_page_indices)) if use_page_concurrency else 1
        )

        try:
            if use_page_concurrency:
                # Phase 2: parallel digital page extraction (thread pool)
                results_by_idx = {}  # page_idx -> future or (page_layout, ocr_parts)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    for layout_al in page_layouts_al:
                        page_idx = layout_al.page_index
                        if page_idx not in selected_page_set:
                            continue
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
                for layout_al in page_layouts_al:
                    page_idx = layout_al.page_index
                    if page_idx not in selected_page_set:
                        continue
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
                _ltqg = getattr(self._host, "_ltqg_summary", None)
                if _ltqg:
                    _perf["ltqg"] = _ltqg
            except Exception as _ce:
                logger.warning("[DocMirror] Logical table composition failed: %s", _ce)
                _perf["compose_failed"] = True
                _quarantined = []
            _perf["composition_ms"] = (_clock() - _t) * 1000
            if _logical_tables_payload is not None:
                _perf["_logical_tables"] = _logical_tables_payload

            # ═══ Step 5: Cross-page merge — removed (dual-view only; CPA design 12 / ADR-CPA-13) ═══
            _t = _clock()
            if _dual_view:
                logger.info(
                    "[DocMirror] Dual-view mode: preserving per-page physical tables (destructive merge disabled)"
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
                profile = getattr(self._host, "_extraction_profile", None)
                from docmirror.core.profile.registry import is_borderless_ledger_profile

                skip_fix = bool(
                    profile
                    and is_borderless_ledger_profile(profile)
                    and getattr(profile, "document_type_hint", None) == "bank_statement"
                )
                if skip_fix:
                    logger.info(
                        "[DocMirror] Borderless bank: skipping fix_table_structures / "
                        "infer_missing_headers (compose unavailable — preserve physical fidelity)"
                    )
                else:
                    pages = fix_table_structures(pages)
                    pages = infer_missing_headers(pages)

            # ── Log performance breakdown ──
            _logical_payload = _perf.pop("_logical_tables", None)
            logger.info(
                "[DocMirror] ⏱ Pipeline timing breakdown:\n"
                + "\n".join(f"    {k}: {v:.0f}ms" for k, v in _perf.items() if isinstance(v, (int, float)))
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
                    _ltqg = _perf.get("ltqg") or {}
                    if _ltqg.get("enabled"):
                        _primary_logical = int(_ltqg.get("expected_data_rows") or 0)
                    else:
                        _primary_logical = max(int(lt.get("row_count") or 0) for lt in _logical_tables_payload)
                _perf["extraction_audit"] = {
                    "profile_id": _profile_id,
                    "pages": list(_audit),
                    "quarantined_pages": [
                        {
                            "page": q.get("page"),
                            "row_count": q.get("row_count"),
                            "reason": q.get("reason", "col_count_mismatch"),
                            "loss_reason": q.get("reason", "col_count_mismatch"),
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
                if _ltqg := _perf.get("ltqg"):
                    _perf["extraction_audit"]["ltqg"] = dict(_ltqg)

            if _page_perf:
                for pp in _page_perf:
                    parts = []
                    for k, v in pp.items():
                        if k == "page":
                            continue
                        if k == "stages_ms" and isinstance(v, dict):
                            parts.append("stages=" + ",".join(f"{sk}={sv:.0f}ms" for sk, sv in v.items()))
                        elif isinstance(v, (int, float)):
                            parts.append(f"{k}={v:.0f}ms")
                    logger.debug(f"[DocMirror] ⏱ Page {pp['page']}: " + " | ".join(parts))

            return pages, full_text, extraction_layer, extraction_confidence, _perf, _page_perf


def _attach_stage_timings(host: Any, page_idx: int, page_entry: dict[str, Any]) -> None:
    """Merge CPS stage breakdown from PagePipeline into per-page perf."""
    audit = getattr(host, "_page_stage_timings", None) or []
    for item in audit:
        if item.get("page") == page_idx:
            merge_page_stage_timings(page_entry, item.get("stages_ms", {}))
            return


__all__ = ["PdfSyncProcessor"]
