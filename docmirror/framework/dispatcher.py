# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
ParserDispatcher — L0 Routing Layer (FCR-driven)
=================================================

Routes an already accepted source into the canonical extraction pipeline.

Validation, MIME detection, checksum calculation, forgery checks, and FCR
resolution are deliberately owned by InputAcceptance and never repeated here.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from docmirror.configs.format.models import UNKNOWN_CAPABILITY, FormatCapability
from docmirror.framework.extraction_runner import (
    build_perceive_context,
    run_extraction_chain,
)
from docmirror.input.canonical.seal import seal_canonical_result
from docmirror.input.entry.options import ParsePolicy
from docmirror.input.models import AcceptedSource
from docmirror.input.pipeline.context import ParseContext
from docmirror.models.entities.parse_result import ParseResult
from docmirror.models.sealed import SealedParseResult, seal_parse_result

logger = logging.getLogger(__name__)


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
    """L0 routing from immutable ``AcceptedSource`` to ``ParseResult``."""

    async def process(
        self,
        source: AcceptedSource,
        policy: ParsePolicy | None = None,
        *,
        max_workers: int | None = None,
        on_progress: Callable[[str, float, str], None] | None = None,
    ) -> SealedParseResult:
        if not isinstance(source, AcceptedSource):
            raise TypeError("ParserDispatcher.process accepts AcceptedSource only")
        _t0 = time.time()
        path = source.path
        display_path = source.display_path
        cap = source.capability
        if not source.verify_content_identity():
            return seal_parse_result(
                build_failure(
                    "INPUT_IDENTITY_MISMATCH",
                    "Accepted source bytes no longer match the intake checksum",
                    _t0,
                    str(display_path),
                    file_type=cap.transport,
                )
            )
        if cap.status != "supported":
            return seal_parse_result(_capability_failure(cap, display_path, _t0))

        policy = policy or ParsePolicy()
        enhance_mode = policy.enhance_mode
        max_pages = policy.pages.max_pages
        document_type = policy.doc_type_hint.value if policy.doc_type_hint else None
        if policy.pages.ranges and cap.transport not in {"pdf", "image"}:
            return seal_parse_result(
                build_failure(
                    "INVALID_OPTIONS",
                    f"--pages is only supported for paged PDF/image inputs, not transport={cap.transport}",
                    _t0,
                    str(display_path),
                    file_type=cap.transport,
                    is_forged=source.is_forged,
                    forgery_reasons=list(source.forgery_reasons),
                )
            )
        perceive_ctx = build_perceive_context(
            path,
            cap,
            file_size=source.size_bytes,
            mime_type=source.detected_mime,
            checksum=source.sha256,
            is_forged=source.is_forged,
            forgery_reasons=list(source.forgery_reasons),
            t0=_t0,
        )
        parse_context = ParseContext(
            file_path=path,
            file_type=cap.transport,
            content_model=cap.content_model,
            capability_id=cap.id,
            file_size=source.size_bytes,
            mime_type=source.detected_mime,
            checksum=source.sha256,
            is_forged=source.is_forged,
            forgery_reasons=source.forgery_reasons,
            enhance_mode=enhance_mode,
            max_pages=max_pages,
            started_at=perceive_ctx.get("started_at"),
            options={
                "document_type": document_type,
                "parse_policy": policy.to_dict(),
                "parse_policy_fingerprint": policy.fingerprint(),
                "selected_pages": policy.pages.to_display(),
                "doc_type_hint": policy.doc_type_hint.value if policy.doc_type_hint else None,
                "doc_type_hint_strength": policy.doc_type_hint.strength if policy.doc_type_hint else None,
            },
        )
        perceive_ctx.update(parse_context.to_perceive_context())
        perceive_ctx["enhance_mode"] = enhance_mode
        perceive_ctx["parse_policy"] = policy
        perceive_ctx["parse_policy_dict"] = policy.to_dict()
        perceive_ctx["parse_policy_fingerprint"] = policy.fingerprint()
        perceive_ctx["max_workers"] = max_workers
        perceive_ctx["ocr_mode"] = policy.ocr
        perceive_ctx["doc_type_hint"] = policy.doc_type_hint.value if policy.doc_type_hint else None
        perceive_ctx["doc_type_hint_strength"] = policy.doc_type_hint.strength if policy.doc_type_hint else None
        perceive_ctx["document_type"] = document_type
        perceive_ctx["on_progress"] = on_progress

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
            return seal_parse_result(
                build_failure(
                    "PARSER_ERROR",
                    str(exc),
                    _t0,
                    str(display_path),
                    file_type=cap.transport,
                    is_forged=source.is_forged,
                    forgery_reasons=list(source.forgery_reasons),
                )
            )

        if not source.verify_content_identity():
            return seal_parse_result(
                build_failure(
                    "INPUT_IDENTITY_MISMATCH",
                    "Accepted source bytes changed during adapter processing",
                    _t0,
                    str(display_path),
                    file_type=cap.transport,
                )
            )

        elapsed = int((time.time() - _t0) * 1000)
        result.parser_info.elapsed_ms = elapsed
        if result.provenance is not None:
            result.provenance.file_path = str(display_path)

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
        return seal_canonical_result(result)


ParserDispatcher._build_failure = staticmethod(build_failure)
