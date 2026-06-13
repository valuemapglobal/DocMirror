# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
ExtractionHint — per-page hint from layout analysis to table engine
====================================================================

Bridges the gap between ``analyze_document_layout`` (PyMuPDF) and
``extract_tables_layered`` (pdfplumber), eliminating redundant
analysis.

``_quick_classify()`` in ``classifier.py`` still runs as a
verification step but no longer needs to recompute column/row
statistics from scratch.

Usage::

    hint = ExtractionHint.from_al_page_layout(layout_al)
    tables, layer, conf = extract_tables_layered(
        page_plum, layout_hint=hint, ...
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractionHint:
    """Per-page extraction hint produced by layout analysis.

    All fields are ``Optional`` to allow partial population when
    layout analysis is unavailable (e.g., fallback paths).

    Attributes:
        has_table: Whether the page contains a table.
        is_continuation: Whether the page is a cross-page table continuation.
        table_count: Estimated number of tables on the page.
        image_count: Number of images on the page.
        text_region_count: Number of text regions on the page.
        is_scanned: Whether the page is a scan (no text layer).
        has_borders: Whether table borders/lines were detected (from fitz drawings).
        ignore: If True, skip all table extraction (e.g., scanned/empty pages).
    """

    has_table: bool | None = None
    is_continuation: bool | None = None
    table_count: int | None = None
    image_count: int | None = None
    text_region_count: int | None = None
    is_scanned: bool | None = None
    has_borders: bool | None = None
    ignore: bool = False

    @classmethod
    def from_al_page_layout(cls, layout: Any) -> ExtractionHint:
        """Convert from an ``ALPageLayout`` (layout analysis result).

        Extracts table presence and continuation info from fitz-based
        layout analysis, allowing ``extract_tables_layered`` to skip
        its own ``_quick_classify``.
        """
        return cls(
            has_table=getattr(layout, "has_table", None),
            is_continuation=getattr(layout, "is_continuation", None),
            table_count=getattr(layout, "table_count", None),
            image_count=getattr(layout, "image_count", None),
            text_region_count=getattr(layout, "text_region_count", None),
            is_scanned=getattr(layout, "is_scanned", None),
            has_borders=None,  # borders info is from pdfplumber lines, not fitz drawings
            ignore=False,
        )

    @classmethod
    def ignore_page(cls) -> ExtractionHint:
        """Create a hint that tells the engine to skip extraction entirely."""
        return cls(ignore=True)

    def to_dict(self) -> dict:
        return {
            "has_table": self.has_table,
            "is_continuation": self.is_continuation,
            "table_count": self.table_count,
            "image_count": self.image_count,
            "text_region_count": self.text_region_count,
            "is_scanned": self.is_scanned,
            "has_borders": self.has_borders,
            "ignore": self.ignore,
        }
