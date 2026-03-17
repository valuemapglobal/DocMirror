# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
PDF Adapter — PDF → PerceptionResult
=====================================

Converts PDF files into structured output via two paths:

- ``to_base_result()``: Core extraction only (no middleware pipeline).
  Instantiates ``CoreExtractor`` directly and returns an immutable ``BaseResult``.

- ``perceive()``: Full pipeline (recommended). Uses a shared ``Orchestrator``
  singleton to run extraction + middleware enhancement, then maps the result
  to a ``PerceptionResult`` via ``PerceptionResultBuilder``.

- ``parse()``: **Deprecated** legacy interface kept for backward compatibility.
  Delegates to the same orchestrator but returns a ``ParserOutput`` instead.

The orchestrator singleton is lazily initialized on first use to avoid
import-time overhead from heavy dependencies (PyMuPDF, pdfplumber).
"""
from __future__ import annotations


import logging
import threading
from pathlib import Path

from docmirror.framework.base import BaseParser, ParserOutput
from docmirror.models.entities.domain import BaseResult

logger = logging.getLogger(__name__)

# Module-level orchestrator singleton with thread-safe lazy initialization.
_orchestrator = None
_orchestrator_lock = threading.Lock()


def _get_shared_orchestrator():
    """Return (and lazily create) the shared Orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:  # double-check
                from docmirror.framework.orchestrator import Orchestrator
                _orchestrator = Orchestrator()
    return _orchestrator


class PDFAdapter(BaseParser):
    """
    PDF format adapter.

    Uses a shared Orchestrator singleton to run the full extraction
    and enhancement pipeline, then builds a PerceptionResult in one step.

    Args:
        enhance_mode: Enhancement level for the middleware pipeline.
            One of "raw" (extraction only), "standard" (default), or "full".
    """

    def __init__(self, enhance_mode: str = "standard", **kwargs):
        self._enhance_mode = enhance_mode

    async def to_base_result(self, file_path: Path, **kwargs) -> BaseResult:
        """
        Extract a PDF into a BaseResult without running the middleware pipeline.

        This is useful when you only need the raw extraction output
        (text, tables, layout) without any business-specific enhancements.
        """
        from docmirror.core.extraction.extractor import CoreExtractor
        
        logger.info(f"[PDFAdapter] Starting raw extraction for: {file_path}")
        extractor = CoreExtractor()
        result = await extractor.extract(file_path)
        logger.info(f"[PDFAdapter] Completed raw extraction for: {file_path}")
        return result

    async def perceive(self, file_path: Path, **context) -> "PerceptionResult":
        """
        Full pipeline: PDF → PerceptionResult (recommended entry point).

        Steps:
            1. Orchestrator runs CoreExtractor + middleware pipeline → EnhancedResult
            2. PerceptionResultBuilder maps EnhancedResult → PerceptionResult
        """
        from docmirror.models.construction.builder import PerceptionResultBuilder

        orchestrator = _get_shared_orchestrator()
        file_type = (context.get("file_type") or "pdf").lower()
        
        logger.info(f"[PDFAdapter] Starting full perception pipeline for: {file_path} (mode: {self._enhance_mode})")
        enhanced = await orchestrator.run_pipeline(
            file_path=file_path,
            enhance_mode=self._enhance_mode,
            file_type=file_type,
        )

        logger.info(f"[PDFAdapter] Building PerceptionResult from enhanced data for: {file_path}")
        return PerceptionResultBuilder.build(
            enhanced.base_result,
            enhanced=enhanced,
            **context,
        )

    async def parse(self, file_path: Path, **kwargs) -> ParserOutput:
        """
        [DEPRECATED] Legacy interface — use perceive() instead.

        Runs the same orchestrator pipeline but returns a ParserOutput
        for backward compatibility with older callers.
        """
        orchestrator = _get_shared_orchestrator()
        enhanced = await orchestrator.run_pipeline(
            file_path=file_path,
            enhance_mode=self._enhance_mode,
            **kwargs,
        )
        output = enhanced.to_parser_output()
        output._enhanced = enhanced
        return output