# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
ParserDispatcher — L0 Routing Layer (FCR-driven)
=================================================

Turns a file path into a ParseResult via Format Capability Registry (FCR).

    process(path)
      ├─ 1. _validate()              → FileContext
      ├─ 2. resolve_capability()   → FormatCapability
      └─ 3. run_extraction_chain() → ParseResult
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import filetype

from docmirror.configs.format.models import FormatCapability, UNKNOWN_CAPABILITY
from docmirror.configs.format.resolver import detect_transport, get_capability_by_transport, resolve_capability
from docmirror.framework.base import BaseParser
from docmirror.framework.extraction_runner import (
    build_perceive_context,
    instantiate_adapter,
    run_extraction_chain,
)
from docmirror.models.entities.parse_result import ParseResult
from docmirror.core.pipeline.context import ParseContext
from docmirror.core.entry.options import ParseControl, normalize_parse_control

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileContext:
    """Pure-data snapshot of file metadata, assembled at validate time."""

    path: Path
    file_type: str
    content_model: str
    capability_id: str
    capability_status: str
    file_size: int
    mime_type: str
    checksum: str
    is_forged: bool | None = None
    forgery_reasons: list[str] = field(default_factory=list)


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


def get_parser(file_type: str, enhance_mode: str = "standard") -> BaseParser | None:
    """Thin wrapper for Archive child dispatch and tests."""
    cap = get_capability_by_transport(file_type)
    if cap is None or cap.binding is None or not cap.binding.adapter:
        return None
    return instantiate_adapter(
        cap.binding.adapter,
        enhance_mode=enhance_mode,
        transport=file_type,
    )


def detect_file_type(path: Path, known_mime: str = "") -> str:
    """Backward-compatible alias — returns transport string."""
    return detect_transport(path, known_mime)


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


def _detect_forgery(path: Path, file_type: str) -> tuple[bool | None, list[str]]:
    try:
        if file_type == "pdf":
            from docmirror.framework.security.forgery_detector import detect_pdf_forgery

            return detect_pdf_forgery(path)
        if file_type == "image":
            from docmirror.framework.security.forgery_detector import detect_image_forgery

            return detect_image_forgery(path)
    except Exception as exc:
        logger.warning("[Dispatcher] Forgery detection error: %s", exc)
    return None, []


def _capability_failure(cap: FormatCapability, path: Path, t0: float) -> ParseResult:
    if cap.status == "planned":
        return build_failure(
            "UNSUPPORTED_FORMAT",
            f"Format '{path.suffix}' is recognized but not yet supported (capability: {cap.id})",
            t0,
            str(path),
            file_type=cap.transport,
        )
    if cap.id == UNKNOWN_CAPABILITY.id:
        return build_failure(
            "UNSUPPORTED_FORMAT",
            f"Unsupported format: {path.suffix or 'unknown'}",
            t0,
            str(path),
            file_type="unknown",
        )
    return build_failure(
        "UNSUPPORTED_FORMAT",
        f"Format not supported: {path.suffix} (capability: {cap.id})",
        t0,
        str(path),
        file_type=cap.transport,
    )


class ParserDispatcher:
    """L0 routing — FCR resolve + extraction chain."""

    async def process(
        self,
        file_path: str | Path,
        fallback: bool = True,
        document_type=None,
        skip_cache: bool = False,
        on_progress=None,
        **kwargs,
    ) -> ParseResult:
        _t0 = time.time()
        path = Path(file_path)

        ctx = self._validate(path)
        if ctx is None:
            return build_failure("FILE_NOT_FOUND", f"File not found: {file_path}", _t0, str(path))
        if ctx.file_size == 0:
            return build_failure("FILE_EMPTY", "File is empty (0 bytes)", _t0, str(path))

        cap = resolve_capability(path, ctx.mime_type)
        if cap.status != "supported":
            return _capability_failure(cap, path, _t0)

        raw_control = kwargs.get("parse_control")
        parse_control = normalize_parse_control(
            raw_control if isinstance(raw_control, ParseControl) else None,
            max_pages=kwargs.get("max_pages"),
            skip_cache=skip_cache,
            enhance_mode=kwargs.get("enhance_mode") or os.environ.get("DOCMIRROR_ENHANCE_MODE", "standard"),
        )
        enhance_mode = parse_control.enhance_mode
        max_pages = parse_control.pages.max_pages
        if parse_control.doc_type_hint and document_type is None:
            document_type = parse_control.doc_type_hint.value
        if parse_control.pages.ranges and cap.transport not in {"pdf", "image"}:
            return build_failure(
                "INVALID_OPTIONS",
                f"--pages is only supported for paged PDF/image inputs, not transport={cap.transport}",
                _t0,
                str(path),
                file_type=cap.transport,
                is_forged=ctx.is_forged,
                forgery_reasons=ctx.forgery_reasons,
            )
        perceive_ctx = build_perceive_context(
            path,
            cap,
            file_size=ctx.file_size,
            mime_type=ctx.mime_type,
            checksum=ctx.checksum,
            is_forged=ctx.is_forged,
            forgery_reasons=ctx.forgery_reasons,
            t0=_t0,
        )
        parse_context = ParseContext(
            file_path=path,
            file_type=cap.transport,
            content_model=cap.content_model,
            capability_id=cap.id,
            file_size=ctx.file_size,
            mime_type=ctx.mime_type,
            checksum=ctx.checksum,
            is_forged=ctx.is_forged,
            forgery_reasons=tuple(ctx.forgery_reasons),
            enhance_mode=enhance_mode,
            max_pages=max_pages,
            started_at=perceive_ctx.get("started_at"),
            options={
                "skip_cache": skip_cache,
                "fallback": fallback,
                "document_type": document_type,
                "parse_control": parse_control.to_dict(),
                "parse_control_fingerprint": parse_control.fingerprint(),
                "selected_pages": parse_control.pages.to_display(),
                "doc_type_hint": parse_control.doc_type_hint.value if parse_control.doc_type_hint else None,
                "doc_type_hint_strength": parse_control.doc_type_hint.strength if parse_control.doc_type_hint else None,
            },
        )
        perceive_ctx.update(parse_context.to_perceive_context())
        perceive_ctx["enhance_mode"] = enhance_mode
        perceive_ctx["parse_control"] = parse_control
        perceive_ctx["parse_control_dict"] = parse_control.to_dict()
        perceive_ctx["parse_control_fingerprint"] = parse_control.fingerprint()
        perceive_ctx["doc_type_hint"] = parse_control.doc_type_hint.value if parse_control.doc_type_hint else None
        perceive_ctx["doc_type_hint_strength"] = parse_control.doc_type_hint.strength if parse_control.doc_type_hint else None

        # ── Cache Lookup ──
        use_cache = not parse_control.skip_cache
        fingerprint = parse_control.fingerprint()
        if use_cache:
            from docmirror.framework.cache import parse_cache
            try:
                cached_json = await parse_cache.get(ctx.checksum, fingerprint)
                if cached_json:
                    result = ParseResult.model_validate_json(cached_json)
                    logger.info("[Dispatcher] Cache HIT for checksum=%s, fingerprint=%s", ctx.checksum, fingerprint)
                    return result
            except Exception as e:
                logger.warning("[Dispatcher] Failed to load cached result: %s", e)

        try:
            result = await run_extraction_chain(
                cap,
                path,
                perceive_ctx,
                enhance_mode=enhance_mode,
                t0=_t0,
            )
        except Exception as exc:
            logger.error("[Dispatcher] Extraction chain error: %s", exc, exc_info=True)
            return build_failure(
                "PARSER_ERROR",
                str(exc),
                _t0,
                str(path),
                file_type=cap.transport,
                is_forged=ctx.is_forged,
                forgery_reasons=ctx.forgery_reasons,
            )

        elapsed = int((time.time() - _t0) * 1000)
        result.parser_info.elapsed_ms = elapsed

        # ── Cache Write ──
        if use_cache and result.success:
            from docmirror.framework.cache import parse_cache
            try:
                serialized = result.model_dump_json()
                await parse_cache.set(ctx.checksum, fingerprint, serialized)
            except Exception as e:
                logger.warning("[Dispatcher] Failed to cache result: %s", e)

        logger.info(
            "[Dispatcher] ◀ process | parser=%s | transport=%s | content_model=%s | "
            "status=%s | text_len=%d | tables=%d | elapsed=%dms",
            result.parser_info.parser_name,
            cap.transport,
            cap.content_model,
            result.status.value,
            len(result.full_text),
            result.total_tables,
            elapsed,
        )
        return result

    def _validate(self, path: Path) -> FileContext | None:
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
            logger.debug("[Dispatcher] File stat failed: %s", exc)

        cap = resolve_capability(path, mime_type)
        is_forged, forgery_reasons = _detect_forgery(path, cap.transport)

        logger.info(
            "[Dispatcher] ▶ process | file=%s | transport=%s | cap=%s | status=%s | mime=%s",
            path.name,
            cap.transport,
            cap.id,
            cap.status,
            mime_type,
        )

        return FileContext(
            path=path,
            file_type=cap.transport,
            content_model=cap.content_model,
            capability_id=cap.id,
            capability_status=cap.status,
            file_size=file_size,
            mime_type=mime_type,
            checksum=checksum,
            is_forged=is_forged,
            forgery_reasons=forgery_reasons,
        )


ParserDispatcher._build_failure = staticmethod(build_failure)
