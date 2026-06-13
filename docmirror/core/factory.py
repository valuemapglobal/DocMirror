# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
MultiModal Perception Factory
==============================

Single public entry point for document parsing.

First-principles design:
    - The entry function's only job is to accept a file path + explicit options,
      then return a fully parsed and classified ParseResult.
    - All configuration is *explicit* via PerceiveOptions, not hidden in
      environment variables or global settings.
    - PerceptionFactory is the Configurable Factory that assembles the
      processing pipeline; perceive_document() is the convenience shortcut.

Usage::

    from docmirror.core.factory import perceive_document, PerceiveOptions

    # Quick mode: first page only
    result = await perceive_document("report.pdf", PerceiveOptions(max_pages=1))

    # Full mode with progress
    async def on_progress(step, total, name, detail):
        print(f"[{step}/{total}] {name}: {detail}")

    result = await perceive_document(
        "report.pdf",
        PerceiveOptions(enhance_mode="full", on_progress=on_progress),
    )
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, Union

from docmirror.framework.dispatcher import ParserDispatcher
from docmirror.models.entities.document_types import DocumentType

if TYPE_CHECKING:
    from docmirror.models.entities.parse_result import ParseResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Explicit Options — replaces implicit env-vars / global config
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class PerceiveOptions:
    """
    Explicit parsing options — every field is visible and controllable.

    All fields are optional; defaults match the current production behaviour.

    Examples::

        # First page only (fast preview)
        PerceiveOptions(max_pages=1)

        # Full enhancement with progress callback
        PerceiveOptions(enhance_mode="full", skip_cache=True)
    """

    # ── Parsing scope ──
    max_pages: int | None = None
    """Limit to first N pages. ``None`` means no limit
    (fallback to env ``DOCMIRROR_MAX_PAGES`` if set)."""

    # ── Enhancement / classification ──
    enhance_mode: Literal["raw", "standard", "full"] = "standard"
    """Processing depth.
    ``raw`` = extraction only (no classification, no entities).
    ``standard`` = +classification (EvidenceEngine) + entity extraction.
    ``full`` = +table structure fix + language detection."""

    # ── Cache ──
    skip_cache: bool = False
    """Bypass the result cache (useful for force-reparse)."""

    # ── Callbacks ──
    on_progress: Callable[[int, int, str, str], None] | None = None
    """Optional progress callback ``f(step, total_steps, step_name, detail)``."""


# ═══════════════════════════════════════════════════════════════════════════════
# PerceptionFactory — assembles and caches the processing pipeline
# ═══════════════════════════════════════════════════════════════════════════════


class PerceptionFactory:
    """
    Configurable parsing factory.

    Maintains a thread-safe singleton of the ParserDispatcher (the orchestrator
    that routes files to the correct adapter and runs the middleware pipeline).

    Use ``perceive_document()`` for the single-call convenience API;
    use ``PerceptionFactory`` directly when you need to customise the
    dispatcher or test with a mock.
    """

    _dispatcher: ParserDispatcher | None = None
    _lock = threading.Lock()

    @classmethod
    def get_dispatcher(cls) -> ParserDispatcher:
        """Get (or create) the singleton dispatcher."""
        if cls._dispatcher is None:
            with cls._lock:
                if cls._dispatcher is None:  # double-check locking
                    cls._dispatcher = ParserDispatcher()
        return cls._dispatcher

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton dispatcher (useful for testing)."""
        with cls._lock:
            cls._dispatcher = None


# ═══════════════════════════════════════════════════════════════════════════════
# Internal: apply explicit options as env-var overrides
# ═══════════════════════════════════════════════════════════════════════════════


def _apply_options(opts: PerceiveOptions) -> dict[str, str]:
    """Apply option values as environment-variable overrides.

    The downstream code (extractor, adapter) reads DOCMIRROR_MAX_PAGES,
    DOCMIRROR_ENHANCE_MODE etc. from ``os.environ``.  Rather than threading
    these values through every internal API, we set them as env-var overrides
    at the entry boundary — this is the **only** place where "user intent"
    meets "environment config".

    Returns a dict of env vars that were *overwritten* so the caller can
    restore them afterwards.
    """
    overrides: dict[str, str] = {}

    if opts.max_pages is not None:
        prev = os.environ.get("DOCMIRROR_MAX_PAGES", "")
        os.environ["DOCMIRROR_MAX_PAGES"] = str(opts.max_pages)
        overrides["DOCMIRROR_MAX_PAGES"] = prev

    if opts.enhance_mode != "standard":
        prev = os.environ.get("DOCMIRROR_ENHANCE_MODE", "")
        os.environ["DOCMIRROR_ENHANCE_MODE"] = opts.enhance_mode
        overrides["DOCMIRROR_ENHANCE_MODE"] = prev

    return overrides


def _restore_env(overrides: dict[str, str]) -> None:
    """Restore env vars to their previous values."""
    for key, prev in overrides.items():
        if prev:
            os.environ[key] = prev
        else:
            os.environ.pop(key, None)


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience entry point
# ═══════════════════════════════════════════════════════════════════════════════


async def perceive_document(
    file_path: str | Path,
    options: PerceiveOptions | None = None,
) -> ParseResult:
    """
    Parse a document and return a fully structured ``ParseResult``.

    This is the **one public function** users call. Everything below
    (dispatcher, adapter, extractor, middlewares) is internal.

    Args:
        file_path: Path to the document (PDF, image, Excel, Word, etc.).
        options:   Explicit parsing options. ``None`` → ``PerceiveOptions()``
                   which uses env-var defaults.

    Returns:
        A ``ParseResult`` with full text, tables, entities, classification,
        and evidence log.

    Examples::

        # Default mode
        result = await perceive_document("invoice.pdf")

        # First page only, no cache
        result = await perceive_document("large.pdf",
            PerceiveOptions(max_pages=1, skip_cache=True))

        # Full pipeline with progress
        result = await perceive_document("report.pdf",
            PerceiveOptions(enhance_mode="full"))
    """
    opts = options or PerceiveOptions()

    logger.info(
        f"[PerceptionFactory] ▶ perceive_document | "
        f"file={file_path} | mode={opts.enhance_mode} | "
        f"max_pages={opts.max_pages or 'unlimited'} | "
        f"skip_cache={opts.skip_cache}"
    )

    # ── Apply explicit options as env-var overrides ──
    restored = _apply_options(opts)

    try:
        dispatcher = PerceptionFactory.get_dispatcher()
        result = await dispatcher.process(
            str(file_path),
            skip_cache=opts.skip_cache,
            on_progress=opts.on_progress,
        )
    finally:
        # Restore env vars even if an exception was raised
        _restore_env(restored)

    return result
