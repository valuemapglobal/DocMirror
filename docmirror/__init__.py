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

__version__ = "1.0.0"
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

# ── Light deps: static import (always loaded, statically traceable) ──
from docmirror.models.entities.parse_result import ParseResult  # noqa: E402
from docmirror.models.entities.domain_result import DomainExtractionResult  # noqa: E402

async def perceive_document(*args, **kwargs):
    """Parse a document -> PerceiveResult.

    Deferred wrapper around ``docmirror.input.pipeline.perceive_document``.
    All positional/keyword arguments are forwarded as-is.
    """
    from docmirror.input.pipeline import perceive_document as _pd
    return await _pd(*args, **kwargs)

__all__ = [
    "perceive_document",
    "ParseResult",
    "DomainExtractionResult",
]
