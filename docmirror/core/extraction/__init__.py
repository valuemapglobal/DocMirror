# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Extraction package — core PDF parsing engine and foundation utilities.

Purpose: Top-level namespace for ``CoreExtractor``, ``FitzEngine``, and
supporting extraction helpers that drive the main parse loop.

Main components: ``CoreExtractor``, ``FitzEngine`` (re-exported at package level).

Upstream: ``entry.factory`` via ``ParserDispatcher``.

Downstream: ``pipeline``, ``segment``, ``extract``, ``ocr``, ``table``.
"""

from .extractor import CoreExtractor  # noqa: F401
from .foundation import FitzEngine  # noqa: F401
from docmirror.core.analyze.pre_analyzer import PreAnalysisResult, PreAnalyzer  # noqa: F401

__all__ = [
    "CoreExtractor",
    "FitzEngine",
    "PreAnalyzer",
    "PreAnalysisResult",
]
