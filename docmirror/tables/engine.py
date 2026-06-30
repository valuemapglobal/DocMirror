# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Extract engine — four-tier layered table extraction.

Purpose: Main table extraction entry ``extract_tables_layered`` that
progressively tries PyMuPDF, RapidTable, char/signal, and fallback backends.

Main components: ``extract_tables_layered``.

Upstream: ``pipeline.handlers.table_zone``, ``ExtractionProfile``.

Downstream: ``extract.best_candidate``, ``extraction.table_postprocessor``.
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
import time
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docmirror.models.entities.extraction_profile import ExtractionProfile

    from .template_injector import GlobalTableTemplate

from docmirror.layout.vocabulary import _is_header_row, _score_header_by_vocabulary

logger = logging.getLogger(__name__)
# T3-3: Module-level DEBUG flag — avoids f-string formatting cost
# when debug logging is disabled (~5-10% CPU savings on hot paths)
_DEBUG = logger.isEnabledFor(logging.DEBUG)


from .char_strategy import (
    _extract_by_hline_columns,
    _extract_by_rect_columns,
    detect_columns_by_clustering,
    detect_columns_by_data_voting,
    detect_columns_by_header_anchors,
    detect_columns_by_header_guided,
    detect_columns_by_whitespace_projection,
    detect_columns_by_word_anchors,
    detect_table_via_grid,
)
from .classifier import (
    TABLE_SETTINGS,
    TABLE_SETTINGS_LINES,
    _cell_is_stuffed,
    _compute_table_confidence,
    _layer_timings_var,
    _quick_classify,
    _tables_look_valid,
)
from .merged_cells import detect_merged_cells  # noqa: F401 — re-exported for table_zone
from .pdfplumber_strategy import _recover_header_from_zone
from .pipe_strategy import _extract_by_pipe_delimited
from .profile_run_state import ProfileRunState as _ProfileRunState
from .zone_crop import crop_simple_to_table_zone
from .zone_crop import crop_to_table_zone as _crop_to_table_zone


def _extract_tables_layered_registry(
    page_plum,
    table_zone_bbox: tuple[float, float, float, float] | None = None,
    document_page_count: int | None = None,
    fitz_page=None,
    watermark_filtered: bool = False,
    layer_hint: str | None = None,
    global_grid_x: list[float] | None = None,
    table_template: GlobalTableTemplate | None = None,
    extraction_profile: ExtractionProfile | None = None,
    extraction_audit: list | None = None,
    fast_continuation: bool = False,
    audit_page: int | None = None,
) -> tuple[list[list[list[str]]], str, float]:
    """Registry-first table extraction path.

    This keeps the raw BCS/profile gates but delegates individual
    extraction methods to ``TableMethodRegistry`` instead of hard-coding the
    L0-L3 method calls in the engine body.
    """
    from docmirror.tables.method_reconstructor import TableMethodContext, TableMethodRegistry

    registry = TableMethodRegistry()
    timings: dict[str, float] = {}
    t_total = time.time()
    state = _ProfileRunState(extraction_profile, extraction_audit, audit_page=audit_page)
    bcs_ledger = bool(
        state.use_bcs
        and state.profile
        and state.profile.is_borderless_ledger()
        and state.profile.bcs_oracle_layer == "pdfplumber_default"
    )
    has_oracle_candidate = False
    layer2_fallback: tuple[list[list[str]], str] | None = None

    work_page = page_plum
    y0 = table_zone_bbox[1] if table_zone_bbox else None
    y1 = table_zone_bbox[3] if table_zone_bbox else None
    if table_zone_bbox:
        try:
            if fast_continuation:
                work_page, y0, y1 = crop_simple_to_table_zone(page_plum, table_zone_bbox)
            else:
                work_page, y0, y1 = _crop_to_table_zone(page_plum, table_zone_bbox)
        except Exception as exc:
            logger.debug("registry crop failed: %s", exc)

    def _t(label: str, started: float) -> None:
        timings[label] = round((time.time() - started) * 1000, 2)

    def _emit(table: list[list[str]], layer: str):
        tables = [table]
        conf = _compute_table_confidence(tables, layer)
        if extraction_profile and not state.offer(tables, layer, conf):
            return None
        timings["total"] = round((time.time() - t_total) * 1000, 2)
        timings["registry_path"] = 1
        _layer_timings_var.set(dict(timings))
        logger.info(
            "[TableEngine] Registry extraction completed using layer='%s' (conf=%.3f, timings=%s)",
            layer,
            conf,
            timings,
        )
        return tables, layer, conf

    def _disabled(method_id: str) -> bool:
        return state.layer_disabled(method_id)

    lines = work_page.lines or []
    v_line_count = sum(1 for line in lines if abs(line.get("x0", 0) - line.get("x1", 0)) < 1)
    h_line_count = sum(1 for line in lines if abs(line.get("top", 0) - line.get("bottom", 0)) < 1)
    has_borders = v_line_count >= 2
    segmented_h_lines = None
    if v_line_count >= 10 and h_line_count < 10:
        v_x_counts = Counter(round(line["x0"], 0) for line in lines if abs(line.get("x0", 0) - line.get("x1", 0)) < 1)
        max_segments = v_x_counts.most_common(1)[0][1] if v_x_counts else 0
        if max_segments > 3:
            y_values = set()
            for line in lines:
                if abs(line.get("x0", 0) - line.get("x1", 0)) < 1:
                    y_values.add(round(line["top"], 1))
                    y_values.add(round(line["bottom"], 1))
                if abs(line.get("top", 0) - line.get("bottom", 0)) < 1:
                    y_values.add(round(line["top"], 1))
            segmented_h_lines = sorted(y_values)

    line_settings = None
    if segmented_h_lines:
        line_settings = dict(TABLE_SETTINGS_LINES)
        line_settings["explicit_horizontal_lines"] = segmented_h_lines

    context = TableMethodContext(
        fitz_page=fitz_page,
        table_zone_bbox=table_zone_bbox,
        crop_y0=y0,
        crop_y1=y1,
        table_template=table_template,
        global_grid_x=global_grid_x,
        has_borders=has_borders,
        line_settings=line_settings,
    )

    def _run_one(method_id: str, *, recover_header: bool = False, min_rows: int = 2):
        if _disabled(method_id):
            timings[f"{method_id}_skipped"] = "profile"
            return None
        started = time.time()
        result = registry.reconstruct_one(method_id, work_page, extraction_profile, context=context)
        _t(method_id, started)
        if result is None:
            return None
        layer, table, _score = result
        if (
            method_id == "template_injection"
            and table_template
            and not _is_header_row(table[0])
            and table_template.header_vocab
        ):
            header = table_template.header_vocab[: len(table[0])]
            while len(header) < len(table[0]):
                header.append("")
            table.insert(0, header)
        if len(table) < min_rows or not _tables_look_valid([table], has_borders=has_borders):
            return None
        if recover_header:
            table = _recover_header_from_zone([table], work_page, table_zone_bbox, page_plum)[0]
        return _emit(table, layer)

    def _offer_one(method_id: str, *, recover_header: bool = False, min_rows: int = 2) -> bool:
        nonlocal has_oracle_candidate
        result = _run_one(method_id, recover_header=recover_header, min_rows=min_rows)
        if result is not None:
            return True
        if bcs_ledger:
            for candidate in state.candidates:
                if candidate.layer in {method_id, "pdfplumber_default", "pipe_delimited"} and candidate.row_count >= 2:
                    has_oracle_candidate = True
                    break
        return False

    def _finalize(default_layer: str = "fallback"):
        tables, layer, conf = state.finalize(page_plum.extract_tables() or [], default_layer, 0.0)
        if tables and tables[0]:
            result = _emit(tables[0], layer)
            return result if result is not None else (tables, layer, conf)
        timings["total"] = round((time.time() - t_total) * 1000, 2)
        timings["registry_path"] = 1
        _layer_timings_var.set(dict(timings))
        return tables, layer, conf

    if table_template and fast_continuation:
        result = _run_one("template_injection", min_rows=2)
        if result is not None:
            return result
        if state.use_bcs:
            finalized = state.pick_oracle_layer(layer="template_injection", mark_fast_continuation=True)
            if finalized is not None:
                return finalized

    if layer_hint:
        hinted = _run_one(layer_hint, recover_header=layer_hint in {"lines", "hline_columns", "rect_columns"})
        if hinted is not None:
            return hinted

    started = time.time()
    classify_hint = _quick_classify(work_page)
    _t("pre_classify", started)

    from docmirror.tables.structure_detect import detect_pipe_grid_page, page_has_no_drawing_primitives

    pipe_signal = detect_pipe_grid_page(work_page) if page_has_no_drawing_primitives(work_page) else None
    if pipe_signal and pipe_signal.confidence >= 0.5:
        if _offer_one("pipe_delimited", min_rows=3):
            if not state.use_bcs:
                return _finalize("pipe_delimited")
        if bcs_ledger and has_oracle_candidate:
            return _finalize()

    if bcs_ledger and not fast_continuation:
        _offer_one("pdfplumber_default", recover_header=True, min_rows=2)
        if has_oracle_candidate:
            return _finalize()

    if not (pipe_signal and pipe_signal.confidence >= 0.5):
        early = _run_one("pipe_delimited", min_rows=3)
        if early is not None:
            return early

    if fitz_page is not None and not watermark_filtered:
        native = _run_one("pymupdf_native", min_rows=3)
        if native is not None:
            return native

    if classify_hint != "char":
        for method_id in ("lines", "hline_columns", "rect_columns", "text"):
            if method_id in {"hline_columns", "rect_columns"} and (
                classify_hint == "text" or (h_line_count >= 100 and v_line_count == 0)
            ):
                timings[f"{method_id}_skipped"] = "pre_classify"
                continue
            result = _run_one(method_id, recover_header=True, min_rows=3 if method_id != "text" else 2)
            if result is not None:
                return result

    if classify_hint != "char" or bcs_ledger:
        result = _run_one("pdfplumber_default", recover_header=True, min_rows=2)
        if result is not None:
            return result
        result = _run_one("text_fallback", recover_header=True, min_rows=2)
        if result is not None:
            return result
    else:
        timings["pdfplumber_default_skipped"] = "char_hint"

    skip_l2 = bcs_ledger and has_oracle_candidate
    if not skip_l2:
        signal = _run_one("signal_processor", min_rows=2)
        if signal is not None:
            return signal

        started = time.time()
        char_candidates = registry.reconstruct_all(
            work_page,
            extraction_profile,
            method_ids=[
                "header_anchors",
                "header_guided",
                "grid_reconstructor",
                "word_anchors",
                "data_voting",
                "whitespace_projection",
            ],
            context=context,
            max_workers=4,
        )
        _t("L2_registry_char_level", started)
        usable: list[tuple[list[list[str]], str, int]] = []
        for layer, table, _score in char_candidates:
            if table and len(table) >= 2:
                usable.append((table, layer, _score_header_by_vocabulary(table[0])))
        if usable:
            priority = {
                "grid_reconstructor": 5,
                "header_guided": 4,
                "header_anchors": 3,
                "word_anchors": 2,
                "data_voting": 1,
                "whitespace_projection": 0,
            }
            usable.sort(
                key=lambda item: (
                    item[2],
                    priority.get(item[1], 0),
                    len(item[0])
                    - sum(1 for row in item[0][:10] for cell in row if _cell_is_stuffed(str(cell or ""))) * 10,
                ),
                reverse=True,
            )
            best_table, best_layer, best_score = usable[0]
            try:
                from docmirror.tables.utils import _refine_dense_rows

                refined = _refine_dense_rows(best_table, [], [])
                if refined is not None:
                    best_table = refined
            except Exception:
                pass
            if best_score >= 3:
                result = _emit(best_table, best_layer)
                if result is not None:
                    return result
            layer2_fallback = (best_table, best_layer)
    else:
        timings["L2_registry_char_level_skipped"] = "bcs_oracle"

    import os

    rapid_max_pages_raw = os.getenv("DOCMIRROR_TABLE_RAPID_MAX_PAGES", "").strip()
    rapid_max_pages = int(rapid_max_pages_raw) if rapid_max_pages_raw else None
    rapid_min_conf = float(os.getenv("DOCMIRROR_TABLE_RAPID_MIN_CONFIDENCE_THRESHOLD", "0.5"))
    skip_rapid = bcs_ledger
    skip_reason = "bcs_ledger_oracle" if bcs_ledger else None
    if document_page_count is not None and rapid_max_pages is not None and document_page_count > rapid_max_pages:
        skip_rapid = True
        skip_reason = "document_page_count_exceeded"
    if layer2_fallback and not skip_rapid:
        upstream_conf = _compute_table_confidence([layer2_fallback[0]], layer2_fallback[1])
        if upstream_conf >= rapid_min_conf:
            skip_rapid = True
            skip_reason = "upstream_confidence_above_threshold"
    if skip_rapid:
        timings["rapid_table_skipped"] = skip_reason or "config"
    else:
        rapid = _run_one("rapid_table", min_rows=2)
        if rapid is not None:
            return rapid

    clustering = _run_one("x_clustering", min_rows=2)
    if clustering is not None:
        return clustering

    if layer2_fallback:
        result = _emit(layer2_fallback[0], layer2_fallback[1])
        if result is not None:
            return result

    return _finalize()


def extract_tables_layered(
    page_plum,
    table_zone_bbox: tuple[float, float, float, float] | None = None,
    document_page_count: int | None = None,
    fitz_page=None,
    watermark_filtered: bool = False,
    layer_hint: str | None = None,
    _zone_layer_hints: dict[str, str] | None = None,
    global_grid_x: list[float] | None = None,
    table_template: GlobalTableTemplate | None = None,
    pid_resample: bool = False,  # noqa: ARG001 — reserved API; profile uses skip_pid_resample
    extraction_profile: ExtractionProfile | None = None,
    extraction_audit: list | None = None,
    fast_continuation: bool = False,
    audit_page: int | None = None,
) -> tuple[list[list[list[str]]], str, float]:
    """Progressively layered table extraction.

    Optimisation highlights:
      - Pre-classification (``_quick_classify``): skip unlikely layers based
        on quick page features.
      - Per-layer timing: results stored in ``_layer_timings_var``.
      - Layer 2 parallel execution: 4 char-level methods run concurrently
        via ``ThreadPoolExecutor``.
      - Confidence scoring: returns a 0–1 float combining vocab_score,
        row_count, and col_consistency.

    Args:
        page_plum: pdfplumber page object.
        table_zone_bbox: Optional ``(x0, y0, x1, y1)`` bounding box of the
            table zone.  All layers operate on the cropped page to avoid
            extracting metadata tables or title text outside the zone.

    Returns:
        ``(tables, layer_label, confidence)`` 3-tuple.
    """
    try:
        from docmirror.configs.runtime.settings import get_settings

        if get_settings().udtr_use_table_method_registry:
            return _extract_tables_layered_registry(
                page_plum,
                table_zone_bbox=table_zone_bbox,
                document_page_count=document_page_count,
                fitz_page=fitz_page,
                watermark_filtered=watermark_filtered,
                layer_hint=layer_hint,
                global_grid_x=global_grid_x,
                table_template=table_template,
                extraction_profile=extraction_profile,
                extraction_audit=extraction_audit,
                fast_continuation=fast_continuation,
                audit_page=audit_page,
            )
    except Exception as exc:
        logger.warning("[TableEngine] registry path failed; falling back to raw cascade: %s", exc)

    timings: dict[str, float] = {}
    t_total = time.time()
    _pr = _ProfileRunState(extraction_profile, extraction_audit, audit_page=audit_page)
    _bcs_ledger = bool(
        _pr.use_bcs
        and _pr.profile
        and _pr.profile.is_borderless_ledger()
        and _pr.profile.bcs_oracle_layer == "pdfplumber_default"
    )
    _ran_l09_early = False
    _has_oracle_candidate = False

    def _t(label: str, t0: float):
        """Record per-layer elapsed time (ms)."""
        timings[label] = round((time.time() - t0) * 1000, 2)

    def _return(tables, layer):
        """Unified return: compute confidence and record total time."""
        conf = _compute_table_confidence(tables, layer)
        if extraction_profile and not _pr.offer(tables, layer, conf):
            return None
        timings["total"] = round((time.time() - t_total) * 1000, 2)
        _layer_timings_var.set(dict(timings))
        logger.info(f"[TableEngine] Extraction completed using layer='{layer}' (conf={conf:.3f}, timings={timings})")
        return tables, layer, conf

    def _emit(tables, layer):
        """Return from layer if profile allows, else continue cascade."""
        result = _return(tables, layer)
        if result is not None:
            return result
        return None

    def _run_l09_pdfplumber(*, label_prefix: str = "L0.9", include_text_fallback: bool = True):
        """Run pdfplumber default (+ optional text fallback). Returns early-exit tuple or None."""
        nonlocal _ran_l09_early, _has_oracle_candidate
        _ran_l09_early = True
        t0 = time.time()
        tables = work_page.extract_tables()
        _t(f"{label_prefix}_default", t0)
        if tables and _tables_look_valid(tables, has_borders=has_borders):
            _done = _emit(
                _recover_header_from_zone(tables, work_page, table_zone_bbox, page_plum),
                "pdfplumber_default",
            )
            if _done is not None:
                return _done
            if _bcs_ledger:
                for c in _pr.candidates:
                    if c.layer == "pdfplumber_default" and c.row_count >= 2:
                        _has_oracle_candidate = True
                        break

        if include_text_fallback and not _ran_l1b_text:
            t0 = time.time()
            tables = work_page.extract_tables(table_settings=TABLE_SETTINGS)
            _t(f"{label_prefix}_text", t0)
            if tables and _tables_look_valid(tables, has_borders=has_borders):
                _done = _emit(
                    _recover_header_from_zone(tables, work_page, table_zone_bbox, page_plum),
                    "text_fallback",
                )
                if _done is not None:
                    return _done
        return None

    def _finalize_bcs_or_continue():
        """Pick best BCS candidate and return, or None to continue cascade."""
        tables, layer, conf = _pr.finalize(page_plum.extract_tables() or [], "fallback", 0.0)
        result = _return(tables, layer)
        return result if result is not None else (tables, layer, conf)

    has_borders = False

    # ── Crop to table zone (all layers work on the cropped page) ──
    work_page = page_plum
    if table_zone_bbox:
        try:
            if fast_continuation:
                work_page, y0, y1 = crop_simple_to_table_zone(page_plum, table_zone_bbox)
            else:
                work_page, y0, y1 = _crop_to_table_zone(page_plum, table_zone_bbox)
        except Exception as e:
            logger.debug(f"crop failed: {e}")
            y0, y1 = table_zone_bbox[1], table_zone_bbox[3]

    # ── Ledger continuation (page 2..N): oracle pdfplumber only — skip template + BCS duel.
    if table_template and fast_continuation and _bcs_ledger:
        _run_l09_pdfplumber(label_prefix="L0.9_fast", include_text_fallback=False)
        oracle_layer = (
            _pr.profile.bcs_oracle_layer if _pr.profile and _pr.profile.bcs_oracle_layer else "pdfplumber_default"
        )
        picked = _pr.pick_oracle_layer(layer=oracle_layer, mark_fast_continuation=True)
        if picked is not None:
            tables, layer, conf = picked
            timings["total"] = round((time.time() - t_total) * 1000, 2)
            _layer_timings_var.set(dict(timings))
            logger.debug(
                "[TableEngine] Ledger continuation fast path layer=%r conf=%.3f rows=%d",
                layer,
                conf,
                len(tables[0]) if tables and tables[0] else 0,
            )
            return tables, layer, conf

    # ── Template Injection: Force absolute grid alignment ──
    # Skip on the first page (no fast_continuation) — let CSP and other
    # layers extract the full row set from scratch.  Template is only
    # needed for continuation pages where the header is absent.
    if table_template and fast_continuation:
        from .template_injector import extract_by_injected_template

        t0 = time.time()
        try:
            injected_table = extract_by_injected_template(work_page, table_template)
            _t("L_template", t0)
            if injected_table and len(injected_table) >= 2:
                if not _is_header_row(injected_table[0]) and table_template.header_vocab:
                    # Align header length to injected table width
                    aligned_hdr = table_template.header_vocab[: len(injected_table[0])]
                    while len(aligned_hdr) < len(injected_table[0]):
                        aligned_hdr.append("")
                    injected_table.insert(0, aligned_hdr)

                if _DEBUG:
                    logger.debug(
                        "Template Injection succeeded (forced grid alignment, %d rows)",
                        len(injected_table),
                    )
                _done = _emit([injected_table], "template_injection")
                if _done is not None:
                    return _done
        except Exception as exc:
            _t("L_template", t0)
            if _DEBUG:
                logger.debug("Template Injection failed: %s", exc)

    # ── Layer Hint: skip to the previously successful layer ──
    if layer_hint:
        _HINT_DISPATCH = {
            "hline_columns": lambda wp: _extract_by_hline_columns(wp),
            "rect_columns": lambda wp: _extract_by_rect_columns(wp),
            "header_anchors": lambda wp: detect_columns_by_header_anchors(wp),
            "word_anchors": lambda wp: detect_columns_by_word_anchors(wp),
            "data_voting": lambda wp: detect_columns_by_data_voting(wp),
            "whitespace_projection": lambda wp: detect_columns_by_whitespace_projection(wp),
            "x_clustering": lambda wp: detect_columns_by_clustering(wp),
        }
        # Also handle signal_processor hint
        if layer_hint == "signal_processor":
            try:
                from .signal_processor import extract_table_by_signal

                _HINT_DISPATCH["signal_processor"] = lambda wp: extract_table_by_signal(
                    wp, global_tensor_x=global_grid_x
                )
            except ImportError:
                pass

        hint_func = _HINT_DISPATCH.get(layer_hint)
        if hint_func:
            t0 = time.time()
            try:
                hint_table = hint_func(work_page)
                _t(f"L_hint_{layer_hint}", t0)
                if hint_table and len(hint_table) >= 2:
                    hint_vocab = _score_header_by_vocabulary(hint_table[0])
                    if hint_vocab >= 3 and _tables_look_valid([hint_table], has_borders=has_borders):
                        if _DEBUG:
                            logger.debug(
                                "Layer hint '%s' succeeded (vocab=%d, %d rows)",
                                layer_hint,
                                hint_vocab,
                                len(hint_table),
                            )
                        _done = _emit([hint_table], layer_hint)
                        if _done is not None:
                            return _done
            except Exception as exc:
                _t(f"L_hint_{layer_hint}", t0)
                if _DEBUG:
                    logger.debug("Layer hint '%s' failed: %s", layer_hint, exc)
        # Hint failed → fall through to full cascade

    # ── Pre-classification: determine starting layer from quick features ──
    t0 = time.time()
    classify_hint = _quick_classify(work_page)
    _t("pre_classify", t0)
    if _DEBUG:
        logger.debug("pre-classify hint: %s", classify_hint)

    # ── Detect vertical border lines: bordered tables skip stuffed-cell check ──
    _lines = work_page.lines or []
    _v_line_count = sum(1 for l in _lines if abs(l.get("x0", 0) - l.get("x1", 0)) < 1)
    has_borders = _v_line_count >= 2
    _ran_l1b_text = False
    # When vertical lines are segmented per row (same x, many short lines)
    # and horizontal lines are insufficient, extract implicit row boundary
    # y-coordinates from vertical-line endpoints.
    _h_line_count = sum(1 for l in _lines if abs(l.get("top", 0) - l.get("bottom", 0)) < 1)
    _segmented_h_lines = None
    if _v_line_count >= 10 and _h_line_count < 10:
        # Counter already imported at module level
        # Count how many vertical lines share each x-position
        _v_x_counts = Counter(round(l["x0"], 0) for l in _lines if abs(l.get("x0", 0) - l.get("x1", 0)) < 1)
        # If the most common x has > 3 segments, vertical lines are row-segmented
        _max_segs = _v_x_counts.most_common(1)[0][1] if _v_x_counts else 0
        if _max_segs > 3:
            _y_set = set()
            for l in _lines:
                if abs(l.get("x0", 0) - l.get("x1", 0)) < 1:
                    _y_set.add(round(l["top"], 1))
                    _y_set.add(round(l["bottom"], 1))
            # Also include existing horizontal line y-values
            for l in _lines:
                if abs(l.get("top", 0) - l.get("bottom", 0)) < 1:
                    _y_set.add(round(l["top"], 1))
            _segmented_h_lines = sorted(_y_set)
            logger.debug(
                f"segmented v_lines → {len(_segmented_h_lines)} implicit row boundaries (max_segs={_max_segs})"
            )

    # ── SALO: pipe-first when SDU detects ASCII pipe grid (ADR-M13) ──
    from docmirror.tables.structure_detect import detect_pipe_grid_page, page_has_no_drawing_primitives

    _pipe_signal = None
    if page_has_no_drawing_primitives(work_page):
        _pipe_signal = detect_pipe_grid_page(work_page)

    if _pipe_signal and _pipe_signal.confidence >= 0.5:
        t0 = time.time()
        pipe_table = _extract_by_pipe_delimited(work_page)
        _t("L0.5_pipe", t0)
        if pipe_table and len(pipe_table) >= 3:
            _done = _emit([pipe_table], "pipe_delimited")
            if _done is not None:
                return _done
            if _bcs_ledger:
                for c in _pr.candidates:
                    if c.layer == "pipe_delimited" and c.row_count >= 2:
                        _has_oracle_candidate = True
                        break

    # ── BCS ledger fast path: pdfplumber oracle before expensive L1/L2 layers ──
    if _bcs_ledger and not fast_continuation:
        early = _run_l09_pdfplumber()
        if early is not None:
            return early
        if _has_oracle_candidate:
            return _finalize_bcs_or_continue()

    # ── Layer 0.5: pipe separator (fallback when SALO block did not early-return) ──
    if not (_pipe_signal and _pipe_signal.confidence >= 0.5):
        t0 = time.time()
        pipe_table = _extract_by_pipe_delimited(work_page)
        _t("L0.5_pipe", t0)
        if pipe_table and len(pipe_table) >= 3:
            _done = _emit([pipe_table], "pipe_delimited")
            if _done is not None:
                return _done

    # ── Layer 0.8: PyMuPDF native table detection (C implementation, ~50-70% faster) ──
    # T4-3: Only when fitz_page is provided. Falls through for borderless/complex tables.
    if fitz_page is not None and not watermark_filtered and not _pr.layer_disabled("pymupdf_native"):
        t0 = time.time()
        try:
            # Use full page width and expanded y-range (matching pdfplumber crop).
            # y0 comes from header probe expansion; y1 comes from bottom probe expansion.
            _pymupdf_bbox = None
            if table_zone_bbox:
                _pymupdf_bbox = (0, y0, fitz_page.rect.width, y1)
            _pymupdf_tables = _extract_by_pymupdf(fitz_page, _pymupdf_bbox)
            _t("L0.8_pymupdf", t0)
            if _pymupdf_tables:
                # Validate: at least 3 rows and reasonable column count
                for tbl in _pymupdf_tables:
                    if tbl and len(tbl) >= 3 and len(tbl[0]) >= 2:
                        if _tables_look_valid([tbl], has_borders=has_borders):
                            _done = _emit([tbl], "pymupdf_native")
                            if _done is not None:
                                return _done
        except Exception as exc:
            _t("L0.8_pymupdf", t0)
            if _DEBUG:
                logger.debug("L0.8 PyMuPDF error: %s", exc)

    # Pre-classification jump: if hint='char', skip Layers 1–1.8
    if classify_hint != "char":
        # ── Layer 1: lines strategy ──
        t0 = time.time()
        if _segmented_h_lines:
            settings = dict(TABLE_SETTINGS_LINES)
            settings["explicit_horizontal_lines"] = _segmented_h_lines
            tables = work_page.extract_tables(table_settings=settings)
        else:
            tables = work_page.extract_tables(table_settings=TABLE_SETTINGS_LINES)
        _t("L1_lines", t0)
        if tables and _tables_look_valid(tables, has_borders=has_borders):
            _done = _emit(
                _recover_header_from_zone(tables, work_page, table_zone_bbox, page_plum),
                "lines",
            )
            if _done is not None:
                return _done

        # Pre-classification jump: if hint='text', skip L1a/L1.5 to L1b
        # Also skip when excessive h_lines but v_lines=0 (degenerate case —
        # e.g. 192 h_lines + 0 v_lines where every text line has a rule).
        # Threshold 100: valid tables typically have <50 h_lines (header + row borders).
        _skip_l1a = (classify_hint == "text") or (_h_line_count >= 100 and _v_line_count == 0)
        if not _skip_l1a:
            # ── Layer 1a: horizontal-line column boundary method ──
            t0 = time.time()
            table = _extract_by_hline_columns(work_page)
            _t("L1a_hline", t0)
            if table and len(table) >= 3 and _tables_look_valid([table], has_borders=has_borders):
                # Header quality check: if the first row looks like data (contains date), reject L1a
                _first_cell = (table[0][0] or "").strip()
                _header_looks_like_data = bool(
                    re.match(r"^\d{4}[-./]\d{2}[-./]\d{2}", _first_cell) or re.match(r"^\d{8}$", _first_cell)
                )
                logger.debug(f"L1a header check: first_cell={_first_cell!r} looks_like_data={_header_looks_like_data}")
                if not _header_looks_like_data:
                    _done = _emit(
                        _recover_header_from_zone([table], work_page, table_zone_bbox, page_plum),
                        "hline_columns",
                    )
                    if _done is not None:
                        return _done
                else:
                    logger.info("L1a rejected: header looks like data row")

            # ── Layer 1.5: rectangle column boundary method ──
            has_header_only = tables and any(t and len(t) == 1 and len(t[0]) >= 3 for t in tables)
            if has_header_only:
                t0 = time.time()
                table = _extract_by_rect_columns(work_page)
                _t("L1.5_rect", t0)
                if table and len(table) >= 3:
                    _done = _emit(
                        _recover_header_from_zone([table], work_page, table_zone_bbox, page_plum),
                        "rect_columns",
                    )
                    if _done is not None:
                        return _done

        # ── Layer 1b: text strategy ──
        t0 = time.time()
        tables = work_page.extract_tables(table_settings=TABLE_SETTINGS)
        _t("L1b_text", t0)
        if tables and _tables_look_valid(tables, has_borders=has_borders):
            _done = _emit(
                _recover_header_from_zone(tables, work_page, table_zone_bbox, page_plum),
                "text",
            )
            if _done is not None:
                return _done

    # ── Layer 0.9: pdfplumber safety net ──
    # T3-1: Skip when classify_hint is 'char' (pdfplumber can't handle char-only tables)
    # EPO: Always run oracle layer when BCS requests pdfplumber_default (borderless ledgers)
    _run_l09 = classify_hint != "char" or (
        _pr.use_bcs and _pr.profile and _pr.profile.bcs_oracle_layer == "pdfplumber_default"
    )
    _ran_l1b_text = classify_hint != "char" and "L1b_text" in timings

    if _run_l09 and not _ran_l09_early:
        t0 = time.time()
        tables = work_page.extract_tables()
        _t("L0.9_default", t0)
        if tables and _tables_look_valid(tables, has_borders=has_borders):
            _done = _emit(
                _recover_header_from_zone(tables, work_page, table_zone_bbox, page_plum),
                "pdfplumber_default",
            )
            if _done is not None:
                return _done

        if not _ran_l1b_text:
            t0 = time.time()
            tables = work_page.extract_tables(table_settings=TABLE_SETTINGS)
            _t("L0.9_text", t0)
            if tables and _tables_look_valid(tables, has_borders=has_borders):
                _done = _emit(
                    _recover_header_from_zone(tables, work_page, table_zone_bbox, page_plum),
                    "text_fallback",
                )
                if _done is not None:
                    return _done
    else:
        timings["L0.9_skipped"] = "char_hint"

    # (RapidTable at L2.5 — too slow for early pipeline, ~10s/page CPU)

    _skip_l2 = _bcs_ledger and _has_oracle_candidate

    # ── Layer 2 Primary: Dual-Axis Signal Processor (single O(n) pass) ──
    if not _skip_l2:
        t0 = time.time()
        try:
            from .signal_processor import extract_table_by_signal

            signal_table = extract_table_by_signal(work_page, global_tensor_x=global_grid_x)
            _t("L2_signal", t0)
            if signal_table and len(signal_table) >= 2:
                sig_vocab = _score_header_by_vocabulary(signal_table[0])
                if sig_vocab >= 3:
                    if _tables_look_valid([signal_table], has_borders=has_borders):
                        _done = _emit([signal_table], "signal_processor")
                        if _done is not None:
                            return _done
                if _DEBUG:
                    logger.debug(
                        "L2 signal_processor: %d rows, vocab=%d (below threshold)",
                        len(signal_table),
                        sig_vocab,
                    )
        except Exception as exc:
            _t("L2_signal", t0)
            if _DEBUG:
                logger.debug("L2 signal_processor error: %s", exc)
    else:
        timings["L2_signal"] = 0
        timings["L2_signal_skipped"] = "bcs_oracle"

    # ── Layer 2 Fallback: char-level competitive selection (parallel execution) ──
    _layer2_fallback = None
    if not _skip_l2:
        t0 = time.time()

        def _run_method(name, func, wp):
            """Run a char-level method in a thread; return (table, name, score) or None."""
            try:
                tbl = func(wp)
                if tbl and len(tbl) >= 2:
                    score = _score_header_by_vocabulary(tbl[0])
                    return (tbl, name, score)
            except Exception as ex:
                logger.debug(f"L2 {name} error: {ex}")
            return None

        methods = [
            ("header_anchors", detect_columns_by_header_anchors),
            ("header_guided", detect_columns_by_header_guided),
            ("grid_reconstructor", detect_table_via_grid),
            ("word_anchors", detect_columns_by_word_anchors),
            ("data_voting", detect_columns_by_data_voting),
            ("whitespace_projection", detect_columns_by_whitespace_projection),
        ]

        candidates: list[tuple[list[list[str]], str, int]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_run_method, name, func, work_page): name for name, func in methods}
            # Deterministic: collect ALL results (no early exit) to avoid
            # thread-race non-determinism from as_completed ordering.
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result is not None:
                    candidates.append(result)

        _t("L2_char_level", t0)

        if candidates:
            # Layer 2 method priority: header_guided and grid_reconstructor
            # are preferred over word_anchors (they produce better column segmentation).
            _L2_METHOD_PRIO: dict[str, int] = {
                "grid_reconstructor": 5,
                "header_guided": 4,
                "header_anchors": 3,
                "word_anchors": 2,
                "data_voting": 1,
                "whitespace_projection": 0,
            }

            def _get_sort_key(c):
                tbl = c[0]
                vocab_score = c[2]
                method_name = c[1]
                method_prio = _L2_METHOD_PRIO.get(method_name, 0)
                row_count = len(tbl)
                stuffed_count = sum(1 for row in tbl[:10] for cell in row if _cell_is_stuffed(str(cell or "")))
                return (vocab_score, method_prio, row_count - stuffed_count * 10)

            candidates.sort(key=_get_sort_key, reverse=True)
            best_table, best_layer, best_score = candidates[0]
            # Post-process dense rows (evenly distribute fused values).
            # Applied regardless of which char-level method won BCS.
            try:
                from docmirror.tables.utils import _refine_dense_rows as _rdfn

                _refined = _rdfn(best_table, [], [])
                if _refined is not None:
                    best_table = _refined
            except Exception:
                pass
            if best_score >= 3:
                _done = _emit([best_table], best_layer)
                if _done is not None:
                    return _done
            _layer2_fallback = (best_table, best_layer)
    else:
        timings["L2_char_level"] = 0
        timings["L2_char_skipped"] = "bcs_oracle"

    # ── Layer 2.5: RapidTable vision model (slow ~10 s, only when L2 also fails) ──
    # G4: Skip RapidTable when document is large or upstream confidence is high enough
    import os

    _rapid_max_pages_raw = os.getenv("DOCMIRROR_TABLE_RAPID_MAX_PAGES", "").strip()
    _rapid_max_pages = int(_rapid_max_pages_raw) if _rapid_max_pages_raw else None
    _rapid_min_conf = float(os.getenv("DOCMIRROR_TABLE_RAPID_MIN_CONFIDENCE_THRESHOLD", "0.5"))
    _skip_rapid = False
    _skip_reason = None
    if _bcs_ledger:
        _skip_rapid = True
        _skip_reason = "bcs_ledger_oracle"
    if document_page_count is not None and _rapid_max_pages is not None and document_page_count > _rapid_max_pages:
        _skip_rapid = True
        _skip_reason = "document_page_count_exceeded"
    if _layer2_fallback and not _skip_rapid:
        _upstream_conf = _compute_table_confidence([_layer2_fallback[0]], _layer2_fallback[1])
        if _upstream_conf >= _rapid_min_conf:
            _skip_rapid = True
            _skip_reason = "upstream_confidence_above_threshold"
    t0 = time.time()
    if _skip_rapid:
        timings["L2.5_rapid_table"] = 0
        timings["rapid_table_skipped"] = _skip_reason or "config"
        logger.debug(f"RapidTable skipped: {_skip_reason}")
        rapid_result = None
    else:
        rapid_result = _extract_by_rapid_table(page_plum)
        _t("L2.5_rapid_table", t0)
    if rapid_result and len(rapid_result) >= 2:
        rt_vocab = _score_header_by_vocabulary(rapid_result[0])
        if rt_vocab >= 2:  # At least 2 header vocabulary matches
            _done = _emit([rapid_result], "rapid_table")
            if _done is not None:
                return _done

    # ── Layer 3: x-coordinate clustering ──
    t0 = time.time()
    table = detect_columns_by_clustering(work_page)
    _t("L3_clustering", t0)
    if table and len(table) >= 2:
        _done = _emit([table], "x_clustering")
        if _done is not None:
            return _done

    # Layer 2 low-score candidate fallback (still better than pdfplumber default)
    if _layer2_fallback:
        _done = _emit(_layer2_fallback[1], [_layer2_fallback[0]])
        if _done is not None:
            return _done

    tables, layer, conf = _pr.finalize(page_plum.extract_tables() or [], "fallback", 0.0)
    result = _return(tables, layer)
    return result if result is not None else (tables, layer, conf)


def extract_tables_layered_with_geometry(
    page_plum,
    table_zone_bbox: tuple[float, float, float, float] | None = None,
    **kwargs,
) -> tuple[list[list[list[str]]], str, float, list[dict]]:
    """Run layered extraction and attach conservative geometry companions."""
    tables, layer, confidence = extract_tables_layered(
        page_plum,
        table_zone_bbox=table_zone_bbox,
        **kwargs,
    )
    from docmirror.geometry.table_geometry import build_table_geometry

    default_bbox = (
        0.0,
        0.0,
        float(getattr(page_plum, "width", 0.0) or 0.0),
        float(getattr(page_plum, "height", 0.0) or 0.0),
    )
    geometry_payloads = [
        build_table_geometry(
            table,
            chars=list(getattr(page_plum, "chars", None) or []),
            table_bbox=table_zone_bbox or default_bbox,
            table_index=idx,
            geometry_source=layer,
            geometry_confidence=confidence,
        ).to_attrs()
        for idx, table in enumerate(tables or [])
    ]
    return tables, layer, confidence, geometry_payloads


from docmirror.tables.layers.backends import (
    extract_by_pymupdf as _extract_by_pymupdf,
)
from docmirror.tables.layers.backends import (
    extract_by_rapid_table as _extract_by_rapid_table,
)
