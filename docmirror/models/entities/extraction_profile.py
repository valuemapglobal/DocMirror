# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
ExtractionProfile re-export shim — configuration models at the entities boundary.

Re-exports ``ExtractionProfile`` and ``SegmentationMode`` from
``docmirror.configs.models.extraction_profile`` so EPO-aware code can import
profile types from the models package without a direct configs dependency
in higher-level contracts.

Canonical SSOT: ``docmirror.configs.models.extraction_profile``.
"""

from docmirror.configs.models.extraction_profile import ExtractionProfile, SegmentationMode

__all__ = ["ExtractionProfile", "SegmentationMode"]
