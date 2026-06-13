# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Orchestrator — Post-Extraction Middleware Pipeline
===================================================

Runs **after** format adapters finish ``to_parse_result()`` and **before**
the final ``ParseResult`` is returned to callers.

Position in the end-to-end flow::

    ParserDispatcher.process()
      → Adapter.to_parse_result()     # L0: raw extraction
      → BaseParser.perceive()
           → Orchestrator.enhance()   # ★ this module
      → ParseResult

Responsibilities (this file only):
    1. Guard against empty extraction (no pages → FAILURE, skip middleware).
    2. Resolve which middlewares to run from ``configs/pipeline_registry.py``.
    3. Instantiate middleware classes via ``MIDDLEWARE_REGISTRY``.
    4. Execute them sequentially through ``MiddlewarePipeline`` (in-place).
    5. Record timing and optional mutation analysis.

What this file does **not** do:
    - Read files or select adapters (see ``framework/dispatcher.py``).
    - Run domain plugins (see ``plugins/`` — downstream of middleware).

Enhancement modes (``enhance_mode``):
    ``raw``
        Skip all middleware; return the adapter extraction unchanged.
        Set via ``PerceiveOptions(enhance_mode="raw")`` or env
        ``DOCMIRROR_ENHANCE_MODE=raw``.

    ``standard`` (default)
        Format-specific pipeline from ``FORMAT_PIPELINES`` in
        ``pipeline_registry.py``.  Examples as of current config:

        - ``pdf``   → EntityExtractor → EvidenceEngine → InstitutionDetector
                      → Validator
        - ``image`` / ``word`` → LanguageDetector → GenericEntityExtractor
        - ``excel`` → GenericEntityExtractor
        - other types (ppt, email, ofd, archive, …) → ``*`` fallback
                      → LanguageDetector

    ``full``
        Longer pipeline where defined (currently PDF only).  Names listed in
        ``pipeline_registry`` must also exist in ``MIDDLEWARE_REGISTRY`` below
        or they are skipped with a warning (e.g. ``TableStructureFixer``).

Optional runtime append (not in this file):
    ``DOCMIRROR_ENABLE_SLM=1`` → ``get_pipeline_config()`` appends
    ``SLMEntityExtractor`` to the resolved list.

Failure handling:
    ``MiddlewarePipeline`` uses ``fail_strategy`` from settings (default
    ``"skip"``): a failing middleware is logged, an error is attached to the
    result, and the pipeline continues.  ``"abort"`` stops the pipeline and
    sets ``ResultStatus.FAILURE`` (env ``DOCMIRROR_FAIL_STRATEGY``).

Classification note:
    Document-type detection is performed by ``EvidenceEngine`` (120 business
    categories via ``classification_rules.yaml``).  The legacy ``SceneDetector``
    middleware is **not** used in current pipelines.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Literal

from ..configs.settings import DocMirrorSettings
from ..core.classification.evidence_engine import EvidenceEngine
from ..middlewares import (
    BaseMiddleware,
    EntityExtractor,
    GenericEntityExtractor,
    InstitutionDetector,
    LanguageDetector,
    MiddlewarePipeline,
    SLMEntityExtractor,
    Validator,
)
from ..models.entities.parse_result import ParseResult, ResultStatus

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Middleware Registry
# ═══════════════════════════════════════════════════════════════════════════════
#
# Maps string names (used in pipeline_registry.FORMAT_PIPELINES) to classes.
#
# To add a new middleware:
#   1. Implement ``BaseMiddleware`` in ``middlewares/``.
#   2. Register the class here under its ``__name__``.
#   3. Append that name to the appropriate list in ``pipeline_registry.py``.
#
# Names referenced in pipeline_registry but missing here are skipped at runtime
# with ``[Orchestrator] Unresolved middleware`` (see ``_build_middlewares``).

MIDDLEWARE_REGISTRY: dict[str, type[BaseMiddleware]] = {
    # ── PDF / financial document pipeline ──
    "EvidenceEngine": EvidenceEngine,       # 120-type classification (replaces SceneDetector)
    "EntityExtractor": EntityExtractor,     # KV / table / regex entities (PDF-oriented)
    "InstitutionDetector": InstitutionDetector,
    "Validator": Validator,
    # ── Cross-format middlewares ──
    "LanguageDetector": LanguageDetector,
    "GenericEntityExtractor": GenericEntityExtractor,
    "SLMEntityExtractor": SLMEntityExtractor,  # optional; appended when DOCMIRROR_ENABLE_SLM=1
}


class Orchestrator:
    """
    Middleware enhancement orchestrator.

    Typically constructed by ``BaseParser.perceive()`` once per document.
    A singleton is also available via ``docmirror.di.container.get_orchestrator()``
    for tests and DI.

    Usage::

        orchestrator = Orchestrator()
        result = await orchestrator.enhance(
            parse_result,
            enhance_mode="standard",
            file_type="pdf",
        )
    """

    def __init__(
        self,
        settings: DocMirrorSettings | None = None,
        config: dict[str, Any] | None = None,
        fail_strategy: str | None = None,
        seal_detector_fn: Callable | None = None,
    ):
        """
        Args:
            settings: Global DocMirror settings.  Defaults to
                ``DocMirrorSettings.from_env()``.
            config: Per-middleware config dict passed as
                ``cls(config=self.config.get(name, {}))``.  Defaults to
                ``settings.to_dict()``.
            fail_strategy: ``"skip"`` (default) or ``"abort"`` — forwarded to
                ``MiddlewarePipeline``.  Overrides ``settings.fail_strategy``
                when set.
            seal_detector_fn: Reserved hook; not used by current pipelines.
        """
        self.settings = settings or DocMirrorSettings.from_env()
        self.config = config or self.settings.to_dict()
        self.pipeline = MiddlewarePipeline(
            fail_strategy=fail_strategy or self.settings.fail_strategy
        )

    async def enhance(
        self,
        result: ParseResult,
        enhance_mode: Literal["raw", "standard", "full"] = "standard",
        file_type: str = "unknown",
        **kwargs,
    ) -> ParseResult:
        """
        Run the middleware pipeline on an extracted ``ParseResult``.

        The same ``result`` object is mutated in-place and returned.  Middleware
        steps record changes via ``result.record_mutation()``; per-step timings
        are stored in ``result.entities.domain_specific["step_timings"]``.

        Args:
            result: Raw ``ParseResult`` from ``Adapter.to_parse_result()``.
            enhance_mode: ``raw`` | ``standard`` | ``full`` (see module docstring).
            file_type: Logical format from dispatcher (``pdf``, ``excel``,
                ``archive``, …) — selects ``FORMAT_PIPELINES`` entry.
            **kwargs: Unused; accepted for forward compatibility.

        Returns:
            The enriched ``ParseResult`` (same instance as ``result``).
        """
        t0 = time.time()

        logger.info(
            f"[Orchestrator] Pipeline ▶ mode={enhance_mode} | file_type={file_type} | pages={result.page_count}"
        )

        # ── Step 1: Empty extraction guard ──
        # Adapters should not reach here with zero pages, but bail early to
        # avoid running EvidenceEngine / EntityExtractor on empty input.
        if not result.pages:
            logger.warning("[Orchestrator] Empty ParseResult — no pages")
            result.status = ResultStatus.FAILURE
            result.add_error("Empty extraction result")
            return result

        # ── Step 2: Middleware pipeline ──
        # ``raw`` bypasses middleware entirely (extraction-only mode).
        if enhance_mode == "raw":
            logger.info("[Orchestrator] Raw mode — skipping middleware pipeline")
        else:
            middlewares = self._build_middlewares(enhance_mode, file_type)
            result = self.pipeline.execute(middlewares, result)

        # ── Step 3: Orchestrator-level timing ──
        # Note: ``parser_info.elapsed_ms`` here covers middleware only; the
        # dispatcher overwrites it with total wall time including extraction.
        elapsed = (time.time() - t0) * 1000
        result.processing_time = elapsed
        result.parser_info.elapsed_ms = elapsed

        # ── Step 4: Mutation summary (best-effort) ──
        if result.mutations:
            try:
                from ..middlewares import MutationAnalyzer

                analyzer = MutationAnalyzer()
                analysis = analyzer.analyze(result.mutations)
                result.entities.domain_specific["mutation_analysis"] = analysis.to_dict()
            except Exception as e:
                logger.debug(f"[Orchestrator] MutationAnalyzer error bypass: {e}")

        logger.info(
            f"[Orchestrator] Pipeline ◀ status={result.status.value} | "
            f"scene={result.entities.document_type} | "
            f"mutations={result.mutation_count} | "
            f"elapsed={elapsed:.0f}ms"
        )

        return result

    def _build_middlewares(
        self,
        enhance_mode: str,
        file_type: str = "pdf",
    ) -> list[BaseMiddleware]:
        """
        Resolve middleware **names** from ``pipeline_registry`` into instances.

        Lookup is delegated to ``get_pipeline_config(file_type, enhance_mode)``,
        which applies format/mode fallbacks and optional SLM append.

        Each instance receives ``config=self.config.get(middleware_name, {})``.
        Unknown names are logged and omitted (pipeline continues with the rest).
        """
        from ..configs.pipeline_registry import get_pipeline_config

        middleware_names = get_pipeline_config(file_type, enhance_mode)
        middlewares: list[BaseMiddleware] = []

        for name in middleware_names:
            cls = MIDDLEWARE_REGISTRY.get(name)
            if cls is None:
                logger.warning(f"[Orchestrator] Unresolved middleware: {name}")
                continue
            mw_config = self.config.get(name, {})
            middlewares.append(cls(config=mw_config))

        return middlewares
