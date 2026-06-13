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
    - PerceptionFactory delegates to ``docmirror.di`` for shared singletons;
      perceive_document() is the convenience shortcut.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, Union

from docmirror.core.perceive_result import PerceiveResult
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
    """No-op (parse cache removed from the default pipeline). Kept for API compat."""

    # ── Callbacks ──
    on_progress: Callable[[int, int, str, str], None] | None = None
    """Optional progress callback ``f(step, total_steps, step_name, detail)``."""

    # ── Plugin layer (PEC) — optional; does not mutate Mirror ──
    editions: list[str] = field(default_factory=list)
    """If non-empty, run ``plugins.runner`` for each edition after parse.

    Results are stored on ``PerceiveResult.editions`` (never on ``ParseResult``).
    """


# ═══════════════════════════════════════════════════════════════════════════════
# PerceptionFactory — assembles and caches the processing pipeline
# ═══════════════════════════════════════════════════════════════════════════════


class PerceptionFactory:
    """
    Backward-compatible accessor for the shared ``ParserDispatcher``.

    ``get_dispatcher()`` delegates to ``docmirror.di.get_dispatcher()`` —
    there is only one process-wide singleton.  Prefer ``perceive_document()``
    for parsing; use this class only when you need direct dispatcher access
    in tests or custom integrations.
    """

    @classmethod
    def get_dispatcher(cls) -> ParserDispatcher:
        """Return the global ``ParserDispatcher`` (via DI container)."""
        from docmirror.di.container import get_dispatcher

        return get_dispatcher()

    @classmethod
    def reset(cls) -> None:
        """Reset all framework singletons (dispatcher, orchestrator, settings)."""
        from docmirror.di.container import reset_container

        reset_container()


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
) -> PerceiveResult:
    """
    Parse a document and return a ``PerceiveResult`` envelope.

    ``PerceiveResult.mirror`` is the frozen Mirror ``ParseResult``.
    Attribute access (``result.full_text``, etc.) delegates to ``mirror``.

    Args:
        file_path: Path to the document (PDF, image, Excel, Word, etc.).
        options:   Explicit parsing options. ``None`` → ``PerceiveOptions()``.

    Returns:
        ``PerceiveResult`` with ``mirror`` and optional ``editions`` dicts.
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

    if opts.editions:
        from docmirror.plugins.runner import run_plugin_extract

        edition_outputs: dict[str, Any] = {}
        full_text = getattr(result, "full_text", "") or ""
        fp = str(file_path)
        for edition in opts.editions:
            if edition not in ("community", "enterprise", "finance"):
                logger.warning("[PerceptionFactory] Unknown edition %r — skipped", edition)
                continue
            try:
                payload = await run_plugin_extract(
                    result,
                    edition=edition,  # type: ignore[arg-type]
                    full_text=full_text,
                    file_path=fp,
                )
                if payload is not None:
                    edition_outputs[edition] = payload
            except Exception as exc:
                logger.warning("[PerceptionFactory] edition %s failed: %s", edition, exc)
        if edition_outputs:
            return PerceiveResult(mirror=result, editions=edition_outputs)

    return PerceiveResult(mirror=result)
