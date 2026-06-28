# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scanned micro-grid reconstruction from OCR geometry."""

from docmirror.ocr.micro_grid.cell_recognition import CellRecognition, normalize_allowlist_text
from docmirror.ocr.micro_grid.detect import detect_micro_grid_candidates
from docmirror.ocr.micro_grid.materialize import extract_micro_grid_structures, register_micro_grid_materializer
from docmirror.ocr.micro_grid.models import MicroGrid, MicroGridCandidate, MicroGridCell, OCRToken

__all__ = [
    "CellRecognition",
    "MicroGrid",
    "MicroGridCandidate",
    "MicroGridCell",
    "OCRToken",
    "detect_micro_grid_candidates",
    "extract_micro_grid_structures",
    "normalize_allowlist_text",
    "register_micro_grid_materializer",
]
