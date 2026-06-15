# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Pipeline package — document- and page-level orchestration of extraction stages.

Purpose: Coordinates the multi-stage parse flow from document open through
per-page prepare/segment/assemble/finalize.

Main components: ``DocumentPipeline``, ``PagePipeline``, ``PageExtractor``.

Upstream: ``extraction.extractor.CoreExtractor``.

Downstream: ``segment``, ``extract``, ``ocr``, ``table``, ``physical.models``.
"""

from docmirror.core.pipeline.context import DocumentPipelineContext, PageExtractionContext
from docmirror.core.pipeline.document_pipeline import DocumentPipeline
from docmirror.core.pipeline.page_extractor import PageExtractor
from docmirror.core.pipeline.page_pipeline import PagePipeline
from docmirror.core.pipeline.pdf_processor import PdfSyncProcessor

__all__ = [
    "DocumentPipeline",
    "DocumentPipelineContext",
    "PageExtractionContext",
    "PageExtractor",
    "PagePipeline",
    "PdfSyncProcessor",
]
