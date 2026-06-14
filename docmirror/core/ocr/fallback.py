# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Scanned page OCR fallback facade (CPA design 12 UOP)."""

from docmirror.core.ocr.preprocess.legacy_fallback import (
    _resolve_external_ocr_provider,
    assess_image_quality_from_bgr,
)
from docmirror.core.ocr.scanned.analyze_page import analyze_scanned_page
from docmirror.core.ocr.scanned.universal import ocr_extract_universal

__all__ = [
    "_resolve_external_ocr_provider",
    "analyze_scanned_page",
    "assess_image_quality_from_bgr",
    "ocr_extract_universal",
]
