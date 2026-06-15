# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
EPO and layout configuration models — extraction orchestration profiles.

Pydantic models for document layout and extraction profiles used by the
Extraction Profile Orchestrator (EPO). These are configuration-side models
(not Mirror Object Contract entities); runtime copies are re-exported from
``docmirror.models.entities`` for convenience.

Exports::

    LayoutProfile / LayoutProfileMatchRules / InstitutionVariant
    ExtractionProfile / SegmentationMode

Profiles are loaded from ``layout_profiles.yaml`` and drive table method
selection, column anchors, institution variants, and segmentation strategy
without hardcoding layout logic in ``CoreExtractor``.
"""

from docmirror.configs.models.extraction_profile import ExtractionProfile, SegmentationMode
from docmirror.configs.models.layout_profile import (
    InstitutionVariant,
    LayoutProfile,
    LayoutProfileMatchRules,
)

__all__ = [
    "LayoutProfile",
    "LayoutProfileMatchRules",
    "InstitutionVariant",
    "ExtractionProfile",
    "SegmentationMode",
]
