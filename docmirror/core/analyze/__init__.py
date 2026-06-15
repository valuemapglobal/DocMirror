# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Analyze package — pre-extraction document analysis and quality routing.

Purpose: Hosts pre-parse analyzers that classify document quality and route
pages to appropriate extraction strategies before the main pipeline runs.

Main components: ``PreAnalyzer``, ``AdaptiveQualityRouter`` (via submodules).

Upstream: ``entry.factory`` / ``CoreExtractor`` open phase.

Downstream: ``pipeline.document_profile``, ``extract`` strategy selection,
``ocr.fallback``.
"""

from docmirror.core.analyze.pre_analyzer import PreAnalysisResult, PreAnalyzer
from docmirror.core.analyze.quality_router import AdaptiveQualityRouter

__all__ = ["PreAnalyzer", "PreAnalysisResult", "AdaptiveQualityRouter"]
