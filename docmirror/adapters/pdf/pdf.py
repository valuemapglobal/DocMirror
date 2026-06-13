# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
PDF Adapter — PDF → ParseResult
=================================

Extracts PDF content via ``CoreExtractor``, bridges to ParseResult,
then delegates to ``BaseParser.perceive()`` for middleware enrichment.
"""

from __future__ import annotations

import logging
from pathlib import Path

from docmirror.framework.base import BaseParser

logger = logging.getLogger(__name__)


class PDFAdapter(BaseParser):
    """
    PDF format adapter.

    Uses CoreExtractor for raw extraction, then relies on the base class
    ``perceive()`` to run the shared Orchestrator middleware pipeline.

    Args:
        enhance_mode: Enhancement level. One of "raw", "standard", or "full".
    """

    def __init__(self, enhance_mode: str = "standard", **kwargs):
        self._enhance_mode = enhance_mode

    async def to_parse_result(self, file_path: Path, **kwargs) -> "ParseResult":
        """
        Extract a PDF into a ParseResult with provenance pre-filled.

        Pipeline: CoreExtractor → BaseResult → ParseResultBridge → ParseResult.
        """
        from docmirror.core.extraction.extractor import CoreExtractor
        from docmirror.models.construction.parse_result_bridge import ParseResultBridge

        logger.info(f"[PDFAdapter] Starting extraction for: {file_path}")
        extractor = CoreExtractor()
        base_result = await extractor.extract(file_path)
        logger.info(f"[PDFAdapter] Completed extraction for: {file_path}")

        pr = ParseResultBridge.from_base_result(base_result)

        # PDF-specific parser_info
        pr.parser_info.parser_name = "DocMirror"
        pr.parser_info.table_engine = "pymupdf_native"
        pr.parser_info.page_count = len(base_result.pages)

        # ── Fill provenance (lightweight, no re-read of full file) ──
        if pr.provenance is None:
            from docmirror.models.entities.parse_result import ProvenanceInfo

            try:
                stat = file_path.stat()
                pr.provenance = ProvenanceInfo(
                    file_type="pdf",
                    file_size=stat.st_size,
                )
            except OSError:
                pass

        return pr

    async def perceive(self, file_path: Path, **context) -> "ParseResult":
        """
        Full pipeline: PDF → middleware → ParseResult.

        Injects the adapter's enhance_mode before delegating to base class.
        """
        context.setdefault("enhance_mode", self._enhance_mode)
        context.setdefault("file_type", "pdf")
        return await super().perceive(file_path, **context)
