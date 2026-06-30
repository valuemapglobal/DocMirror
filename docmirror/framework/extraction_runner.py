# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Extraction chain runner — transcode gate, primary adapter, optional fallback.

Executes the L0 adapter sequence for a resolved ``FormatCapability``: optional
disk-to-disk transcoding via ``TranscodingGate``, primary ``BaseParser``
extraction, and configured fallback adapters on failure. Invoked by
``ParserDispatcher`` after FCR routing.
"""

from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from docmirror.configs.format.models import FormatCapability
from docmirror.framework.base import BaseParser
from docmirror.input.adapters.transcode.gate import FormatRequiresConverterError, transcode_session
from docmirror.models.entities.parse_result import ParseResult, ResultStatus
from docmirror.models.errors import build_failure_result

logger = logging.getLogger(__name__)

_ADAPTER_CLASS_CACHE: dict[str, type[BaseParser]] = {}


def _load_adapter_class(adapter_ref: str) -> type[BaseParser]:
    if adapter_ref in _ADAPTER_CLASS_CACHE:
        return _ADAPTER_CLASS_CACHE[adapter_ref]
    module_path, _, class_name = adapter_ref.rpartition(".")
    if not module_path:
        raise ValueError(f"Invalid adapter reference: {adapter_ref}")
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    _ADAPTER_CLASS_CACHE[adapter_ref] = cls
    return cls


def instantiate_adapter(
    adapter_ref: str,
    *,
    enhance_mode: str = "standard",
    transport: str = "",
) -> BaseParser:
    cls = _load_adapter_class(adapter_ref)
    if adapter_ref.endswith("PDFAdapter") and transport in ("pdf", "image", ""):
        return cls(enhance_mode=enhance_mode)
    return cls()


def _should_fallback(_cap: FormatCapability, primary: ParseResult, when: str) -> bool:
    if when == "primary_failed":
        return primary.status == ResultStatus.FAILURE
    if when == "primary_empty":
        return not primary.full_text.strip() or primary.status == ResultStatus.FAILURE
    return False


async def run_extraction_chain(
    cap: FormatCapability,
    path: Path,
    context: dict[str, Any],
    *,
    enhance_mode: str = "standard",
    t0: float | None = None,
) -> ParseResult:
    """
    Execute FCR extraction binding: optional transcode → primary → optional fallback.
    """
    binding = cap.binding
    if binding is None or not binding.adapter:
        return build_failure_result(
            "UNSUPPORTED_FORMAT",
            f"No extraction binding for capability: {cap.id}",
            file_path=str(path),
            file_type=cap.transport,
            t0=t0,
        )

    perceive_ctx = dict(context)
    perceive_ctx.setdefault("file_type", cap.transport)
    perceive_ctx.setdefault("content_model", cap.content_model)
    ocr_mode = str(perceive_ctx.get("ocr_mode") or "auto").lower()
    if binding.deserializer:
        perceive_ctx["deserializer"] = binding.deserializer

    # OCR-only shortcut for images (debug / low-resource)
    if (
        cap.transport == "image"
        and ocr_mode != "off"
        and (ocr_mode == "force" or os.environ.get("DOCMIRROR_IMAGE_OCR_ONLY") == "1")
        and binding.fallback
    ):
        fb = instantiate_adapter(binding.fallback.adapter)
        perceive_ctx["parser_name"] = fb.__class__.__name__
        return await fb.perceive(path, **perceive_ctx)

    try:
        async with transcode_session(path, binding.transcode) as work_path:
            primary_cls = _load_adapter_class(binding.adapter)
            primary = instantiate_adapter(
                binding.adapter,
                enhance_mode=enhance_mode,
                transport=cap.transport,
            )
            perceive_ctx["parser_name"] = primary_cls.__name__
            result = await primary.perceive(work_path, **perceive_ctx)

        allow_fallback_ocr = ocr_mode != "off"
        if binding.fallback and allow_fallback_ocr and _should_fallback(cap, result, binding.fallback.when):
            fb = instantiate_adapter(binding.fallback.adapter)
            fb_name = fb.__class__.__name__
            logger.info(
                "[ExtractionRunner] Primary %s empty/failed, fallback %s",
                primary_cls.__name__,
                fb_name,
            )
            perceive_ctx["parser_name"] = fb_name
            fb_result = await fb.perceive(path, **perceive_ctx)
            if fb_result.full_text.strip() and fb_result.status != ResultStatus.FAILURE:
                return fb_result

        return result

    except FormatRequiresConverterError as exc:
        return build_failure_result(
            exc.code,
            str(exc),
            file_path=str(path),
            file_type=cap.transport,
            t0=t0,
        )


def build_perceive_context(
    _path: Path,
    cap: FormatCapability,
    *,
    file_size: int = 0,
    mime_type: str = "",
    checksum: str = "",
    is_forged: bool | None = None,
    forgery_reasons: list[str] | None = None,
    t0: float | None = None,
) -> dict[str, Any]:
    return {
        "file_type": cap.transport,
        "content_model": cap.content_model,
        "capability_id": cap.id,
        "file_size": file_size,
        "mime_type": mime_type,
        "checksum": checksum,
        "is_forged": is_forged,
        "forgery_reasons": forgery_reasons or [],
        "started_at": datetime.fromtimestamp(t0) if t0 else datetime.now(),
    }
