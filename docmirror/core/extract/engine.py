# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Layered table extraction engine — main entry point.

Split from ``table_extraction.py``.
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from docmirror.models.entities.extraction_profile import ExtractionProfile
    from .template_injector import GlobalTableTemplate

from ..utils.vocabulary import _RE_IS_AMOUNT, _RE_IS_DATE, _is_header_cell, _is_header_row, _score_header_by_vocabulary

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
    detect_columns_by_whitespace_projection,
    detect_columns_by_word_anchors,
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
from .pdfplumber_strategy import _recover_header_from_zone
from .pipe_strategy import _extract_by_pipe_delimited


from .profile_run_state import ProfileRunState as _ProfileRunState
from .zone_crop import crop_simple_to_table_zone, crop_to_table_zone as _crop_to_table_zone
from .merged_cells import detect_merged_cells





def extract_tables_layered(
    page_plum,
    table_zone_bbox: tuple[float, float, float, float] | None = None,
    document_page_count: int | None = None,
    fitz_page=None,
    watermark_filtered: bool = False,
    layer_hint: str | None = None,
    zone_layer_hints: dict[str, str] | None = None,
    global_grid_x: list[float] | None = None,
    table_template: GlobalTableTemplate | None = None,
    pid_resample: bool = False,
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
    if table_template:
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

    # ── BCS ledger fast path: pdfplumber oracle before expensive L1/L2 layers ──
    if _bcs_ledger and not fast_continuation:
        early = _run_l09_pdfplumber()
        if early is not None:
            return early
        if _has_oracle_candidate:
            return _finalize_bcs_or_continue()

    # ── Layer 0.5: pipe separator (mainframe ASCII art) ──
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
            # Penalty: if extracted table has many stuffed cells, lower its priority
            # Tie-breaker: method name for deterministic ordering
            def _get_sort_key(c):
                tbl = c[0]
                vocab_score = c[2]
                method_name = c[1]
                row_count = len(tbl)
                stuffed_count = sum(1 for row in tbl[:10] for cell in row if _cell_is_stuffed(str(cell or "")))
                return (vocab_score, row_count - stuffed_count * 10, method_name)

            candidates.sort(key=_get_sort_key, reverse=True)
            best_table, best_layer, best_score = candidates[0]
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
        _done = _emit([_layer2_fallback[0]], _layer2_fallback[1])
        if _done is not None:
            return _done

    tables, layer, conf = _pr.finalize(page_plum.extract_tables() or [], "fallback", 0.0)
    result = _return(tables, layer)
    return result if result is not None else (tables, layer, conf)



from docmirror.core.extract.layers.backends import (
    extract_by_pymupdf as _extract_by_pymupdf,
    extract_by_rapid_table as _extract_by_rapid_table,
    parse_html_table as _parse_html_table,
)
