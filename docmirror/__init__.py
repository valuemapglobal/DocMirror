# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror: Universal Document Parsing Engine

Directory structure:
- input/: File intake, adapters, parse controls, and extraction intake.
- structure/: Evidence plane, page topology, OCR, tables, graph, and verification.
- output/: Canonical mirror JSON, projections, exporters, and serialization.
- models/: Shared contracts and typed data models.
- framework/: Orchestration, dispatch, dependency injection, and middleware framework.
- runtime/: Execution state, progress, artifacts, scheduling, and checkpoints.
- plugins/: Domain plugins plus internal plugin runtime.
- configs/: Config loaders and packaged YAML/JSON schemas.
- evidence/, quality/, security/: Cross-cutting ledgers, gates, and safety controls.
- cli/, server/, sdk/: User-facing execution boundaries.

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
