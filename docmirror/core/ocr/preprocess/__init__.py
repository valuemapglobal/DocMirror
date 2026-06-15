# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
OCR preprocess subpackage — image preparation before recognition.

Purpose: Package marker for legacy fallback preprocessing (deskew, upscale,
quality assessment) used on scanned paths.

Main components: Functions from ``legacy_fallback``.

Upstream: Raw rendered page images.

Downstream: ``ocr.recognize.runner_legacy``, ``ocr.scanned.analyze_page``.
"""

from docmirror.core.ocr.image_preprocessing import *  # noqa: F403
