# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Pipeline context objects (CPA design 12 §4.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


__all__ = ["DocumentPipelineContext", "PageExtractionContext"]
