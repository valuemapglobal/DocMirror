# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Strategy registry — registers and resolves extraction strategies by name.

Purpose: Plugin-style registry mapping profile/strategy names to
``BaseExtractionStrategy`` implementations.

Main components: ``BaseExtractionStrategy``, ``register_strategy``,
``get_strategy``.

Upstream: Strategy modules at import time.

Downstream: ``CoreExtractor``, ``extraction.strategies.section_driven``.
"""

from __future__ import annotations

import contextvars
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)

_bypass_content_type: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "strategy_bypass_content_type",
    default=None,
)


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
    if content_type and content_type == _bypass_content_type.get():
        return None
    cls = _REGISTRY.get(content_type)
    if cls is not None:
        return cls()
    return None
