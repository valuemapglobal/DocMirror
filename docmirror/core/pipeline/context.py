# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Pipeline context objects — shared state for document and page extraction.

Purpose: Holds per-page and per-document mutable state (fitz page, profile,
template, timings) passed through pipeline stages without global side effects.

Main components: ``PageExtractionContext``, ``DocumentPipelineContext``.

Upstream: ``CoreExtractor`` / ``PagePipeline.run``.

Downstream: All ``pipeline.stages`` and ``pipeline.handlers``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParseContext:
    """Request-scoped parse context propagated from dispatcher to adapters.

    This carries user intent and file metadata without relying on process-wide
    environment mutations.
    """

    file_path: Path
    file_type: str = "unknown"
    content_model: str = ""
    capability_id: str = ""
    file_size: int = 0
    mime_type: str = ""
    checksum: str = ""
    is_forged: bool | None = None
    forgery_reasons: tuple[str, ...] = ()
    enhance_mode: str = "standard"
    max_pages: int | None = None
    request_id: str = ""
    started_at: datetime | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def to_perceive_context(self) -> dict[str, Any]:
        """Return a kwargs-compatible context for existing adapter APIs."""
        return {
            "parse_context": self,
            "file_type": self.file_type,
            "content_model": self.content_model,
            "capability_id": self.capability_id,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "checksum": self.checksum,
            "is_forged": self.is_forged,
            "forgery_reasons": list(self.forgery_reasons),
            "enhance_mode": self.enhance_mode,
            "max_pages": self.max_pages,
            "request_id": self.request_id,
            "started_at": self.started_at,
            "options": self.options,
        }


@dataclass
class PageExtractionContext:
    """Encapsulates all parameters for single-page extraction."""

    page_plum: Any  # pdfplumber page
    fitz_page: Any  # PyMuPDF page
    fitz_doc: Any  # PyMuPDF document
    page_idx: int  # 0-based page index
    layout_al: Any  # layout analysis result
    cleaned_path: Any  # pre-processed PDF path
    is_digital: bool = True  # digital vs scanned
    strategy_params: dict[str, Any] = field(default_factory=dict)
    page_quality: int = 100  # image quality 0-100
    content_type: str = "unknown"  # table_dominant/text_dominant/mixed/scanned
    zone_template: list | None = None  # zone template for homogeneous docs
    global_grid_x: list | None = None  # global x-coordinate grid
    global_table_template: Any = None  # golden page template
    extraction_profile: Any = None  # ExtractionProfile (EPO)


@dataclass
class DocumentPipelineContext:
    """Document-level extraction state (early-bound profile + pre-analysis)."""

    file_path: Path
    profile: Any | None = None
    pre_analysis: Any | None = None
    fitz_doc: Any = None
    options: dict[str, Any] = field(default_factory=dict)


__all__ = ["DocumentPipelineContext", "PageExtractionContext", "ParseContext"]
