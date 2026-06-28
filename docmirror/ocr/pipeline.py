# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
OCR pipeline — orchestrates full scanned-page OCR flow.

Purpose: Top-level scanned page runner wiring preprocess → recognize →
reconstruct → postprocess for ``pipeline.handlers.scanned_page``.

Main components: ``run_scanned_page``.

Upstream: ``pipeline.handlers.scanned_page``.

Downstream: ``ocr.scanned.analyze_page``, ``physical.models.Block``.
"""

from __future__ import annotations

from typing import Any

from docmirror.models.entities.domain import PageLayout


def run_scanned_page(
    fitz_page: Any,
    page_idx: int,
    *,
    page_quality: int = 100,
    content_type: str = "unknown",
    extraction_profile: Any = None,
    **kwargs: Any,
) -> PageLayout:
    """Run the scanned-page OCR pipeline and return a ``PageLayout``."""
    from docmirror.ocr.fallback import analyze_scanned_page

    return analyze_scanned_page(
        fitz_page,
        page_idx,
        page_quality=page_quality,
        content_type=content_type,
        extraction_profile=extraction_profile,
        **kwargs,
    )


# Backward-compatible alias
analyze_scanned_page = run_scanned_page

__all__ = ["run_scanned_page", "analyze_scanned_page"]
