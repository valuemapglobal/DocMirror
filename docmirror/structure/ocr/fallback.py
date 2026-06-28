# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
OCR fallback — dispatches to configured external OCR when primary fails.

Purpose: Resolves fallback OCR provider chain and normalizes outputs into
word/char structures compatible with reconstruction.

Main components: Fallback dispatch helpers.

Upstream: Failed local OCR, ``ocr.preprocess.legacy_fallback``.

Downstream: ``ocr.scanned.analyze_page``, ``pipeline.handlers.scanned_page``.
"""

from docmirror.structure.ocr.preprocess.legacy_fallback import (
    _resolve_external_ocr_provider,
    assess_image_quality_from_bgr,
)
from docmirror.structure.ocr.scanned.analyze_page import analyze_scanned_page
from docmirror.structure.ocr.scanned.universal import ocr_extract_universal

__all__ = [
    "_resolve_external_ocr_provider",
    "analyze_scanned_page",
    "assess_image_quality_from_bgr",
    "ocr_extract_universal",
]
