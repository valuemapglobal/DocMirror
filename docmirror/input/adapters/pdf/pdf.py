# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
PDF Adapter — PDF → ParseResult (Registry-Enabled)
===================================================

Extracts PDF content via the best available parser backend (from the
``ParserRegistry``), bridges to ``ParseResult``, then delegates to
``BaseParser.perceive()`` for middleware enrichment.

Falls back to ``CoreExtractor`` when no backend is registered.
"""

from __future__ import annotations

import logging
from pathlib import Path

from typing import TYPE_CHECKING

from docmirror.framework.base import BaseParser

if TYPE_CHECKING:
    from docmirror.input.adapters.parsers import ParserRegistry

logger = logging.getLogger(__name__)


class PDFAdapter(BaseParser):
    """
    PDF format adapter with pluggable parser backend support.

    Uses the ``ParserRegistry`` to select the best available backend for PDF
    parsing. Falls back to ``CoreExtractor`` for backward compatibility when
    no backend is registered. Then relies on ``BaseParser.perceive()`` for
    the shared Orchestrator middleware pipeline.

    Args:
        enhance_mode: Enhancement level. One of "raw", "standard", or "full".
    """

    def __init__(self, enhance_mode: str = "standard", **_kwargs):
        self._enhance_mode = enhance_mode

    async def to_parse_result(self, file_path: Path, **kwargs) -> ParseResult:
        """
        Extract a PDF into a ParseResult using the best available backend.

        Pipeline:
          1. Try the registry: if a non-default backend is registered or
             the caller specifies ``parser_backend`` in kwargs, use it.
          2. Fall back: ``CoreExtractor.extract_parse_result()`` (original).
          3. Always fills parser_info and provenance.
        """
        from docmirror.input.extraction.extractor import CoreExtractor

        logger.info(f"[PDFAdapter] Starting extraction for: {file_path}")
        parse_control = kwargs.get("parse_control")
        backend_preference = kwargs.get("parser_backend")

        # Step 0: Resolve registry (lazy, may be empty)
        registry = _get_registry()
        if registry is None:
            backend = None
        else:
            backend = _select_backend(registry, backend_preference)

        workers = None
        if parse_control is not None:
            workers = getattr(getattr(parse_control, "resource", None), "workers", None)
            if workers == "auto":
                workers = None

        if backend is not None:
            try:
                raw_result = await backend.parse(file_path)
                pr = _raw_to_parse_result(raw_result, file_path, kwargs)
                logger.info("[PDFAdapter] Backend %r completed: %s", backend.name, file_path)
                return pr
            except Exception as exc:
                logger.warning("Backend %r failed (%s); falling back to CoreExtractor", backend.name, exc)

        # Step 2: Fall back to CoreExtractor
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
                "on_progress": kwargs.get("on_progress"),
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

    async def perceive(self, file_path: Path, **context) -> ParseResult:
        """
        Full pipeline: PDF → middleware → ParseResult.

        Injects the adapter's enhance_mode before delegating to base class.
        """
        context.setdefault("enhance_mode", self._enhance_mode)
        context.setdefault("file_type", "pdf")
        return await super().perceive(file_path, **context)


# ── Registry helpers (lazy, single-pay import) ────────────────────────────


def _get_registry():
    """Return the global ParserRegistry, or None if the module is unavailable.

    The import is deferred to avoid paying the ~1 s startup cost inside
    ``to_parse_result`` every time.  Once imported, the result is cached
    in a module-level variable so subsequent calls are instant.
    """
    if _registry_singleton is not None:
        return _registry_singleton
    try:
        from docmirror.input.adapters.parsers import get_registry

        reg = get_registry()
    except ImportError:
        reg = None
    globals()["_registry_singleton"] = reg
    return reg


def _select_backend(registry, preference):
    """Select a non-default parser backend, or None to fall through."""
    if registry.count == 0:
        return None
    if preference:
        try:
            return registry.select("pdf", preference=preference)
        except ValueError:
            logger.warning(
                "Requested parser backend %r not found for pdf; falling back",
                preference,
            )
            return None
    for b in registry.list_for_format("pdf"):
        if b.name != "pymupdf":
            return b
    return None


_registry_singleton = None  # populated by first call to _get_registry()


# Bridge: RawParseResult -> ParseResult -------------------------------


def _raw_to_parse_result(raw, file_path, kwargs):
    """Convert a RawParseResult from any ParserBackend into a ParseResult.

    This bridge enables PDFAdapter to consume output from any registered
    parser backend (PyMuPDFBackend, OpenDataLoaderBridge, etc.) and produce
    a valid ParseResult that the Orchestrator middleware can enrich.

    The mapping is intentionally basic but lossless for supported fields.
    Missing fields (entities, evidence, quality reports) are filled by the
    middleware pipeline in BaseParser.perceive().
    """
    from docmirror.models.entities.parse_result import (
        CellValue,
        DataType,
        KeyValuePair,
        PageContent,
        ParseResult,
        ParserInfo,
        ProvenanceInfo,
        ResultStatus,
        RowType,
        TableBlock,
        TableRow,
        TextBlock,
        TextLevel,
    )

    pages = []
    for raw_page in raw.pages:
        texts = [
            TextBlock(
                content=t.content,
                level=_infer_text_level(t),
                confidence=t.confidence,
                bbox=t.bbox if t.bbox is not None else None,
            )
            for t in raw_page.texts
        ]

        tables = []
        for rt in raw_page.tables:
            rows = []
            if rt.headers:
                rows.append(TableRow(
                    cells=[CellValue(text=h, data_type=DataType.TEXT) for h in rt.headers],
                    row_type=RowType.HEADER,
                ))
            for row_data in rt.data_rows:
                rows.append(TableRow(
                    cells=[CellValue(text=c, data_type=DataType.TEXT) for c in row_data],
                    row_type=RowType.DATA,
                    confidence=rt.confidence,
                ))
            tables.append(TableBlock(
                table_id=rt.table_id,
                headers=rt.headers,
                rows=rows,
                bbox=rt.bbox,
                confidence=rt.confidence,
            ))

        kvs = [
            KeyValuePair(key=kv.key, value=kv.value, confidence=kv.confidence, bbox=kv.bbox)
            for kv in raw_page.key_values
        ]

        pages.append(PageContent(
            page_number=raw_page.page_number,
            width=int(raw_page.width_pt) if raw_page.width_pt else None,
            height=int(raw_page.height_pt) if raw_page.height_pt else None,
            texts=texts,
            tables=tables,
            key_values=kvs,
            page_confidence=raw_page.confidence if raw_page.confidence else 1.0,
        ))

    full_text = "\n".join(t.content for p in pages for t in p.texts)

    provenance = None
    try:
        stat = file_path.stat()
        provenance = ProvenanceInfo(
            file_type=kwargs.get("file_type") or "pdf",
            file_size=int(kwargs.get("file_size") or stat.st_size),
            checksum=kwargs.get("checksum", ""),
            mime_type=kwargs.get("mime_type", ""),
            capability_id=kwargs.get("capability_id", ""),
            content_model=kwargs.get("content_model", ""),
        )
    except OSError:
        pass

    backend_name = raw.metadata.get("backend", "unknown") if raw.metadata else "unknown"
    parser_info = ParserInfo(
        parser_name="DocMirror/{}".format(backend_name),
        table_engine=backend_name,
        page_count=len(pages),
    )

    return ParseResult(
        pages=pages,
        full_text=full_text,
        status=ResultStatus.SUCCESS,
        confidence=raw.confidence if raw.confidence else 1.0,
        trust_score=raw.confidence if raw.confidence else 1.0,
        parser_info=parser_info,
        provenance=provenance,
    )


def _infer_text_level(raw_text):
    """Infer TextLevel from a RawText object using font size heuristics.

    - >= 20pt -> TITLE
    - >= 14pt -> H1
    - >= 12pt -> H2
    - >= 10pt -> H3
    - otherwise -> BODY
    """
    font_size = getattr(raw_text, "font_size", None)
    if font_size is not None:
        if font_size >= 20:
            return TextLevel.TITLE
        if font_size >= 14:
            return TextLevel.H1
        if font_size >= 12:
            return TextLevel.H2
        if font_size >= 10:
            return TextLevel.H3
    return TextLevel.BODY
