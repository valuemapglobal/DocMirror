"""
MultiModal: Perception Hub (Unified API)

Refactored directory structure:
- core/: Core extraction engines (CoreExtractor, Foundation, LayoutAnalysis, TableExtraction)
- models/: Data models (BaseResult, EnhancedResult, Mutation)
- middlewares/: Middleware pipeline (SceneDetector, ColumnMapper, Validator, Repairer, ...)
- configs/: Configuration (settings, hints.yaml, institution_registry.yaml)
- orchestrator.py: Full pipeline orchestrator
- engines/: Vision LLM (Qwen-VL), OCR, Seal detection
- schemas/: External data contracts (PerceptionResult, DocumentType)
- dispatcher.py: L0 file type routing
- base.py: ParserOutput + BaseParser base classes
- adapters/: Format adapters (PDF, Image, Office, Email, Web)

Single public entry point: perceive_document()
"""

import logging
import warnings
from pathlib import Path
from typing import Literal, Optional

from docmirror.core.factory import perceive_document, PerceptionFactory
from docmirror.models.document_types import DocumentType
from docmirror.models.perception_result import PerceptionResult
from docmirror.models.domain_models import DomainData
from docmirror.framework.dispatcher import ParserDispatcher
from docmirror.framework.dispatcher import ParserDispatcher as DocumentProcessingOrchestrator  # compat
from docmirror.framework.base import ParserOutput
from docmirror.framework.orchestrator import Orchestrator
from docmirror.models.enhanced import EnhancedResult

logger = logging.getLogger(__name__)

# backward-compat alias — callers importing PerceptionResponse get ParserOutput
PerceptionResponse = ParserOutput


async def parse_pdf_v2(
    file_path,
    enhance_mode: Literal["raw", "standard", "full"] = "standard",
    **kwargs,
) -> EnhancedResult:
    """
    [DEPRECATED] Use perceive_document() as the sole entry point.

    Kept for backward compatibility only. Internally delegates to perceive_document.
    """
    warnings.warn(
        "parse_pdf_v2() is deprecated, use perceive_document() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    result = await perceive_document(file_path, DocumentType.OTHER)
    # Return EnhancedResult for legacy caller compatibility
    if hasattr(result, '_enhanced') and result._enhanced is not None:
        return result._enhanced
    # If no _enhanced (non-PDF path), construct minimal EnhancedResult
    from docmirror.models.domain import BaseResult
    base = BaseResult(document_id=str(file_path), full_text=result.content.text, pages=(), metadata={})
    return EnhancedResult.from_base_result(base)


__all__ = [
    "perceive_document",
    "PerceptionFactory",
    "PerceptionResult",
    "PerceptionResponse",
    "DocumentType",
    "DomainData",
    "DocumentProcessingOrchestrator",
    "ParserOutput",
    "Orchestrator",
    "parse_pdf_v2",
]

