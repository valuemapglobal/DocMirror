# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
OCR vision subpackage — local vision models (OCR, seal detection).

Purpose: Namespace for on-device vision engines (RapidOCR, seal/stamp
detection) used during extraction.

Main components: ``RapidOCREngine``, ``SealDetector``.

Upstream: Preprocessed page/zone images.

Downstream: ``ocr.recognize``, ``pipeline.handlers`` enrichment.
"""

