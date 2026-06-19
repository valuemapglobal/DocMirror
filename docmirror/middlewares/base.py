# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Middleware Base Class and Pipeline Executor
===========================================

Design principles:
    - Each Middleware is an independent, composable Python class.
    - Unified ``process(ParseResult) -> ParseResult`` interface.
    - PipelineExecutor provides per-middleware exception isolation.
    - All data transformations are recorded via Mutations on ParseResult.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from ..core.entry.exceptions import MiddlewareError
from ..models.entities.parse_result import ParseResult

logger = logging.getLogger(__name__)


class BaseMiddleware(ABC):
    """
    Abstract Base Class for Middlewares.

    All Middlewares must implement the ``process()`` method.

    Causal Dependency Protocol:
        - ``DEPENDS_ON``: List of middleware class names that MUST run before this one.
        - ``PROVIDES``:   List of data keys this middleware contributes to the result.

    Conventions:
        - Receives a ParseResult, returns the modified ParseResult.
        - Records all transformations via result.record_mutation().
        - Upon failure, should use add_error() rather than raising exceptions.
    """

    # ── Causal Dependency Declarations ──
    DEPENDS_ON: list[str] = []  # Middleware names that must run before this one
    PROVIDES: list[str] = []  # Data keys this middleware contributes

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._name = self.__class__.__name__

    @property
    def name(self) -> str:
        return self._name

    def should_skip(self, result: ParseResult) -> bool:
        """
        Conditional Skip: If True is returned, the Middleware is skipped.

        Subclasses can override this method to implement conditional logic.
        Default implementation: Checks the ``skip_scenes`` list in config.
        """
        skip_scenes = self.config.get("skip_scenes")
        if skip_scenes:
            return result.entities.document_type in skip_scenes
        return False

    @abstractmethod
    def process(self, result: ParseResult) -> ParseResult:
        """Processes the ParseResult and returns the augmented Result."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.name}>"


class MiddlewarePipeline:
    """
    Middleware Pipeline Executor.

    Responsibilities:
        1. Sequentially executes the provided list of Middlewares.
        2. Implements per-middleware try/except exception isolation.
        3. Decides whether to [Skip] or [Abort] based on the strategy.
        4. Records the execution time of each Middleware.
    """

    def __init__(
        self,
        fail_strategy: str = "skip",  # "skip" | "abort"
    ):
        self.fail_strategy = fail_strategy

    def execute(
        self,
        middlewares: list[BaseMiddleware],
        result: ParseResult,
    ) -> ParseResult:
        """Executes the Middleware Pipeline sequentially."""
        logger.info(f"[Middleware] Pipeline ▶ {len(middlewares)} middlewares: {[m.name for m in middlewares]}")

        step_timings: dict[str, float] = {}

        for mw in middlewares:
            self._run_single(mw, result, step_timings)

        result.entities.domain_specific["step_timings"] = step_timings

        total_mutations = result.mutation_count
        logger.info(
            f"[Middleware] Pipeline ◀ status={result.status.value} | "
            f"total_mutations={total_mutations} | timings={step_timings}"
        )

        return result

    def _run_single(
        self,
        mw: BaseMiddleware,
        result: ParseResult,
        step_timings: dict[str, float],
    ) -> None:
        """Execute a single middleware sequentially (original path)."""
        if mw.should_skip(result):
            logger.info(f"[Middleware] {mw.name} \u23ed skipped")
            step_timings[mw.name] = 0.0
            return

        t0 = time.time()
        try:
            logger.debug(f"[DocMirror] Running {mw.name}...")
            result_new = mw.process(result)
            # Some middlewares may return a new result; merge key fields
            if result_new is not result:
                for attr in ("status",):
                    if hasattr(result_new, attr):
                        setattr(result, attr, getattr(result_new, attr))
                result.entities = result_new.entities
            elapsed = (time.time() - t0) * 1000
            step_timings[mw.name] = round(elapsed, 1)
            num_mutations = sum(1 for m in result.mutations if m.middleware_name == mw.name)
            logger.info(f"[Middleware] {mw.name} \u25c0 {elapsed:.0f}ms | mutations=+{num_mutations}")
        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            step_timings[mw.name] = round(elapsed, 1)
            mw_error = MiddlewareError(str(e), middleware_name=mw.name)
            logger.warning(f"[Middleware] {mw_error}", exc_info=True)
            result.add_error(str(mw_error))
            if self.fail_strategy == "abort":
                logger.warning(f"[Middleware] Pipeline aborted at {mw.name}")
                from ..models.entities.parse_result import ResultStatus

                result.status = ResultStatus.FAILURE
