# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Generic OCR postprocess — language-agnostic cleanup hooks.

Purpose: Applies baseline normalization passes on OCR strings before
column-aware or vocabulary stages.

Main components: Generic postprocess entry functions.

Upstream: ``ocr.ocr_postprocess`` normalized text.

Downstream: ``ocr.postprocess.column_aware``, block text fields.
"""

from docmirror.structure.ocr.ocr_postprocess import *  # noqa: F403
