# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Extraction middleware package — generic entity and header enrichment stages.
"""

from .generic_entity_extractor import GenericEntityExtractor

# SLMEntityExtractor removed in v1.1 — superseded by LlmDocumentRestorer

__all__ = ["GenericEntityExtractor"]
