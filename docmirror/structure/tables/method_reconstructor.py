# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Table Method Reconstructor — registry-based wrapper for all 18 extraction methods.

Migrates the hardcoded layered pipeline in ``engine.py`` to a pluggable
``TableMethodReconstructor`` protocol + ``TableMethodRegistry``, enabling:

- Independent registration of extraction methods
- Parallel dispatch with consistent error handling
- Seamless integration with ``RegionReconstructorRegistry``
- Feature-flag controlled rollout with a legacy engine fallback

Protocol: ``TableMethodReconstructor``
    - ``id``: unique method identifier (e.g. "header_guided").
    - ``score(page_plum, profile)``: relative priority (used by BCS).
    - ``reconstruct(page_plum, profile)``: return table rows or None.

Registry: ``TableMethodRegistry``
    - ``register(method)``: add a reconstructor.
    - ``reconstruct_all(page_plum, profile)``: run all registered methods in
      parallel and return ``list[tuple[str, list[list[str]], float]]``.
"""

from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Protocol
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TableMethodContext:
    """Optional runtime context for methods that need more than a pdfplumber page."""

    fitz_page: Any | None = None
    table_zone_bbox: tuple[float, float, float, float] | None = None
    crop_y0: float | None = None
    crop_y1: float | None = None
    table_template: Any | None = None
    global_grid_x: list[float] | None = None
    has_borders: bool = False
    text_fallback_settings: dict[str, Any] | None = None
    line_settings: dict[str, Any] | None = None


class TableMethodReconstructor:
    """Protocol for a single table extraction method."""

    id: str
    supported_layers: set[str] = {"char", "line", "native", "vision", "clustering", "template", "text"}

    def score(self, page_plum: Any, profile: Any | None = None, context: TableMethodContext | None = None) -> float:
        """Return relative priority (0.0-1.0) used by BCS layer_prior."""
        _ = page_plum, profile, context
        return 0.5

    def reconstruct(
        self,
        page_plum: Any,
        profile: Any | None = None,
        context: TableMethodContext | None = None,
    ) -> list[list[str]] | None:
        """Extract table rows from a pdfplumber page. Return None if no table found."""
        _ = page_plum, profile, context
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Wrapper: PDF Native Methods (L0.x)
# ──────────────────────────────────────────────────────────────────────────────

class PipeDelimitedReconstructor(TableMethodReconstructor):
    id = "pipe_delimited"
    supported_layers = {"native"}

    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.engine import _extract_by_pipe_delimited
        return _extract_by_pipe_delimited(page_plum)


class PyMuPDFNativeReconstructor(TableMethodReconstructor):
    id = "pymupdf_native"
    supported_layers = {"native"}

    def reconstruct(self, page_plum, profile=None, context=None):
        _ = page_plum, profile
        if context is None or context.fitz_page is None:
            return None
        from docmirror.structure.tables.layers.backends import extract_by_pymupdf

        bbox = None
        if context.table_zone_bbox:
            y0 = context.crop_y0 if context.crop_y0 is not None else context.table_zone_bbox[1]
            y1 = context.crop_y1 if context.crop_y1 is not None else context.table_zone_bbox[3]
            bbox = (0, y0, context.fitz_page.rect.width, y1)
        tables = extract_by_pymupdf(context.fitz_page, bbox)
        for table in tables or []:
            if table and len(table) >= 3 and len(table[0]) >= 2:
                return table
        return None


class PdfPlumberDefaultReconstructor(TableMethodReconstructor):
    id = "pdfplumber_default"
    supported_layers = {"native"}
    def score(self, page_plum, profile=None, context=None): return 1.0
    def reconstruct(self, page_plum, profile=None, context=None):
        tables = page_plum.extract_tables() or []
        return tables[0] if tables else None


class LinesReconstructor(TableMethodReconstructor):
    id = "lines"
    supported_layers = {"line"}
    def score(self, page_plum, profile=None, context=None): return 0.80
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.classifier import TABLE_SETTINGS_LINES

        settings = context.line_settings if context and context.line_settings else TABLE_SETTINGS_LINES
        tables = page_plum.extract_tables(table_settings=settings) or []
        return tables[0] if tables else None


class TextReconstructor(TableMethodReconstructor):
    id = "text"
    supported_layers = {"text"}
    def score(self, page_plum, profile=None, context=None): return 0.85
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.classifier import TABLE_SETTINGS

        tables = page_plum.extract_tables(table_settings=TABLE_SETTINGS) or []
        return tables[0] if tables else None


class TextFallbackReconstructor(TableMethodReconstructor):
    id = "text_fallback"
    supported_layers = {"native", "text"}
    def score(self, page_plum, profile=None, context=None): return 0.70
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.classifier import TABLE_SETTINGS

        tables = page_plum.extract_tables(table_settings=TABLE_SETTINGS) or []
        return tables[0] if tables else None


# ──────────────────────────────────────────────────────────────────────────────
# Wrapper: Line/Rect Methods (L1.x)
# ──────────────────────────────────────────────────────────────────────────────

class HlineColumnsReconstructor(TableMethodReconstructor):
    id = "hline_columns"
    supported_layers = {"line"}
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.char.hline import _extract_by_hline_columns
        return _extract_by_hline_columns(page_plum)


class RectColumnsReconstructor(TableMethodReconstructor):
    id = "rect_columns"
    supported_layers = {"line"}
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.char.rect import _extract_by_rect_columns
        return _extract_by_rect_columns(page_plum)


# ──────────────────────────────────────────────────────────────────────────────
# Wrapper: Char-Level Methods (L2.x) — 6 methods
# ──────────────────────────────────────────────────────────────────────────────

class HeaderAnchorsReconstructor(TableMethodReconstructor):
    id = "header_anchors"
    supported_layers = {"char"}
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.char.header_anchors import detect_columns_by_header_anchors
        return detect_columns_by_header_anchors(page_plum)


class HeaderGuidedReconstructor(TableMethodReconstructor):
    id = "header_guided"
    supported_layers = {"char"}
    def score(self, page_plum, profile=None, context=None): return 0.65
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.char.header_column_finder import detect_columns_by_header_guided
        return detect_columns_by_header_guided(page_plum)


class GridReconstructorWrapper(TableMethodReconstructor):
    id = "grid_reconstructor"
    supported_layers = {"char"}
    def score(self, page_plum, profile=None, context=None): return 0.80
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.char.grid_reconstructor import detect_table_via_grid
        return detect_table_via_grid(page_plum)


class WordAnchorsReconstructor(TableMethodReconstructor):
    id = "word_anchors"
    supported_layers = {"char"}
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.char.word_anchors import detect_columns_by_word_anchors
        return detect_columns_by_word_anchors(page_plum)


class DataVotingReconstructor(TableMethodReconstructor):
    id = "data_voting"
    supported_layers = {"char"}
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.char.data_voting import detect_columns_by_data_voting
        return detect_columns_by_data_voting(page_plum)


class WhitespaceProjectionReconstructor(TableMethodReconstructor):
    id = "whitespace_projection"
    supported_layers = {"char"}
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.char.projection import detect_columns_by_whitespace_projection
        return detect_columns_by_whitespace_projection(page_plum)


# ──────────────────────────────────────────────────────────────────────────────
# Wrapper: Clustering (L3)
# ──────────────────────────────────────────────────────────────────────────────

class ClusteringReconstructor(TableMethodReconstructor):
    id = "x_clustering"
    supported_layers = {"clustering"}
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.char.clustering import detect_columns_by_clustering
        return detect_columns_by_clustering(page_plum)


# ──────────────────────────────────────────────────────────────────────────────
# Wrapper: Others
# ──────────────────────────────────────────────────────────────────────────────

class SignalProcessorReconstructor(TableMethodReconstructor):
    id = "signal_processor"
    supported_layers = {"char"}
    def score(self, page_plum, profile=None, context=None): return 0.70
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.signal_processor import extract_table_by_signal

        return extract_table_by_signal(page_plum, global_tensor_x=context.global_grid_x if context else None)


class RapidTableReconstructor(TableMethodReconstructor):
    id = "rapid_table"
    supported_layers = {"vision"}
    def score(self, page_plum, profile=None, context=None): return 0.12
    def reconstruct(self, page_plum, profile=None, context=None):
        from docmirror.structure.tables.engine import _extract_by_rapid_table
        return _extract_by_rapid_table(page_plum)


class TemplateInjectionReconstructor(TableMethodReconstructor):
    id = "template_injection"
    supported_layers = {"template"}
    def score(self, page_plum, profile=None, context=None): return 0.99
    def reconstruct(self, page_plum, profile=None, context=None):
        if context is None or context.table_template is None:
            return None
        from docmirror.structure.tables.template_injector import extract_by_injected_template

        return extract_by_injected_template(page_plum, context.table_template)


# ──────────────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────────────

class TableMethodRegistry:
    """Parallel dispatch of table extraction methods."""

    def __init__(self, methods: list[TableMethodReconstructor] | None = None) -> None:
        self._methods: list[TableMethodReconstructor] = methods or _builtin_methods()

    def register(self, method: TableMethodReconstructor) -> None:
        self._methods.append(method)

    def list_ids(self) -> list[str]:
        return [m.id for m in self._methods]

    def get(self, method_id: str) -> TableMethodReconstructor | None:
        for method in self._methods:
            if method.id == method_id:
                return method
        return None

    def reconstruct_one(
        self,
        method_id: str,
        page_plum: Any,
        profile: Any | None = None,
        *,
        context: TableMethodContext | None = None,
    ) -> tuple[str, list[list[str]], float] | None:
        method = self.get(method_id)
        if method is None:
            return None
        try:
            table = method.reconstruct(page_plum, profile, context)
            if table and len(table) >= 2:
                return (method.id, table, method.score(page_plum, profile, context))
        except Exception as exc:
            logger.debug("TableMethodRegistry %s error: %s", method.id, exc)
        return None

    def reconstruct_all(
        self,
        page_plum: Any,
        profile: Any | None = None,
        *,
        layers: set[str] | None = None,
        method_ids: list[str] | None = None,
        context: TableMethodContext | None = None,
        max_workers: int = 6,
    ) -> list[tuple[str, list[list[str]], float]]:
        """Run all matching methods in parallel, return (layer, rows, score)."""
        allowed = set(method_ids or [])
        target = [
            m for m in self._methods
            if (not allowed or m.id in allowed) and (layers is None or bool(m.supported_layers & layers))
        ]
        if not target:
            return []

        def _run(method: TableMethodReconstructor):
            try:
                tbl = method.reconstruct(page_plum, profile, context)
                if tbl and len(tbl) >= 2:
                    return (method.id, tbl, method.score(page_plum, profile, context))
            except Exception as exc:
                logger.debug("TableMethodRegistry %s error: %s", method.id, exc)
            return None

        results: list[tuple[str, list[list[str]], float]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_run, m): m.id for m in target}
            for future in concurrent.futures.as_completed(futures):
                r = future.result()
                if r is not None:
                    results.append(r)
        return results


def _builtin_methods() -> list[TableMethodReconstructor]:
    """Default set of all registry-managed table methods."""
    return [
        PipeDelimitedReconstructor(),
        PyMuPDFNativeReconstructor(),
        PdfPlumberDefaultReconstructor(),
        LinesReconstructor(),
        HlineColumnsReconstructor(),
        RectColumnsReconstructor(),
        TextReconstructor(),
        TextFallbackReconstructor(),
        HeaderAnchorsReconstructor(),
        HeaderGuidedReconstructor(),
        GridReconstructorWrapper(),
        WordAnchorsReconstructor(),
        DataVotingReconstructor(),
        WhitespaceProjectionReconstructor(),
        ClusteringReconstructor(),
        SignalProcessorReconstructor(),
        RapidTableReconstructor(),
        TemplateInjectionReconstructor(),
    ]


__all__ = [
    "TableMethodContext",
    "TableMethodReconstructor",
    "TableMethodRegistry",
]
