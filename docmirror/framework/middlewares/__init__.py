# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Mirror-layer middleware pipeline package (MEP).

Re-exports ``BaseMiddleware``, ``MiddlewarePipeline``, and the default
detection, extraction, and validation middleware classes wired into standard
parse profiles. Middleware runs after format adapters via the ``Orchestrator``
and enriches ``ParseResult`` in place.
"""

from .base import BaseMiddleware, MiddlewarePipeline
from .detection.institution_detector import InstitutionDetector
from .detection.language_detector import LanguageDetector
from .extraction.entity_extractor import EntityExtractor
from .extraction.generic_entity_extractor import GenericEntityExtractor

# SLMEntityExtractor removed in v1.1 — superseded by LlmDocumentRestorer
from .validation.mutation_analyzer import MutationAnalyzer
from .validation.validator import Validator

__all__ = [
    "BaseMiddleware",
    "MiddlewarePipeline",
    "InstitutionDetector",
    "LanguageDetector",
    "EntityExtractor",
    "GenericEntityExtractor",
    # "SLMEntityExtractor",  # removed in v1.1
    "Validator",
    "MutationAnalyzer",
]
