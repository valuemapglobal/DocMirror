# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
PDF Adapter — PDF → ParseResult (Registry-Enabled)
===================================================

Extracts PDF content via the best available parser backend (from the
``ParserRegistry``), maps backend facts into ``ParseResult``, then delegates to
``BaseParser.perceive()`` for middleware enrichment.

Falls back to ``CoreExtractor`` when no backend is registered.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from docmirror.framework.base import BaseParser

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PDFAdapter(BaseParser):
    """
    PDF format adapter with pluggable parser backend support.

    Uses the ``ParserRegistry`` to select the best available backend for PDF
    parsing. Falls back to ``CoreExtractor`` for parser contract stability when
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
        parse_policy = kwargs.get("parse_policy")
        backend_preference = kwargs.get("parser_backend")

        # Step 0: Resolve registry (lazy, may be empty)
        registry = _get_registry()
        if registry is None:
            backend = None
        else:
            backend = _select_backend(registry, backend_preference)

        workers = kwargs.get("max_workers")

        pr = None
        if backend is not None:
            try:
                raw_result = await backend.parse(file_path)
                page_layouts, metadata, raw_text = _raw_backend_to_physical_facts(raw_result)
                from docmirror.input.canonical import assemble_parse_result

                pr = assemble_parse_result(page_layouts, metadata, raw_text)
                logger.info("[PDFAdapter] Backend %r completed: %s", backend.name, file_path)
            except Exception as exc:
                logger.warning("Backend %r failed (%s); falling back to CoreExtractor", backend.name, exc)

        if pr is None:
            # Step 2: Fall back to CoreExtractor
            extractor = CoreExtractor(max_page_concurrency=workers)
            pr = await extractor.extract_parse_result(
                file_path,
                options={
                    "max_pages": kwargs.get("max_pages"),
                    "enhance_mode": kwargs.get("enhance_mode"),
                    "parse_policy": parse_policy,
                    "parse_policy_dict": kwargs.get("parse_policy_dict"),
                    "parse_policy_fingerprint": kwargs.get("parse_policy_fingerprint"),
                    "doc_type_hint": kwargs.get("doc_type_hint"),
                    "doc_type_hint_strength": kwargs.get("doc_type_hint_strength"),
                    "on_progress": kwargs.get("on_progress"),
                },
            )
        logger.info(f"[PDFAdapter] Completed extraction for: {file_path}")

        # PDF-specific parser_info
        pr.parser_info.parser_name = pr.parser_info.parser_name or "DocMirror"
        pr.parser_info.table_engine = pr.parser_info.table_engine or "pymupdf_native"
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


# Adapter fact mapping: RawParseResult -> physical facts --------------


def _raw_backend_to_physical_facts(raw):
    """Convert a backend payload into evidence/basic physical facts.

    The canonical assembler remains the only component that creates the
    ``ParseResult`` SSOT.
    """
    from docmirror.models.entities.physical import Block, PageLayout, Style, TextSpan

    pages = []
    for raw_page in raw.pages:
        blocks = []
        for text_index, item in enumerate(raw_page.texts):
            bbox = tuple(float(value) for value in (item.bbox or [0.0, 0.0, 0.0, 0.0]))
            level = _infer_heading_level(item)
            blocks.append(
                Block(
                    block_id=f"backend:p{raw_page.page_number}:text:{text_index}",
                    block_type="title" if level == 1 else "text",
                    spans=(
                        TextSpan(
                            text=item.content,
                            bbox=bbox,
                            style=Style(font_name=item.font_name or "", font_size=float(item.font_size or 0.0)),
                        ),
                    ),
                    bbox=bbox,
                    reading_order=int(item.reading_order or text_index),
                    page=raw_page.page_number,
                    raw_content=item.content,
                    attrs={"confidence": float(item.confidence)},
                    heading_level=level,
                )
            )
        for table_index, table in enumerate(raw_page.tables):
            raw_rows = [list(table.headers), *[list(row) for row in table.data_rows]]
            bbox = tuple(float(value) for value in (table.bbox or [0.0, 0.0, 0.0, 0.0]))
            blocks.append(
                Block(
                    block_id=table.table_id or f"backend:p{raw_page.page_number}:table:{table_index}",
                    block_type="table",
                    bbox=bbox,
                    reading_order=int(table.reading_order or len(blocks)),
                    page=raw_page.page_number,
                    raw_content=raw_rows,
                    attrs={
                        "extraction_layer": str(table.method or "backend"),
                        "extraction_confidence": float(table.confidence),
                        "preserve_headers": bool(table.headers),
                    },
                )
            )
        for kv_index, item in enumerate(raw_page.key_values):
            bbox = tuple(float(value) for value in (item.bbox or [0.0, 0.0, 0.0, 0.0]))
            blocks.append(
                Block(
                    block_id=f"backend:p{raw_page.page_number}:kv:{kv_index}",
                    block_type="key_value",
                    bbox=bbox,
                    reading_order=int(item.reading_order or len(blocks)),
                    page=raw_page.page_number,
                    raw_content={str(item.key): str(item.value)},
                    attrs={"confidence": float(item.confidence)},
                )
            )
        pages.append(
            PageLayout(
                page_number=raw_page.page_number,
                width=float(raw_page.width_pt or 0.0),
                height=float(raw_page.height_pt or 0.0),
                blocks=tuple(sorted(blocks, key=lambda block: block.reading_order)),
            )
        )

    backend_name = raw.metadata.get("backend", "unknown") if raw.metadata else "unknown"
    full_text = "\n".join(item.content for page in raw.pages for item in page.texts)
    metadata = {
        **dict(raw.metadata or {}),
        "parser": f"DocMirror/{backend_name}",
        "table_engine": backend_name,
        "extraction_method": "digital",
        "overall_confidence": float(raw.confidence or 1.0),
    }
    return tuple(pages), metadata, full_text


def _infer_heading_level(raw_text):
    """Infer canonical heading level from backend font-size hints.

    - >= 20pt -> TITLE
    - >= 14pt -> H1
    - >= 12pt -> H2
    - >= 10pt -> H3
    - otherwise -> BODY
    """
    font_size = getattr(raw_text, "font_size", None)
    if font_size is not None:
        if font_size >= 20:
            return 1
        if font_size >= 14:
            return 1
        if font_size >= 12:
            return 2
        if font_size >= 10:
            return 3
    return None
