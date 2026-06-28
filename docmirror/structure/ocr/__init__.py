# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""OCR package — optical character recognition for scanned and degraded pages.

Purpose: Public API for the OCR bounded context.

Main entry points: run_scanned_page for full-page OCR pipeline,
analyze_scanned_page for fallback OCR analysis.

Upstream: Quality router scanned-page decisions, table OCR crops.

Downstream: pipeline.handlers.scanned_page, table.ocr_scoring.
"""

from docmirror.structure.ocr.pipeline import run_scanned_page
from docmirror.structure.ocr.scanned.analyze_page import analyze_scanned_page

__all__ = ["run_scanned_page", "analyze_scanned_page"]
