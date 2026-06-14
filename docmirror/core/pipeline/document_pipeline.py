# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Document-level pipeline orchestration (CPA design 12)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from docmirror.core.pipeline.document_profile import bind_extraction_profile, compose_logical_tables

if TYPE_CHECKING:
    from docmirror.core.extraction.extractor import CoreExtractor
    from docmirror.models.entities.domain import BaseResult

logger = logging.getLogger(__name__)


class DocumentPipeline:
    """Document open → profile bind → sync extraction → close (EPO entity)."""

    def __init__(self, extractor: CoreExtractor) -> None:
        self._extractor = extractor

    def bind_profile(
        self,
        *,
        full_text_raw: str,
        num_pages: int,
        pre_analysis: Any,
        title_text: str | None = None,
    ) -> Any:
        """Early-bind extraction profile (Step 0)."""
        return bind_extraction_profile(
            self._extractor,
            full_text_raw=full_text_raw,
            num_pages=num_pages,
            pre_analysis=pre_analysis,
            title_text=title_text,
        )

    def compose_logical_tables(
        self,
        pages: list,
        *,
        full_text: str,
        pre_analysis: Any,
    ) -> tuple[list | None, bool, list]:
        """Non-destructive logical table composition (Step 4.5)."""
        return compose_logical_tables(
            self._extractor,
            pages,
            full_text=full_text,
            pre_analysis=pre_analysis,
        )

    async def run(self, file_path: Path, *, doc_id: str) -> BaseResult:
        fitz_doc = None
        try:
            fitz_doc = await self._extractor._open_document(file_path)
            return await self._extractor._run_extraction(fitz_doc, file_path, doc_id)
        finally:
            try:
                if fitz_doc:
                    fitz_doc.close()
            except Exception as exc:
                logger.debug(f"DocumentPipeline: suppressed close error: {exc}")


__all__ = ["DocumentPipeline"]
