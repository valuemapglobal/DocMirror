"""
Middleware base class与PipelineExecutor (Middleware Base & Pipeline)
====================================================

Design principles:
    - eachMiddleware是独立的、可Composition的 Python 类
    - 统一 ``process(EnhancedResult) -> EnhancedResult`` Interface
    - PipelineExecutor提供 per-middleware Exception隔离和Degradation strategy
    - allData变换via Mutation 记录，不直接修改 BaseResult
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..models.enhanced import EnhancedResult
from ..core.exceptions import MiddlewareError

logger = logging.getLogger(__name__)


class BaseMiddleware(ABC):
    """
    MiddlewareAbstractBase class。

    allMiddleware必须implement ``process()`` Method。
    约定:
        - 接收 EnhancedResult，Returns修改后的 EnhancedResult
        - via result.record_mutation() 记录all变换
        - Failed时应 add_error() 而非抛出Exception
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._name = self.__class__.__name__

    @property
    def name(self) -> str:
        return self._name

    def should_skip(self, result: EnhancedResult) -> bool:
        """条件Skip: Returns True 时整个Middleware不Execute。

        Subclass可覆写此Methodimplement条件Skip逻辑。
        Defaultimplement: 检查 config 中的 ``skip_scenes`` List。

        示例::

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
        """Processing EnhancedResult 并Returns增强后的Result。"""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.name}>"


class MiddlewarePipeline:
    """
    MiddlewarePipelineExecutor。

    Responsibilities:
        1. 顺序ExecuteMiddlewareList
        2. Per-middleware try/except Exception隔离
        3. based on策略决定 [SkipFailedMiddleware] 或 [终止Pipeline]
        4. 记录eachMiddleware的耗时

    Usage::

        pipeline = MiddlewarePipeline()
        result = pipeline.execute(
            middlewares=[SceneDetector(), ColumnMapper(), Validator()],
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
        顺序ExecuteMiddlewarePipeline。

        Args:
            middlewares: 有序MiddlewareList。
            result: 初始 EnhancedResult。

        Returns:
            Processing后的 EnhancedResult。
        """
        logger.info(
            f"[DocMirror] Pipeline ▶ {len(middlewares)} middlewares: "
            f"{[m.name for m in middlewares]}"
        )

        step_timings: Dict[str, float] = {}

        for mw in middlewares:
            # ── 条件Skip检查 ──
            if mw.should_skip(result):
                logger.info(f"[DocMirror] {mw.name} ⏭ skipped (should_skip=True)")
                step_timings[mw.name] = 0.0
                continue

            t0 = time.time()
            try:
                logger.debug(f"[DocMirror] Running {mw.name}...")
                result = mw.process(result)
                elapsed = (time.time() - t0) * 1000
                step_timings[mw.name] = round(elapsed, 1)
                logger.info(
                    f"[DocMirror] {mw.name} ◀ {elapsed:.0f}ms | "
                    f"mutations=+{sum(1 for m in result.mutations if m.middleware_name == mw.name)}"
                )

            except Exception as e:
                elapsed = (time.time() - t0) * 1000
                step_timings[mw.name] = round(elapsed, 1)
                mw_error = MiddlewareError(
                    str(e), middleware_name=mw.name
                )
                logger.warning(f"[DocMirror] {mw_error}", exc_info=True)
                result.add_error(str(mw_error))

                if self.fail_strategy == "abort":
                    logger.warning(f"[DocMirror] Pipeline aborted at {mw.name}")
                    result.status = "failed"
                    break
                else:
                    logger.info(f"[DocMirror] Skipping {mw.name}, continuing pipeline")

        # 记录总耗时
        result.enhanced_data["step_timings"] = step_timings

        total_mutations = result.mutation_count
        logger.info(
            f"[DocMirror] Pipeline ◀ status={result.status} | "
            f"total_mutations={total_mutations}"
        )

        return result
