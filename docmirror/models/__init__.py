# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror Models — Mirror Object Contract (MOC) + Domain Extraction Contract (DEC).

See ``docs/design/09_models_layer_first_principles_redesign.md``.
"""

from .entities.domain import BaseResult, Block, PageLayout, Style, TextSpan
from .entities.domain_result import DomainExtractionResult
from .entities.parse_result import ParseResult
from .tracking.mutation import Mutation

__all__ = [
    "Style",
    "TextSpan",
    "Block",
    "PageLayout",
    "BaseResult",
    "Mutation",
    "ParseResult",
    "DomainExtractionResult",
]
