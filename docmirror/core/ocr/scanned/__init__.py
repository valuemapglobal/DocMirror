# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Scanned OCR subpackage — full-page scanned document analysis.

Purpose: Namespace for scanned-page analysis combining preprocess, OCR, and
table reconstruction.

Main components: ``analyze_scanned_page``, ``ocr_extract_universal``.

Upstream: ``ocr.pipeline``, quality router.

Downstream: ``pipeline.handlers.scanned_page`` blocks.
"""

from docmirror.core.ocr.scanned.analyze_page import analyze_scanned_page
from docmirror.core.ocr.scanned.universal import ocr_extract_universal

__all__ = ["analyze_scanned_page", "ocr_extract_universal"]
