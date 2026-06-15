# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Document security and forgery detection utilities.

Re-exports PDF tampering checks and image Error Level Analysis (ELA) helpers
from ``forgery_detector``. Results are advisory signals for downstream review,
not legal or compliance conclusions.
"""

from docmirror.framework.security.forgery_detector import detect_image_forgery, detect_pdf_forgery

__all__ = ["detect_image_forgery", "detect_pdf_forgery"]
