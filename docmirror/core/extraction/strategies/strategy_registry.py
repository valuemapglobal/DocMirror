# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Strategy Registry
=================

Routes ``content_type`` → optimal extraction strategy.

Architecture:
    PreAnalyzer detects structural content_type
    → Registry resolves matching strategy (or None → generic pipeline)
    → Strategy.extract() returns standard 6-tuple

Usage::

    from .strategy_registry import get_strategy

    strategy = get_strategy(pre_analysis.content_type)
    if strategy is not None:
        return strategy.extract(fitz_doc, pre_analysis)
    # else: fall through to generic pipeline
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseExtractionStrategy(ABC):
    """
    Base class for all extraction strategies.

    Each strategy must implement ``extract()`` returning the same
    6-tuple as ``CoreExtractor._process_pdf_sync()``:

        (pages, full_text, extraction_layer, extraction_confidence, _perf, _page_perf)
    """

    @abstractmethod
    def extract(
        self,
        fitz_doc: Any,
        pre_analysis: Any,
    ) -> tuple:
        """
        Execute extraction using strategy-specific logic.

        Args:
            fitz_doc: Opened PyMuPDF document.
            pre_analysis: PreAnalysisResult from PreAnalyzer.

        Returns:
            6-tuple compatible with _process_pdf_sync output:
            (pages, full_text, extraction_layer, extraction_confidence, _perf, _page_perf)
        """
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# Global Registry
# ═══════════════════════════════════════════════════════════════════════════════

_REGISTRY: dict[str, type[BaseExtractionStrategy]] = {}


def register_strategy(content_type: str):
    """
    Decorator: register a strategy class for a content_type.

    Example::

        @register_strategy("section_dominant")
        class SectionDrivenStrategy(BaseExtractionStrategy):
            ...
    """

    def decorator(cls: type[BaseExtractionStrategy]):
        _REGISTRY[content_type] = cls
        logger.debug(f"[StrategyRegistry] Registered {cls.__name__} for content_type={content_type}")
        return cls

    return decorator


def get_strategy(content_type: str) -> Optional[BaseExtractionStrategy]:
    """
    Look up a registered strategy for the given content_type.

    Returns:
        Strategy instance if registered, None otherwise.
        None means the caller should fall through to the generic pipeline.
    """
    cls = _REGISTRY.get(content_type)
    if cls is not None:
        return cls()
    return None
