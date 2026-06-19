# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror: Universal Document Parsing Engine

Directory structure:
- core/: Core extraction engines (CoreExtractor, LayoutAnalysis, TableExtraction)
- models/: Data models (ParseResult MOC, DomainExtractionResult DEC)
- middlewares/: Middleware pipeline (EvidenceEngine, EntityExtractor, Validator, ...)
- configs/: YAML configs (FCR, enhancement profiles, scene keywords) + loaders
- framework/: Pipeline orchestration (dispatcher, extraction_runner, orchestrator)
- di/: Service container (shared dispatcher / orchestrator singletons)
- adapters/: Format adapters (PDF, Image, Office, Email, Web)
- plugins/: Domain plugins (bank_statement, ...)

Single public entry point: perceive_document()
"""

__version__ = "2.0.0"
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

logger = logging.getLogger(__name__)

_EXPORTS = {
    "perceive_document": ("docmirror.core.entry.factory", "perceive_document"),
    "PerceiveResult": ("docmirror.core.entry.perceive_result", "PerceiveResult"),
    "PerceptionFactory": ("docmirror.core.entry.factory", "PerceptionFactory"),
    "ParseResult": ("docmirror.models.entities.parse_result", "ParseResult"),
    "ParseResultBridge": ("docmirror.models.construction.parse_result_bridge", "ParseResultBridge"),
    "DomainExtractionResult": ("docmirror.models.entities.domain_result", "DomainExtractionResult"),
    "ParserDispatcher": ("docmirror.framework.dispatcher", "ParserDispatcher"),
    "Orchestrator": ("docmirror.framework.orchestrator", "Orchestrator"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "perceive_document",
    "PerceiveResult",
    "PerceptionFactory",
    "ParseResult",
    "ParseResultBridge",
    "DomainExtractionResult",
    "ParserDispatcher",
    "Orchestrator",
]
