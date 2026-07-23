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

from docmirror.input.entry.exceptions import MiddlewareError
from docmirror.models.entities.parse_result import ParseResult

logger = logging.getLogger(__name__)


def _mutation_covers_fact_path(field_changed: str, fact_path: str) -> bool:
    """Return whether an audit target owns a concrete canonical change."""
    field = str(field_changed or "").strip().strip(".")
    if not field:
        return False
    if field == fact_path:
        return True
    return fact_path.startswith(f"{field}.") or fact_path.startswith(f"{field}[")


def _middleware_owns_mutation(middleware_name: str, actor: str) -> bool:
    """Canonical capabilities are child actors of the domain enricher."""
    if actor == middleware_name:
        return True
    return middleware_name == "CanonicalDomainEnricher" and actor.startswith("canonical:")


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
            result = self._run_single(mw, result, step_timings)

        # Execution timings are diagnostics, not domain facts. Keep them in
        # parser metadata so worker scheduling cannot contaminate fact identity.
        result.parser_info.structure = {
            **dict(result.parser_info.structure or {}),
            "step_timings": step_timings,
        }

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
    ) -> ParseResult:
        """Execute a single middleware sequentially (original path)."""
        if mw.should_skip(result):
            logger.info(f"[Middleware] {mw.name} \u23ed skipped")
            step_timings[mw.name] = 0.0
            return result

        from docmirror.models.fingerprint import canonical_fact_diff, canonical_fact_payload

        before_facts = canonical_fact_payload(result)
        before_mutation_count = len(result.mutations)
        t0 = time.time()
        try:
            logger.debug(f"[DocMirror] Running {mw.name}...")
            result_new = mw.process(result)
            if not isinstance(result_new, ParseResult):
                raise TypeError(f"{mw.name}.process must return ParseResult")
            after_facts = canonical_fact_payload(result_new)
            fact_changes = canonical_fact_diff(before_facts, after_facts)
            new_mutations = result_new.mutations[before_mutation_count:]
            owned_mutations = [
                mutation
                for mutation in new_mutations
                if _middleware_owns_mutation(mw.name, str(mutation.middleware_name or ""))
            ]
            uncovered = [
                path
                for path in fact_changes
                if not any(_mutation_covers_fact_path(mutation.field_changed, path) for mutation in owned_mutations)
            ]
            if uncovered:
                preview = ", ".join(uncovered[:8])
                if len(uncovered) > 8:
                    preview += f", ... (+{len(uncovered) - 8})"
                raise MiddlewareError(
                    f"canonical mutation audit gap: {preview}",
                    middleware_name=mw.name,
                )
            result = result_new
            elapsed = (time.time() - t0) * 1000
            step_timings[mw.name] = round(elapsed, 1)
            num_mutations = sum(1 for m in result.mutations if m.middleware_name == mw.name)
            logger.info(f"[Middleware] {mw.name} \u25c0 {elapsed:.0f}ms | mutations=+{num_mutations}")
            return result
        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            step_timings[mw.name] = round(elapsed, 1)
            if isinstance(e, MiddlewareError) and "canonical mutation audit gap" in str(e):
                raise
            leaked_changes = canonical_fact_diff(before_facts, canonical_fact_payload(result))
            if leaked_changes:
                preview = ", ".join(list(leaked_changes)[:8])
                logger.error(
                    "[Middleware] %s changed canonical facts before failing: %s",
                    mw.name,
                    preview,
                )
                raise MiddlewareError(
                    f"middleware failed after changing canonical facts: {preview}",
                    middleware_name=mw.name,
                ) from e
            mw_error = MiddlewareError(str(e), middleware_name=mw.name)
            logger.warning(f"[Middleware] {mw_error}", exc_info=True)
            result.add_error(str(mw_error))
            if self.fail_strategy == "abort":
                logger.warning(f"[Middleware] Pipeline aborted at {mw.name}")
                from docmirror.models.entities.parse_result import ResultStatus

                result.status = ResultStatus.FAILURE
            return result
