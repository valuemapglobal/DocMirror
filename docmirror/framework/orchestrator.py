"""
Orchestrate layer (Orchestrator)
======================

系统的"大脑" — 负责全流程Orchestrate:
    1. call CoreExtractor 生成 BaseResult
    2. based on enhance_mode 动态构建MiddlewarePipeline
    3. ExecutePipeline，收集Result
    4. 桥接Output为 v1 兼容的 ParserOutput

三种增强Mode:
    - ``raw``:      仅Extract，不增强
    - ``standard``: SceneDetector + EntityExtractor + InstitutionDetector + ColumnMapper + Validator
    - ``full``:     Standard + Repairer

ExceptionDegradation strategy:
    - MiddlewareFailed时Default skip 继续Execute
    - 保证始终Returns有效Result (即使 status="partial")
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Type

from ..core.extraction.extractor import CoreExtractor
from ..middlewares.base import BaseMiddleware, MiddlewarePipeline
from ..middlewares.scene_detector import SceneDetector
from ..middlewares.institution_detector import InstitutionDetector
from ..middlewares.entity_extractor import EntityExtractor
from ..middlewares.column_mapper import ColumnMapper
from ..middlewares.validator import Validator
from ..middlewares.repairer import Repairer
from ..middlewares.language_detector import LanguageDetector
from ..middlewares.generic_entity_extractor import GenericEntityExtractor
from ..models.enhanced import EnhancedResult
from ..models.domain import BaseResult
from ..configs.settings import DocMirrorSettings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# MiddlewareRegistry — Open/Closed Principle
# ═══════════════════════════════════════════════════════════════════════════════

MIDDLEWARE_REGISTRY: Dict[str, Type[BaseMiddleware]] = {
    "SceneDetector": SceneDetector,
    "EntityExtractor": EntityExtractor,
    "InstitutionDetector": InstitutionDetector,
    "ColumnMapper": ColumnMapper,
    "Validator": Validator,
    "Repairer": Repairer,
    # ── 跨Format通用Middleware ──
    "LanguageDetector": LanguageDetector,
    "GenericEntityExtractor": GenericEntityExtractor,
}

# PipelineConfiguration: enhance_mode → MiddlewareList
PIPELINE_CONFIGS: Dict[str, List[str]] = {
    "raw": [],
    "standard": ["SceneDetector", "EntityExtractor", "InstitutionDetector", "ColumnMapper", "Validator"],
    "full": ["SceneDetector", "EntityExtractor", "InstitutionDetector", "ColumnMapper", "Validator", "Repairer"],
}

# need to hints 注入的MiddlewareName
_HINTS_CONSUMERS = {"ColumnMapper"}


# ═══════════════════════════════════════════════════════════════════════════════
# hints.yaml Cache (mtime-based)
# ═══════════════════════════════════════════════════════════════════════════════

_hints_cache: Optional[Dict[str, Any]] = None
_hints_mtime: float = 0.0


def _load_hints_cached() -> Dict[str, Any]:
    """Load hints.yaml Configuration (mtime Cache)。"""
    global _hints_cache, _hints_mtime
    try:
        import yaml
        hints_path = Path(__file__).resolve().parent.parent / "configs" / "hints.yaml"
        if hints_path.exists():
            mtime = hints_path.stat().st_mtime
            if mtime != _hints_mtime or _hints_cache is None:
                with open(hints_path, "r", encoding="utf-8") as f:
                    _hints_cache = yaml.safe_load(f) or {}
                _hints_mtime = mtime
                logger.debug("[DocMirror] hints.yaml reloaded (mtime changed)")
    except Exception as e:
        logger.debug(f"[DocMirror] Failed to load hints.yaml: {e}")
    return _hints_cache or {}


class Orchestrator:
    """
    MultiModal Orchestrator — 全流程管理。

    Usage::

        orchestrator = Orchestrator()
        result = await orchestrator.run_pipeline(
            file_path=Path("bank_statement.pdf"),
            enhance_mode="full",
        )

        # 获取 v1 兼容Output
        parser_output = result.to_parser_output()
    """

    def __init__(
        self,
        settings: Optional[DocMirrorSettings] = None,
        config: Optional[Dict[str, Any]] = None,
        fail_strategy: Optional[str] = None,
        seal_detector_fn: Optional[Callable] = None,
    ):
        self.settings = settings or DocMirrorSettings.from_env()
        self.config = config or self.settings.to_dict()
        self.extractor = CoreExtractor(seal_detector_fn=seal_detector_fn)
        self.pipeline = MiddlewarePipeline(
            fail_strategy=fail_strategy or self.settings.fail_strategy
        )

    async def run_pipeline(
        self,
        file_path: Path,
        enhance_mode: Literal["raw", "standard", "full"] = "standard",
        file_type: str = "pdf",
        **kwargs,
    ) -> EnhancedResult:
        """
        Execute完整ParsePipeline。

        Args:
            file_path:    PDF file path。
            enhance_mode: 增强Mode (raw/standard/full)。

        Returns:
            EnhancedResult: contains BaseResult + 增强Data + Mutations。
        """
        t0 = time.time()

        logger.info(
            f"[DocMirror] Orchestrator ▶ "
            f"file={Path(file_path).name} | mode={enhance_mode}"
        )

        # ═══ Step 1: 核心Extract → BaseResult ═══
        base_result = await self.extractor.extract(file_path)

        # 检查ExtractResult有效性
        if not base_result.pages and not base_result.full_text:
            error_msg = base_result.metadata.get("error", "Empty extraction result")
            logger.warning(f"[DocMirror] Extraction failed: {error_msg}")
            result = EnhancedResult.from_base_result(base_result)
            result.status = "failed"
            result.add_error(error_msg)
            result.enhanced_data["enhance_mode"] = enhance_mode
            return result

        # ═══ Step 2: Initialize EnhancedResult ═══
        result = EnhancedResult.from_base_result(base_result)
        result.enhanced_data["enhance_mode"] = enhance_mode

        # ═══ Step 2.5: 策略自适应 (based on PreAnalyzer) ═══
        pre_analysis = base_result.metadata.get("pre_analysis", {})
        recommended = pre_analysis.get("recommended_strategy", "standard")
        strategy_params = pre_analysis.get("strategy_params", {})
        result.enhanced_data["pre_analysis"] = pre_analysis

        # fast 策略: Downgrade增强Mode
        effective_mode = enhance_mode
        if recommended == "fast" and enhance_mode == "full":
            effective_mode = "standard"
            logger.info("[DocMirror] PreAnalyzer: fast strategy → downgrade full→standard")
        # LLM Enable: 由 strategy_params 驱动
        if strategy_params.get("enable_llm", False):
            self.config.setdefault("SceneDetector", {})["enable_llm"] = True
            self.config.setdefault("Repairer", {})["enable_llm"] = True
            logger.info("[DocMirror] PreAnalyzer: deep strategy → enable LLM middlewares")

        # ═══ Step 3: 构建MiddlewarePipeline ═══
        if effective_mode == "raw":
            logger.info("[DocMirror] Raw mode — skipping middleware pipeline")
        else:
            middlewares = self._build_middlewares(effective_mode, file_type)
            result = self.pipeline.execute(middlewares, result)

        # ═══ Step 4: 设置最终Status ═══
        elapsed = (time.time() - t0) * 1000
        result.processing_time = elapsed

        # ═══ Step 4.5: Mutation Analyze (认知反馈闭环) ═══
        if result.mutations:
            try:
                from .middlewares.mutation_analyzer import MutationAnalyzer
                analyzer = MutationAnalyzer()
                analysis = analyzer.analyze(result.mutations)
                result.enhanced_data["mutation_analysis"] = analysis.to_dict()
            except Exception as e:
                logger.debug(f"[DocMirror] MutationAnalyzer error: {e}")

        # ensure table block 有内容
        if not base_result.table_blocks:
            if result.status == "success":
                result.status = "partial"
                result.add_error("No tables found in document")

        logger.info(
            f"[DocMirror] Orchestrator ◀ status={result.status} | "
            f"scene={result.scene} | "
            f"mutations={result.mutation_count} | "
            f"elapsed={elapsed:.0f}ms"
        )

        return result

    def _build_middlewares(
        self, enhance_mode: str, file_type: str = "pdf",
    ) -> List[BaseMiddleware]:
        """
        based onFormat + 增强Mode构建MiddlewareList。

        based onRegistryMode，新增Middleware只需:
          1. 在 MIDDLEWARE_REGISTRY 中Register
          2. 在 configs/pipeline_registry.py 中add到对应Format+ModeList
        """
        from ..configs.pipeline_registry import get_pipeline_config
        middleware_names = get_pipeline_config(file_type, enhance_mode)
        middlewares = []

        hints = None  # 惰性Load

        for name in middleware_names:
            cls = MIDDLEWARE_REGISTRY.get(name)
            if cls is None:
                logger.warning(f"[DocMirror] Unknown middleware: {name}")
                continue

            mw_config = self.config.get(name, {})

            # 特殊Processing: need to hints 注入的Middleware
            if name in _HINTS_CONSUMERS:
                if hints is None:
                    hints = _load_hints_cached()
                if hints:
                    mw_config["column_aliases"] = hints.get("column_aliases", {})
                    mw_config["hints"] = hints

            middlewares.append(cls(config=mw_config))

        return middlewares
