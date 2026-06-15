# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Entity domain models — public MOC and DEC exports.

Re-exports the core typed entities used throughout DocMirror:

    ParseResult              Unified parser output contract (MOC)
    DomainExtractionResult   Domain plugin output protocol (DEC)
    BaseResult, Block, PageLayout, Style, TextSpan   Physical layout models

Import from this subpackage for stable public API access without reaching
into individual module files.
"""

from .domain import BaseResult, Block, PageLayout, Style, TextSpan
from .domain_result import DomainExtractionResult
from .parse_result import ParseResult

__all__ = [
    "Style",
    "TextSpan",
    "Block",
    "PageLayout",
    "BaseResult",
    "DomainExtractionResult",
    "ParseResult",
]
