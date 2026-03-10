"""
PDF Adapter — PDF → PerceptionResult

主Path: Orchestrator → EnhancedResult → PerceptionResultBuilder (一步直达)。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from docmirror.framework.base import BaseParser, ParserOutput
from docmirror.models.domain import BaseResult

logger = logging.getLogger(__name__)

# ── Orchestrator Singleton ──
_orchestrator = None

def _get_shared_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        from docmirror.framework.orchestrator import Orchestrator
        _orchestrator = Orchestrator()
    return _orchestrator


class PDFAdapter(BaseParser):
    """
    PDF Format adapter。

    viaShared Orchestrator SingletonComplete全流程，
    using PerceptionResultBuilder 一步生成 PerceptionResult。
    """

    def __init__(self, enhance_mode: str = "standard", **kwargs):
        self._enhance_mode = enhance_mode

    async def to_base_result(self, file_path: Path, **kwargs) -> BaseResult:
        """PDF → BaseResult (仅核心Extract, 不走Middleware)。"""
        from docmirror.core.extractor import CoreExtractor
        extractor = CoreExtractor()
        return await extractor.extract(file_path)

    async def perceive(self, file_path: Path, **context):
        """PDF → PerceptionResult (完整Pipeline, 一步直达)。"""
        from docmirror.models.builder import PerceptionResultBuilder

        orchestrator = _get_shared_orchestrator()
        enhanced = await orchestrator.run_pipeline(
            file_path=file_path,
            enhance_mode=self._enhance_mode,
        )

        return PerceptionResultBuilder.build(
            enhanced.base_result,
            enhanced=enhanced,
            **context,
        )

    async def parse(self, file_path: Path, **kwargs) -> ParserOutput:
        """[DEPRECATED] retain旧Interface兼容。"""
        orchestrator = _get_shared_orchestrator()
        enhanced = await orchestrator.run_pipeline(
            file_path=file_path,
            enhance_mode=self._enhance_mode,
            **kwargs,
        )
        output = enhanced.to_parser_output()
        output._enhanced = enhanced
        return output


