# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Field Grid Reconstruction (FGR) — shared geometry kernel for SMG and SLSR."""

from docmirror.structure.ocr.field_grid.assign import (
    assign_tokens,
    assign_tokens_to_col_bands,
    assignment_confidence,
    assignment_method,
    cell_bbox,
    equal_col_bands,
)
from docmirror.structure.ocr.field_grid.geometry import (
    bbox_area,
    bbox_intersection,
    bbox_iou,
    bbox_overlap_ratio,
)
from docmirror.structure.ocr.field_grid.models import FieldCell, LabelToken
from docmirror.structure.ocr.field_grid.tokens import (
    dedupe_visual_tokens,
    expand_tokens_to_char_tokens,
    split_token_to_char_tokens,
)

__all__ = [
    "FieldCell",
    "LabelToken",
    "assign_tokens",
    "assign_tokens_to_col_bands",
    "assignment_confidence",
    "assignment_method",
    "bbox_area",
    "bbox_intersection",
    "bbox_iou",
    "bbox_overlap_ratio",
    "cell_bbox",
    "dedupe_visual_tokens",
    "equal_col_bands",
    "expand_tokens_to_char_tokens",
    "split_token_to_char_tokens",
]
