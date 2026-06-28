# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scanned local structure restoration from OCR geometry."""

from docmirror.structure.ocr.local_structure.build import build_local_structures, extract_local_structure_evidence
from docmirror.structure.ocr.local_structure.detect import detect_local_structure_candidates
from docmirror.structure.ocr.local_structure.models import (
    LocalStructure,
    LocalStructureCandidate,
    StructureEdge,
    StructureNode,
)
from docmirror.structure.ocr.local_structure.repair import RegionRecognition, recognize_structure_region_from_image

__all__ = [
    "LocalStructure",
    "LocalStructureCandidate",
    "RegionRecognition",
    "StructureEdge",
    "StructureNode",
    "build_local_structures",
    "detect_local_structure_candidates",
    "extract_local_structure_evidence",
    "recognize_structure_region_from_image",
]
