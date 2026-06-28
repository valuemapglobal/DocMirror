# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
OCR reconstruct subpackage — grid reconstruction from OCR output.

Purpose: Re-exports legacy grid reconstruction utilities shared by scanned
analysis and table OCR paths.

Main components: Grid functions from ``grid_legacy``.

Upstream: OCR chars with geometry.

Downstream: ``ocr.scanned.analyze_page``, ``ocr.table_reconstruction``.
"""

from docmirror.structure.ocr.table_reconstruction import *  # noqa: F403
