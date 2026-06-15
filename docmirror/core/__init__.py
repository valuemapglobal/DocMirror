# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror core package — document processing engine public surface.

Purpose: Re-exports the primary extraction entry points (``CoreExtractor``,
``FitzEngine``, ``PreAnalyzer``) for callers that import from
``docmirror.core`` directly.

Main components: ``CoreExtractor``, ``FitzEngine``, ``PreAnalyzer``,
``PreAnalysisResult``.

Upstream: Application code and ``docmirror.core.entry`` factory.

Downstream: ``extraction``, ``analyze``, and the full parse pipeline.
"""

from .extraction.extractor import CoreExtractor
from .extraction.foundation import FitzEngine
from .analyze.pre_analyzer import PreAnalysisResult, PreAnalyzer

__all__ = ["CoreExtractor", "FitzEngine", "PreAnalyzer", "PreAnalysisResult"]
