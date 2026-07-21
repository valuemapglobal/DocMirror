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

Downstream: ``input.acceptance``, ``framework.dispatcher``, and the canonical pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from docmirror.framework.dispatcher import ParserDispatcher
from docmirror.input.entry.options import ParsePolicy, normalize_parse_policy

if TYPE_CHECKING:
    from docmirror.models.entities.parse_result import ParseResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Explicit Options — replaces implicit env-vars / global config
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class PerceiveOptions:
    """
    Request-scoped policy and runtime hooks for ``perceive_document``.

    All fields are optional; defaults match the current production behaviour.

    Examples::

        # First page only (fast preview)
        PerceiveOptions(policy=normalize_parse_policy(max_pages=1))

        # Full enhancement with progress callback
        PerceiveOptions(policy=normalize_parse_policy(mode="accurate"), on_progress=callback)
    """

    # ── Callbacks ──
    on_progress: Callable[..., None] | None = None
    """Optional progress callback (compatible with ``ProgressBus.emit``)."""

    max_workers: int | None = None
    """Optional runtime page concurrency; never part of fact identity."""

    policy: ParsePolicy | None = None
    """Fact-affecting policy. Runtime and delivery values are not accepted here."""

    def normalized_policy(self) -> ParsePolicy:
        """Return the effective fact policy for this request."""
        return normalize_parse_policy(self.policy)


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
    options: PerceiveOptions | None = None,
) -> ParseResult:
    """Public entry point delegated to ``docmirror.input.pipeline``."""
    from docmirror.input.pipeline import perceive_document as _new

    return await _new(file_path, options)
