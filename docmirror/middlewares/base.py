"""
Middleware Base Class and Pipeline Executor
===========================================

Design principles:
    - Each Middleware is an independent, composable Python class.
    - Unified ``process(EnhancedResult) -> EnhancedResult`` interface.
    - PipelineExecutor provides per-middleware exception isolation.
    - All data transformations are recorded via Mutations, without
      directly modifying the BaseResult.
"""
from __future__ import annotations


import concurrent.futures
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..models.enhanced import EnhancedResult
from ..core.exceptions import MiddlewareError

logger = logging.getLogger(__name__)


class BaseMiddleware(ABC):
    """
    Abstract Base Class for Middlewares.

    All Middlewares must implement the ``process()`` method.

    Causal Dependency Protocol (Deutsch V5: 'hard to vary' ordering):
        - ``DEPENDS_ON``: List of middleware class names that MUST run before this one.
        - ``PROVIDES``:   List of data keys this middleware contributes to the result.
        These declarations make the pipeline execution order *causally justified*
        rather than an arbitrary convention. The Orchestrator can topologically
        sort middlewares based on these declarations.

    Conventions:
        - Receives an EnhancedResult, returns the modified EnhancedResult.
        - Records all transformations via result.record_mutation().
        - Upon failure, should use add_error() rather than raising exceptions.
    """

    # ── Causal Dependency Declarations ──
    DEPENDS_ON: List[str] = []   # Middleware names that must run before this one
    PROVIDES: List[str] = []     # Data keys this middleware contributes

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._name = self.__class__.__name__

    @property
    def name(self) -> str:
        return self._name

    def should_skip(self, result: EnhancedResult) -> bool:
        """
        Conditional Skip: If True is returned, the Middleware is skipped.

        Subclasses can override this method to implement conditional logic.
        Default implementation: Checks the ``skip_scenes`` list in config.

        Example::

            class BankSpecificMiddleware(BaseMiddleware):
                def should_skip(self, result):
                    return result.scene not in ('bank_statement', 'unknown')
        """
        skip_scenes = self.config.get("skip_scenes")
        if skip_scenes and hasattr(result, "scene"):
            return result.scene in skip_scenes
        return False

    @abstractmethod
    def process(self, result: EnhancedResult) -> EnhancedResult:
        """Processes the EnhancedResult and returns the augmented Result."""
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

    Usage::

        pipeline = MiddlewarePipeline()
        result = pipeline.execute(
            middlewares=[SceneDetector(), EntityExtractor(), Validator()],
            result=initial_result,
        )
    """

    def __init__(
        self,
        fail_strategy: str = "skip",  # "skip" | "abort"
    ):
        self.fail_strategy = fail_strategy

    def execute(
        self,
        middlewares: List[BaseMiddleware],
        result: EnhancedResult,
    ) -> EnhancedResult:
        """
        Executes the Middleware Pipeline with parallel batching.

        T4-1: Middlewares with no DEPENDS_ON (or whose dependencies are
        already satisfied) are grouped into parallel batches and executed
        concurrently.  Middlewares with unsatisfied dependencies wait for
        their batch predecessors to complete first.

        Args:
            middlewares: Ordered list of Middlewares.
            result: Initial EnhancedResult.

        Returns:
            The processed EnhancedResult.
        """
        logger.info(
            f"[DocMirror] Pipeline \u25b6 {len(middlewares)} middlewares: "
            f"{[m.name for m in middlewares]}"
        )

        # ── Validate causal ordering (Deutsch V5) ──
        seen: set = set()
        for mw in middlewares:
            for dep in mw.DEPENDS_ON:
                if dep not in seen:
                    logger.warning(
                        f"[DocMirror] ⚠ Causal violation: {mw.name} depends on "
                        f"{dep}, but {dep} has not run yet in this pipeline."
                    )
            seen.add(mw.name)

        step_timings: Dict[str, float] = {}

        # ── T4-1: Group into parallel batches ──
        # Batch = set of middlewares whose DEPENDS_ON are all in `completed` set
        completed: set = set()
        remaining = list(middlewares)

        while remaining:
            # Find all middlewares whose dependencies are satisfied
            batch = []
            deferred = []
            for mw in remaining:
                deps_satisfied = all(dep in completed for dep in mw.DEPENDS_ON)
                if deps_satisfied:
                    batch.append(mw)
                else:
                    deferred.append(mw)
            remaining = deferred

            if not batch:
                # Circular dependency or bug — run remaining sequentially
                logger.warning(
                    f"[DocMirror] ⚠ Pipeline: unsatisfied deps for "
                    f"{[m.name for m in remaining]}, running sequentially"
                )
                batch = remaining
                remaining = []

            if len(batch) == 1:
                # Single middleware — run directly (no thread overhead)
                mw = batch[0]
                self._run_single(mw, result, step_timings)
                completed.add(mw.name)
            else:
                # Multiple independent middlewares — run in parallel
                logger.debug(
                    f"[DocMirror] T4-1: parallel batch: {[m.name for m in batch]}"
                )

                # C1 FIX: threading lock protects shared mutable state
                # (mutations list, errors list, status field).
                # enhanced_data dict writes are safe because each middleware
                # writes to distinct keys (scene, language, institution).
                import threading
                _result_lock = threading.Lock()

                # Monkey-patch result methods to be thread-safe for this batch
                _orig_add_mutation = result.add_mutation
                _orig_record_mutation = result.record_mutation
                _orig_add_error = result.add_error

                def _ts_add_mutation(mutation):
                    with _result_lock:
                        _orig_add_mutation(mutation)

                def _ts_record_mutation(*args, **kwargs):
                    with _result_lock:
                        _orig_record_mutation(*args, **kwargs)

                def _ts_add_error(error):
                    with _result_lock:
                        _orig_add_error(error)

                result.add_mutation = _ts_add_mutation
                result.record_mutation = _ts_record_mutation
                result.add_error = _ts_add_error

                def _run_mw(m):
                    """Run a single middleware, return (name, mutations, elapsed)."""
                    if m.should_skip(result):
                        return (m.name, 0, 0.0, None)
                    t0 = time.time()
                    try:
                        m.process(result)
                        elapsed = (time.time() - t0) * 1000
                        with _result_lock:
                            num_mut = sum(
                                1 for mut in result.mutations
                                if mut.middleware_name == m.name
                            )
                        return (m.name, num_mut, elapsed, None)
                    except Exception as e:
                        elapsed = (time.time() - t0) * 1000
                        return (m.name, 0, elapsed, e)

                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as executor:
                        futures = {executor.submit(_run_mw, mw): mw for mw in batch}
                        for future in concurrent.futures.as_completed(futures):
                            name, num_mut, elapsed, error = future.result()
                            step_timings[name] = round(elapsed, 1)
                            if error:
                                from ..core.exceptions import MiddlewareError
                                mw_error = MiddlewareError(
                                    str(error), middleware_name=name
                                )
                                logger.warning(f"[DocMirror] {mw_error}", exc_info=True)
                                result.add_error(str(mw_error))
                                if self.fail_strategy == "abort":
                                    logger.warning(
                                        f"[DocMirror] Pipeline aborted at {name}"
                                    )
                                    result.status = "failed"
                                    remaining = []
                                    break
                            elif elapsed > 0:
                                logger.info(
                                    f"[DocMirror] {name} \u25c0 {elapsed:.0f}ms | "
                                    f"mutations=+{num_mut}"
                                )
                            else:
                                logger.info(f"[DocMirror] {name} \u23ed skipped")
                finally:
                    # Restore original (non-locked) methods
                    result.add_mutation = _orig_add_mutation
                    result.record_mutation = _orig_record_mutation
                    result.add_error = _orig_add_error

                for mw in batch:
                    completed.add(mw.name)

        # Record total execution timings
        result.enhanced_data["step_timings"] = step_timings

        total_mutations = result.mutation_count
        logger.info(
            f"[DocMirror] Pipeline \u25c0 status={result.status} | "
            f"total_mutations={total_mutations}"
        )

        return result

    def _run_single(
        self,
        mw: BaseMiddleware,
        result: EnhancedResult,
        step_timings: Dict[str, float],
    ) -> None:
        """Execute a single middleware sequentially (original path)."""
        if mw.should_skip(result):
            logger.info(f"[DocMirror] {mw.name} \u23ed skipped")
            step_timings[mw.name] = 0.0
            return

        t0 = time.time()
        try:
            logger.debug(f"[DocMirror] Running {mw.name}...")
            result_new = mw.process(result)
            # Some middlewares return a new result object
            if result_new is not result:
                # Copy mutations/data from new result
                for attr in ("scene", "institution", "status"):
                    if hasattr(result_new, attr):
                        setattr(result, attr, getattr(result_new, attr))
                result.enhanced_data.update(result_new.enhanced_data)
            elapsed = (time.time() - t0) * 1000
            step_timings[mw.name] = round(elapsed, 1)
            num_mutations = sum(
                1 for m in result.mutations if m.middleware_name == mw.name
            )
            logger.info(
                f"[DocMirror] {mw.name} \u25c0 {elapsed:.0f}ms | "
                f"mutations=+{num_mutations}"
            )
        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            step_timings[mw.name] = round(elapsed, 1)
            from ..core.exceptions import MiddlewareError
            mw_error = MiddlewareError(
                str(e), middleware_name=mw.name
            )
            logger.warning(f"[DocMirror] {mw_error}", exc_info=True)
            result.add_error(str(mw_error))
            if self.fail_strategy == "abort":
                logger.warning(
                    f"[DocMirror] Pipeline aborted at {mw.name}"
                )
                result.status = "failed"
