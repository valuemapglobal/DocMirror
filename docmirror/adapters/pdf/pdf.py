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

        Pipeline: CoreExtractor.extract_parse_result() (single bridge point).
        """
        from docmirror.core.extraction.extractor import CoreExtractor

        logger.info(f"[PDFAdapter] Starting extraction for: {file_path}")
        parse_control = kwargs.get("parse_control")
        workers = None
        if parse_control is not None:
            workers = getattr(getattr(parse_control, "resource", None), "workers", None)
            if workers == "auto":
                workers = None
        extractor = CoreExtractor(max_page_concurrency=workers)
        pr = await extractor.extract_parse_result(
            file_path,
            options={
                "max_pages": kwargs.get("max_pages"),
                "enhance_mode": kwargs.get("enhance_mode"),
                "parse_control": parse_control,
                "parse_control_dict": kwargs.get("parse_control_dict"),
                "parse_control_fingerprint": kwargs.get("parse_control_fingerprint"),
                "doc_type_hint": kwargs.get("doc_type_hint"),
                "doc_type_hint_strength": kwargs.get("doc_type_hint_strength"),
            },
        )
        logger.info(f"[PDFAdapter] Completed extraction for: {file_path}")

        # PDF-specific parser_info
        pr.parser_info.parser_name = "DocMirror"
        pr.parser_info.table_engine = "pymupdf_native"
        pr.parser_info.page_count = len(pr.pages)

        # ── Fill provenance (lightweight, no re-read of full file) ──
        if pr.provenance is None:
            from docmirror.models.entities.parse_result import ProvenanceInfo

            try:
                stat = file_path.stat()
                pr.provenance = ProvenanceInfo(
                    file_type=kwargs.get("file_type") or "pdf",
                    file_size=int(kwargs.get("file_size") or stat.st_size),
                    checksum=kwargs.get("checksum", ""),
                    mime_type=kwargs.get("mime_type", ""),
                    capability_id=kwargs.get("capability_id", ""),
                    content_model=kwargs.get("content_model", ""),
                )
            except OSError:
                pass
        else:
            pr.provenance.file_type = pr.provenance.file_type or kwargs.get("file_type") or "pdf"
            if not pr.provenance.file_size and kwargs.get("file_size"):
                pr.provenance.file_size = int(kwargs.get("file_size") or 0)
            pr.provenance.checksum = pr.provenance.checksum or kwargs.get("checksum", "")
            pr.provenance.mime_type = pr.provenance.mime_type or kwargs.get("mime_type", "")
            pr.provenance.capability_id = pr.provenance.capability_id or kwargs.get("capability_id", "")
            pr.provenance.content_model = pr.provenance.content_model or kwargs.get("content_model", "")

        return pr

    async def perceive(self, file_path: Path, **context) -> "ParseResult":
        """
        Full pipeline: PDF → middleware → ParseResult.

        Injects the adapter's enhance_mode before delegating to base class.
        """
        context.setdefault("enhance_mode", self._enhance_mode)
        context.setdefault("file_type", "pdf")
        return await super().perceive(file_path, **context)
