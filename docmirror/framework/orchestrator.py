# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Orchestrator — Mirror-Layer Middleware Pipeline (MEP)
======================================================

Runs **after** format adapters finish ``to_parse_result()`` and **before**
the Mirror ``ParseResult`` is returned to callers.

See ``docs/design/08_middleware_layer_first_principles_redesign.md``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Literal

from ..configs.middleware.catalog import get_middleware_class, get_middleware_stage
from ..configs.middleware.resolver import resolve_pipeline
from ..configs.runtime.settings import DocMirrorSettings
from .middlewares import BaseMiddleware, MiddlewarePipeline
from ..models.entities.parse_result import ParseResult, ResultStatus

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Middleware enhancement orchestrator (Mirror layer only).

    Plugin execution (Community / Enterprise / Finance) happens **after**
    ``enhance()`` via ``docmirror.plugins.runner`` — not in this pipeline.
    """

    def __init__(
        self,
        settings: DocMirrorSettings | None = None,
        config: dict[str, Any] | None = None,
        fail_strategy: str | None = None,
        seal_detector_fn: Callable | None = None,  # noqa: ARG002 — legacy hook reserved
    ):
        self.settings = settings or DocMirrorSettings.from_env()
        self.config = config or self.settings.to_dict()
        self.pipeline = MiddlewarePipeline(fail_strategy=fail_strategy or self.settings.fail_strategy)

    async def enhance(
        self,
        result: ParseResult,
        enhance_mode: Literal["raw", "standard", "full"] = "standard",
        file_type: str = "unknown",
        content_model: str = "",
        on_progress: Callable[[str, float, str], None] | None = None,
        **_kwargs,
    ) -> ParseResult:
        t0 = time.time()
        _on_progress = on_progress

        # Emit middleware_pipeline at 0% — middleware phase begins
        if _on_progress:
            _on_progress(
                "middleware_pipeline", 0.0,
                "Running validation & enrichment middlewares...",
            )

        logger.info(
            f"[Orchestrator] Pipeline ▶ mode={enhance_mode} | file_type={file_type} | "
            f"content_model={content_model or 'auto'} | pages={result.page_count}"
        )

        if not result.pages:
            logger.warning("[Orchestrator] Empty ParseResult — no pages")
            result.status = ResultStatus.FAILURE
            result.add_error("Empty extraction result")
            return result

        if enhance_mode == "raw":
            logger.info("[Orchestrator] Raw mode — skipping middleware pipeline")
        else:
            middlewares = self._build_middlewares(enhance_mode, file_type, content_model, result)
            result = self.pipeline.execute(middlewares, result)

        elapsed = (time.time() - t0) * 1000
        result.processing_time = elapsed
        result.parser_info.elapsed_ms = elapsed

        if result.mutations:
            try:
                from .middlewares import MutationAnalyzer

                analyzer = MutationAnalyzer()
                analysis = analyzer.analyze(result.mutations)
                from docmirror.models.ehl import attach_pipeline_debug

                attach_pipeline_debug(result, "mutation_analysis", analysis.to_dict())
            except Exception as e:
                logger.debug(f"[Orchestrator] MutationAnalyzer error bypass: {e}")

        logger.info(
            f"[Orchestrator] Pipeline ◀ status={result.status.value} | "
            f"scene={result.entities.document_type} | "
            f"mutations={result.mutation_count} | "
            f"elapsed={elapsed:.0f}ms"
        )

        # Emit middleware_pipeline at 100% — middleware phase complete
        if _on_progress:
            _on_progress(
                "middleware_pipeline", 100.0,
                "Middleware pipeline complete",
            )

        return result

    def _build_middlewares(
        self,
        enhance_mode: str,
        file_type: str = "pdf",
        content_model: str = "",
        result: ParseResult | None = None,
    ) -> list[BaseMiddleware]:
        from ..configs.format.enhancement import transport_to_content_model

        model = content_model or transport_to_content_model(file_type)
        middleware_names = resolve_pipeline(model, enhance_mode, result, file_type=file_type)
        middlewares: list[BaseMiddleware] = []

        for name in middleware_names:
            try:
                cls = get_middleware_class(name)
            except (KeyError, TypeError) as exc:
                logger.warning(f"[Orchestrator] Unresolved middleware {name!r}: {exc}")
                continue
            stage = get_middleware_stage(name)
            mw_config = self.config.get(name, {})
            middlewares.append(cls(config=mw_config))
            logger.info(
                "[Orchestrator] stage=%s middleware=%s",
                stage or "?",
                name,
            )

        return middlewares
