# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror: Universal Document Parsing Engine

Directory structure:
- core/: Core extraction engines (CoreExtractor, LayoutAnalysis, TableExtraction)
- models/: Data models (BaseResult, EnhancedResult, PerceptionResult)
- middlewares/: Middleware pipeline (SceneDetector, EntityExtractor, Validator, ...)
- configs/: Configuration (settings, pipeline_registry, institution_registry)
- framework/: Pipeline orchestration (dispatcher, orchestrator, cache)
- adapters/: Format adapters (PDF, Image, Office, Email, Web)
- plugins/: Domain plugins (bank_statement, ...)

Single public entry point: perceive_document()
"""

__version__ = "0.3.0"
__author__ = "Adam Lin <adamlin@valuemapglobal.com>"
__copyright__ = "Copyright 2026, ValueMap Global"
__license__ = "Apache 2.0"

import logging
import sys

# Configure root logger with millisecond precision, process/thread IDs, and source context
logging.basicConfig(
    format="%(asctime)s.%(msecs)03d - [%(levelname)s] [%(process)d:%(threadName)s] %(name)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    stream=sys.stdout,
)

from docmirror.core.factory import perceive_document, PerceptionFactory
from docmirror.models.entities.document_types import DocumentType
from docmirror.models.entities.perception_result import PerceptionResult
from docmirror.models.entities.domain_models import DomainData
from docmirror.framework.dispatcher import ParserDispatcher
from docmirror.framework.dispatcher import ParserDispatcher as DocumentProcessingOrchestrator  # compat
from docmirror.framework.base import ParserOutput
from docmirror.framework.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# backward-compat alias — callers importing PerceptionResponse get ParserOutput
PerceptionResponse = ParserOutput


__all__ = [
    "perceive_document",
    "PerceptionFactory",
    "PerceptionResult",
    "PerceptionResponse",
    "DocumentType",
    "DomainData",
    "ParserDispatcher",
    "DocumentProcessingOrchestrator",
    "ParserOutput",
    "Orchestrator",
]