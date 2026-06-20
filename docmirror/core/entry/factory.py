# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Document perception factory — single public entry point for parsing.

Purpose: Accepts a file path and explicit ``PerceiveOptions``, delegates to
``ParserDispatcher``, and returns a ``PerceiveResult`` / ``ParseResult``.
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

from docmirror.core.entry.options import ParseControl, normalize_parse_control
from docmirror.core.entry.perceive_result import PerceiveResult
from docmirror.framework.dispatcher import ParserDispatcher

if TYPE_CHECKING:
    pass

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

    # ── Unified parse control (new contract) ──
    control: ParseControl | None = None
    """Unified request-scoped parse control. Legacy fields above are shims."""

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
    control = opts.normalized_control()
    if control.slm:
        import os

        os.environ["DOCMIRROR_ENABLE_SLM"] = "1"

    logger.info(
        f"[PerceptionFactory] ▶ perceive_document | "
        f"file={file_path} | mode={control.mode}/{control.enhance_mode} | "
        f"pages={control.pages.to_display()} | "
        f"workers={control.resource.workers} | "
        f"formats={','.join(control.output.formats)} | "
        f"skip_cache={control.skip_cache}"
    )

    dispatcher = PerceptionFactory.get_dispatcher()
    result = await dispatcher.process(
        str(file_path),
        skip_cache=control.skip_cache,
        on_progress=opts.on_progress,
        enhance_mode=control.enhance_mode,
        max_pages=control.pages.max_pages,
        parse_control=control,
        document_type=control.doc_type_hint.value if control.doc_type_hint else None,
    )

    if opts.editions:
        from copy import deepcopy

        from docmirror.edition_facade import build_edition_projections

        core_mirror = deepcopy(result)
        requested = tuple(ed for ed in opts.editions if ed in {"community", "enterprise", "finance"})
        projections = build_edition_projections(
            result,
            full_text=getattr(result, "full_text", "") or "",
            file_path=str(file_path),
            mirror_level=control.output.mirror_level,
            include_text=control.output.include_text,
            editions=requested,
        )
        edition_outputs = {
            edition: payload for edition, payload in projections.items() if edition != "mirror" and payload is not None
        }
        if edition_outputs:
            return PerceiveResult(mirror=core_mirror, editions=edition_outputs)
        return PerceiveResult(mirror=core_mirror)

    return PerceiveResult(mirror=result)
