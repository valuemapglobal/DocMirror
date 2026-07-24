# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""DocMirror public API.

DocMirror is the Commercial Document Trust Layer: Parse. Prove. Trust.

The package import is intentionally light. Optional engines such as OCR,
PDF rendering, layout models, server integrations, and AI backends are loaded
only when their feature paths are invoked.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "1.1.2"
__author__ = "Adam Lin <adamlin@valuemapglobal.com>"
__copyright__ = "Copyright 2026, ValueMap Global"
__license__ = "Apache 2.0"

if TYPE_CHECKING:  # pragma: no cover
    from docmirror.models.entities.domain_result import DomainExtractionResult
    from docmirror.models.entities.parse_result import ParseResult


async def perceive_document(*args: Any, **kwargs: Any) -> Any:
    """Parse a document into the canonical runtime ``ParseResult``.

    The implementation is imported lazily so ``import docmirror`` remains fast,
    quiet, and usable with the base package installation.
    """
    from docmirror.input.pipeline import perceive_document as _perceive_document

    return await _perceive_document(*args, **kwargs)


def __getattr__(name: str) -> Any:
    """Lazy access for stable top-level model exports."""
    if name == "ParseResult":
        from docmirror.models.entities.parse_result import ParseResult

        return ParseResult
    if name == "DomainExtractionResult":
        from docmirror.models.entities.domain_result import DomainExtractionResult

        return DomainExtractionResult
    raise AttributeError(f"module 'docmirror' has no attribute {name!r}")


__all__ = [
    "perceive_document",
    "ParseResult",
    "DomainExtractionResult",
]
