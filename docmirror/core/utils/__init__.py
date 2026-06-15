# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Utils package — shared text, image, vocabulary, and quality helpers.

Purpose: Cross-cutting utilities used by extraction, OCR, table, and pipeline
modules (normalization, watermark removal, quality assessment).

Main components: Submodules ``text_utils``, ``vocabulary``, ``watermark``, etc.

Upstream: Raw text, images, and chars from any pipeline stage.

Downstream: Nearly all ``core`` subpackages.
"""

