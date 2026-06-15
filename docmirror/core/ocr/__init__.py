# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
OCR package — optical character recognition for scanned and degraded pages.

Purpose: Namespace for OCR preprocessing, recognition engines, postprocess,
and scanned-page reconstruction paths.

Main components: ``ocr.pipeline``, ``ocr.fallback``, vision engines.

Upstream: Quality router scanned-page decisions, table OCR crops.

Downstream: ``pipeline.handlers.scanned_page``, ``table.ocr_scoring``.
"""
