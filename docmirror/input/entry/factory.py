# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Document perception factory — single public entry point for parsing.

Purpose: Accepts a file path and explicit ``PerceiveOptions``, delegates to
``ParserDispatcher``, and returns a ``ParseResult``.
All configuration is explicit; no hidden globals.

Main components: ``perceive_document``, ``PerceptionFactory``,
``PerceiveOptions``.

Upstream: Application / API layer.

Downstream: ``framework.dispatcher``, ``bridge.parse_result_bridge``,
``extraction.extractor``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from docmirror.framework.dispatcher import ParserDispatcher
from docmirror.input.entry.options import ParseControl, normalize_parse_control

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
    """No-op retained for public API stability; parse cache is not in the default pipeline."""

    # ── Callbacks ──
    # ── Callbacks ──
    on_progress: Callable[..., None] | None = None
    """Optional progress callback (compatible with ``ProgressBus.emit``)."""

    # ── Legacy edition convenience option ──
    editions: list[str] = field(default_factory=list)
    """Deprecated no-op; select editions through ``ParseControl.output``."""

    # ── Unified parse control (new contract) ──
    control: ParseControl | None = None
    """Unified request-scoped parse control. Explicit values override convenience fields."""

    def normalized_control(self) -> ParseControl:
        """Return the effective ParseControl for this request."""
        return normalize_parse_control(
            self.control,
            max_pages=self.max_pages,
            skip_cache=self.skip_cache,
            enhance_mode=self.enhance_mode,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PerceptionFactory — assembles and caches the processing pipeline
# ═══════════════════════════════════════════════════════════════════════════════


class PerceptionFactory:
    """
    Accessor for the shared ``ParserDispatcher``.

    ``get_dispatcher()`` delegates to ``docmirror.framework.di.get_dispatcher()`` —
    there is only one process-wide singleton.  Prefer ``perceive_document()``
    for parsing; use this class only when you need direct dispatcher access
    in tests or custom integrations.
    """

    @classmethod
    def get_dispatcher(cls) -> ParserDispatcher:
        """Return the global ``ParserDispatcher`` (via DI container)."""
        from docmirror.framework.di.container import get_dispatcher

        return get_dispatcher()

    @classmethod
    def reset(cls) -> None:
        """Reset all framework singletons (dispatcher, orchestrator, settings)."""
        from docmirror.framework.di.container import reset_container

        reset_container()


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience entry point
# ═══════════════════════════════════════════════════════════════════════════════


async def perceive_document(
    file_path: str | Path,
    control: PerceiveOptions | None = None,
) -> ParseResult:
    """Public entry point delegated to ``docmirror.input.pipeline``."""
    from docmirror.input.pipeline import perceive_document as _new

    return await _new(file_path, control)
