# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
OCR recognize subpackage — text recognition runners.

Purpose: Hosts recognition orchestration that merges multi-scale OCR runs into
unified word lists.

Main components: ``runner_legacy._run_ocr`` (primary legacy runner).

Upstream: Preprocessed page images.

Downstream: ``ocr.reconstruct``, ``ocr.postprocess``.
"""

from docmirror.core.ocr.aistudio_provider import call_aistudio_layout_ocr
from docmirror.core.ocr.vision.rapidocr_engine import get_ocr_engine

__all__ = ["call_aistudio_layout_ocr", "get_ocr_engine"]
