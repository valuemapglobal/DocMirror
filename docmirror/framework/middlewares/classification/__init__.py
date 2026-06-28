# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Classification middleware package — evidence engine re-export.

Re-exports ``EvidenceEngine`` from ``docmirror.structure.scene`` so the middleware
execution profile (MEP) catalog can discover the 120-type classification
entry point. See ``middleware_catalog.yaml`` for pipeline ordering.
"""

from docmirror.structure.scene.evidence_engine import EvidenceEngine

__all__ = ["EvidenceEngine"]
