# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
ParserDispatcher — L0 Routing Layer
====================================

First-principles responsibility: **turn a file path into a ParseResult.**

Everything else (file validation, type detection, cache, security scan) is
a supporting sub-step.  The dispatcher is intentionally thin — it validates,
selects the right adapter, hands off the heavy work, then writes cache.

Processing is divided into 4 sequential stages:

    process(path)
      ├─ 1. _validate()       → FileContext | build_failure
      ├─ 2. _check_cache()    → ParseResult | None  (short-circuit)
      ├─ 3. _execute_parser() → ParseResult          (core computation)
      └─ 4. _write_cache()    → None                 (side effect)

Usage::

    dispatcher = ParserDispatcher()
    result = await dispatcher.process("invoice.pdf")
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Union

import filetype

from docmirror.framework.base import BaseParser
from docmirror.models.entities.parse_result import ParseResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# FileContext — immutable snapshot of everything known about a file
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FileContext:
    """Pure-data snapshot of file metadata, assembled at validate time."""

    path: Path
    file_type: str
    file_size: int
    mime_type: str
    checksum: str  # fast checksum (mtime + size + first-4KB hash)
    is_forged: bool | None = None
    forgery_reasons: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Failure result builder (module-level, no self needed)
# ═══════════════════════════════════════════════════════════════════════════════


def build_failure(
    error_code: str,
    error_msg: str,
    t0: float,
    file_path: str = "",
    file_type: str = "",
    is_forged: bool | None = None,
    forgery_reasons: list[str] | None = None,
) -> ParseResult:
    """Build a failure ParseResult with unified error code."""
    from docmirror.models.errors import build_failure_result

    return build_failure_result(
        code=error_code,
        message=error_msg,
        file_path=file_path,
        file_type=file_type,
        is_forged=is_forged,
        forgery_reasons=forgery_reasons,
        t0=t0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Parser registry (module-level cache — instantiated once, not per-call)
# ═══════════════════════════════════════════════════════════════════════════════

# Logical file_type → (module_path, class_name, static_kwargs).
# Keys are *categories*, not raw extensions — see ``_FILE_EXT_MAP`` and
# ``detect_file_type()`` for suffix / MIME resolution.
#
# Scope: finance / enterprise / legal document scenarios only (120 business
# doc types).  No entertainment or general multimedia formats.
#
# Priority tiers:
#   P0 core   — high-volume business docs; all entries below are live
#   P1 secondary — see _FILE_EXT_MAP tier-2 extensions
#   ofd     → OFDAdapter    — national fixed-layout standard (e-invoice, fiscal receipt)
#   archive → ArchiveAdapter — zip/rar batch uploads; decompress + recursive dispatch
_PARSER_REGISTRY: dict[str, tuple[str, str, dict]] = {
    # ── P0: core adapters ──
    "pdf": ("docmirror.adapters", "PDFAdapter", {}),
    "image": ("docmirror.adapters", "PDFAdapter", {}),
    "word": ("docmirror.adapters", "WordAdapter", {}),
    "excel": ("docmirror.adapters", "ExcelAdapter", {}),
    "ppt": ("docmirror.adapters", "PPTAdapter", {}),
    "email": ("docmirror.adapters", "EmailAdapter", {}),
    "structured": ("docmirror.adapters", "StructuredAdapter", {}),
    "web": ("docmirror.adapters", "WebAdapter", {}),
    "ofd": ("docmirror.adapters", "OFDAdapter", {}),
    "archive": ("docmirror.adapters", "ArchiveAdapter", {}),
}

# Module-level cache: {file_type: class} — avoids per-call importlib
_PARSER_CLASS_CACHE: dict[str, type[BaseParser]] = {}


def get_parser(file_type: str, enhance_mode: str = "standard") -> BaseParser | None:
    """Get a parser instance for the given file type (cached class, fresh instance)."""
    entry = _PARSER_REGISTRY.get(file_type)
    if entry is None:
        return None

    module_path, class_name, static_kwargs = entry
    cls = _PARSER_CLASS_CACHE.get(file_type)
    if cls is None:
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        _PARSER_CLASS_CACHE[file_type] = cls

    # Dynamic kwargs: only PDFAdapter accepts enhance_mode at construction
    kwargs = dict(static_kwargs)
    if file_type in ("pdf", "image"):
        kwargs["enhance_mode"] = enhance_mode
    return cls(**kwargs) if kwargs else cls()


# ═══════════════════════════════════════════════════════════════════════════════
# Forgery detection helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _detect_forgery(path: Path, file_type: str) -> tuple[bool | None, list[str]]:
    """Run forgery detection on the file. Returns (is_forged, reasons)."""
    try:
        if file_type == "pdf":
            from docmirror.core.security.forgery_detector import detect_pdf_forgery

            return detect_pdf_forgery(path)
        elif file_type == "image":
            from docmirror.core.security.forgery_detector import detect_image_forgery

            return detect_image_forgery(path)
    except Exception as e:
        logger.warning(f"[Dispatcher] Forgery detection error: {e}")
    return None, []


# ═══════════════════════════════════════════════════════════════════════════════
# File-type detection (pure function)
# ═══════════════════════════════════════════════════════════════════════════════

# Extension → logical file_type (finance / enterprise / legal scenarios).
# Grouped by implementation priority; mirrors the 120 business-doc catalog.
_FILE_EXT_MAP: dict[str, str] = {
    # ── P0: fixed-layout & scan archives ──
    ".pdf": "pdf",          # PDF/A archives keep .pdf — PDFAdapter compatible
    ".xps": "pdf",          # MS fixed-layout export (banks, gov systems)
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tiff": "image",
    ".tif": "image",        # multi-page scan archives (legacy_scan_doc)
    ".bmp": "image",
    # ── P0: office — Microsoft ──
    ".doc": "word",
    ".docx": "word",
    ".xlsx": "excel",
    ".xls": "excel",
    ".pptx": "ppt",
    ".ppt": "ppt",
    # ── P0: office — WPS (domestic gov / SME) ──
    ".wps": "word",
    ".et": "excel",
    ".dps": "ppt",
    # ── P0: tabular exports (bank statement, regulatory filing) ──
    ".csv": "excel",        # tabular — routed to ExcelAdapter (not Structured)
    # ── P0: email (regulatory correspondence, vouchers) ──
    ".eml": "email",
    ".msg": "email",
    # ── P0: structured interchange (customs, regulatory API dumps) ──
    ".json": "structured",
    ".xml": "structured",
    # ── P0: web exports ──
    ".html": "web",
    ".htm": "web",
    # ── P0 pending: detected but Adapter not yet registered ──
    ".ofd": "ofd",
    ".zip": "archive",
    ".rar": "archive",
    # ── P1 secondary: common export / archive formats ──
    ".txt": "structured",   # SWIFT / plain-text ledgers; TextAdapter later
    ".mhtml": "web",        # saved online-banking pages
    ".rtf": "word",         # legacy rich-text contracts / reports
}

# MIME → file_type overrides (sniffed before extension fallback).
_MIME_TYPE_MAP: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.ms-xpsdocument": "pdf",
    "text/csv": "excel",
    "application/csv": "excel",
    "application/rtf": "word",
    "text/rtf": "word",
    "message/rfc822": "email",
    "application/vnd.ms-outlook": "email",
    "application/zip": "archive",
    "application/x-rar-compressed": "archive",
    "application/x-rar": "archive",
    "application/ofd": "ofd",
    "application/vnd.ofd": "ofd",
}


def detect_file_type(path: Path, known_mime: str = "") -> str:
    """Detect file type using magic bytes, falling back to extension."""
    mime = known_mime
    if not mime:
        try:
            kind = filetype.guess(str(path))
            if kind:
                mime = kind.mime
        except Exception:
            pass

    if mime:
        mapped = _MIME_TYPE_MAP.get(mime)
        if mapped:
            return mapped
        if mime.startswith("image/"):
            return "image"

    return _FILE_EXT_MAP.get(path.suffix.lower(), "unknown")


# ═══════════════════════════════════════════════════════════════════════════════
# Checksum (pure function)
# ═══════════════════════════════════════════════════════════════════════════════


def compute_checksum(path: Path) -> str:
    """Fast content-aware checksum: (size, mtime, first-4KB-md5)."""
    try:
        stat = path.stat()
        with open(path, "rb") as f:
            head = f.read(4096)
        partial = hashlib.md5(head).hexdigest()[:8]
        return f"fast:{stat.st_size}:{int(stat.st_mtime)}:{partial}"
    except OSError:
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# ParserDispatcher
# ═══════════════════════════════════════════════════════════════════════════════


class ParserDispatcher:
    """
    L0 routing layer — one responsibility: turn a file path into a ParseResult.

    The 4-stage process is fully transparent.  Any stage can return a
    failure ParseResult; callers check ``result.status``.
    """

    async def process(
        self,
        file_path: str | Path,
        fallback: bool = True,
        document_type=None,
        skip_cache: bool = False,
        on_progress=None,
        **kwargs,
    ) -> ParseResult:
        """
        Parse a document and return a structured ParseResult.

        Args:
            file_path:  Path to the document file.
            fallback:   Try fallback parser on primary failure.
            document_type: Pre-known type hint.
            skip_cache: Bypass result cache.
            on_progress: Deprecated — use ``perceive_document(…, PerceiveOptions(…))``.

        Returns:
            ParseResult — check ``result.status`` for SUCCESS / FAILURE.
        """
        _t0 = time.time()
        path = Path(file_path)

        # ═══════════════════════════════════════════════════════════════════
        # Stage 1: Validate + detect file type
        # ═══════════════════════════════════════════════════════════════════
        ctx = self._validate(path)
        if ctx is None:
            return build_failure(
                "FILE_NOT_FOUND", f"File not found: {file_path}", _t0, str(path)
            )
        if ctx.file_size == 0:
            return build_failure(
                "FILE_EMPTY", "File is empty (0 bytes)", _t0, str(path)
            )

        # ═══════════════════════════════════════════════════════════════════
        # Stage 2: Cache lookup (short-circuit)
        # ═══════════════════════════════════════════════════════════════════
        if not skip_cache and ctx.checksum:
            cached = await self._check_cache(ctx.checksum, document_type)
            if cached is not None:
                return cached

        # ═══════════════════════════════════════════════════════════════════
        # Stage 3: Execute parser
        # ═══════════════════════════════════════════════════════════════════
        # Read enhance_mode from env (set by perceive_document → _apply_options)
        import os

        enhance_mode = os.environ.get("DOCMIRROR_ENHANCE_MODE", "standard")
        parser = get_parser(ctx.file_type, enhance_mode)
        if parser is None:
            return build_failure(
                "UNSUPPORTED_FORMAT",
                f"Unsupported format: {ctx.file_type}",
                _t0, str(path), file_type=ctx.file_type,
            )

        result = await self._execute_parser(parser, path, ctx, _t0, fallback)

        # ═══════════════════════════════════════════════════════════════════
        # Stage 4: Write cache (if successful)
        # ═══════════════════════════════════════════════════════════════════
        if ctx.checksum and result.success:
            await self._write_cache(ctx.checksum, document_type, result)

        # Timing + logging
        elapsed = int((time.time() - _t0) * 1000)
        result.parser_info.elapsed_ms = elapsed
        logger.info(
            f"[Dispatcher] ◀ process | parser={result.parser_info.parser_name} | "
            f"status={result.status.value} | confidence={result.confidence:.4f} | "
            f"text_len={len(result.full_text)} | tables={result.total_tables} | "
            f"forged={ctx.is_forged} | elapsed={elapsed}ms"
        )
        return result

    # ── Stage 1 internals ──

    def _validate(self, path: Path) -> FileContext | None:
        """Stage 1: validate file exists and assemble FileContext."""
        if not path.exists():
            return None

        file_size = 0
        mime_type = ""
        checksum = ""

        try:
            stat = path.stat()
            file_size = stat.st_size
            ft = filetype.guess(str(path))
            mime_type = ft.mime if ft else ""
            checksum = compute_checksum(path)
        except OSError as exc:
            logger.debug(f"[Dispatcher] File stat failed: {exc}")

        file_type = detect_file_type(path, mime_type)
        is_forged, forgery_reasons = _detect_forgery(path, file_type)

        logger.info(
            f"[Dispatcher] ▶ process | file={path.name} | size={file_size}B | "
            f"file_type={file_type} | mime={mime_type}"
        )

        return FileContext(
            path=path,
            file_type=file_type,
            file_size=file_size,
            mime_type=mime_type,
            checksum=checksum,
            is_forged=is_forged,
            forgery_reasons=forgery_reasons,
        )

    # ── Stage 2 internals ──

    async def _check_cache(
        self, checksum: str, document_type
    ) -> ParseResult | None:
        """Stage 2: check cache. Returns ParseResult on hit, None on miss."""
        try:
            from docmirror.framework.cache import parse_cache

            cached_json = await parse_cache.get(checksum, document_type or "")
            if cached_json:
                result = ParseResult.model_validate_json(cached_json)
                logger.info(f"[Dispatcher] ⚡ Cache HIT ({len(cached_json)} bytes)")
                return result
        except Exception as e:
            logger.debug(f"[Dispatcher] Cache lookup error (non-fatal): {e}")
        return None

    # ── Stage 3 internals ──

    async def _execute_parser(
        self,
        parser: BaseParser,
        path: Path,
        ctx: FileContext,
        t0: float,
        fallback: bool,
    ) -> ParseResult:
        """Stage 3: run primary (and optionally fallback) parser."""
        parser_name = parser.__class__.__name__
        logger.info(f"[Dispatcher] Dispatching to {parser_name}")

        perceive_ctx = {
            "file_type": ctx.file_type,
            "file_size": ctx.file_size,
            "parser_name": parser_name,
            "started_at": datetime.fromtimestamp(t0),
            "mime_type": ctx.mime_type,
            "checksum": ctx.checksum,
            "is_forged": ctx.is_forged,
            "forgery_reasons": ctx.forgery_reasons,
        }

        try:
            result = await parser.perceive(path, **perceive_ctx)

            # Fallback-on-empty strategy
            if fallback and (not result.success or not result.full_text.strip()):
                fb_parser = self._get_fallback_parser(ctx.file_type)
                if fb_parser and fb_parser.__class__ != parser.__class__:
                    fb_name = fb_parser.__class__.__name__
                    logger.info(
                        f"[Dispatcher] Primary {parser_name} failed/empty, "
                        f"attempting fallback: {fb_name}"
                    )
                    perceive_ctx["parser_name"] = fb_name
                    fb_result = await fb_parser.perceive(path, **perceive_ctx)
                    if fb_result.success and fb_result.full_text.strip():
                        return fb_result

            return result

        except Exception as e:
            logger.error(
                f"[Dispatcher] Parser error ({parser_name}): {e}", exc_info=True
            )
            return build_failure(
                "PARSER_ERROR",
                f"{parser_name} failed: {str(e)}",
                t0,
                str(path),
                file_type=ctx.file_type,
                is_forged=ctx.is_forged,
                forgery_reasons=ctx.forgery_reasons,
            )

    # ── Stage 4 internals ──

    async def _write_cache(
        self, checksum: str, document_type, result: ParseResult
    ) -> None:
        """Stage 4: write cache on success."""
        try:
            from docmirror.framework.cache import parse_cache

            await parse_cache.set(
                checksum,
                document_type or "",
                result.model_dump_json(exclude_none=True),
            )
        except Exception as e:
            logger.debug(f"[Dispatcher] Cache write error (non-fatal): {e}")

    # ── Fallback parser (exists only for L0 resilience) ──

    def _get_fallback_parser(self, file_type: str) -> BaseParser | None:
        """
        Fallback parser strategy.

        Current policy: PDF MultiModal pipeline internally cascades fallbacks.
        No L0-level downgrade needed.
        """
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Deprecated alias — keep for backwards compatibility
# ═══════════════════════════════════════════════════════════════════════════════

ParserDispatcher._build_failure = staticmethod(build_failure)
