# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""UOP recognize stage — delegates to rapidocr / aistudio engines."""

from docmirror.core.ocr.aistudio_provider import call_aistudio_layout_ocr
from docmirror.core.ocr.vision.rapidocr_engine import get_ocr_engine

__all__ = ["call_aistudio_layout_ocr", "get_ocr_engine"]
