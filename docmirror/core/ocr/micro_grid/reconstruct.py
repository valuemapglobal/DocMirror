# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic geometry helpers for local scanned micro-grid reconstruction.

Implementation lives in ``docmirror.core.ocr.field_grid``; this module re-exports
for backward compatibility with SMG callers.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from docmirror.core.ocr.field_grid.assign import (
    assign_tokens,
    assign_tokens_to_col_bands,
    assignment_confidence,
    assignment_method,
    cell_bbox,
    equal_col_bands,
)
from docmirror.core.ocr.field_grid.geometry import (
    bbox_area,
    bbox_intersection,
    bbox_iou,
    bbox_overlap_ratio,
)
from docmirror.core.ocr.field_grid.tokens import (
    dedupe_visual_tokens,
    expand_tokens_to_char_tokens,
    split_token_to_char_tokens,
)
from docmirror.core.ocr.micro_grid.models import MicroGridCell, OCRToken


def build_cell(
    *,
    row_band: dict[str, Any],
    col_band: dict[str, Any],
    tokens: Iterable[OCRToken],
    text: str,
    role: str,
    crop_ocr_text: str | None = None,
    recognition_source: str = "tokens",
    recognition_audit: dict[str, Any] | None = None,
) -> MicroGridCell:
    token_list = list(tokens)
    assign_conf = assignment_confidence(token_list, row_band, col_band)
    method = assignment_method(token_list)
    return MicroGridCell(
        row_index=int(row_band["index"]),
        col_index=int(col_band["index"]),
        bbox=cell_bbox(row_band, col_band),
        text=text,
        confidence=max((t.confidence for t in token_list), default=0.0),
        geometry_status="exact" if text and method == "overlap:native_token" else ("estimated" if text else "empty"),
        token_ids=tuple(t.token_id for t in token_list),
        assignment_confidence=assign_conf,
        assignment_method=method,
        crop_ocr_text=crop_ocr_text,
        recognition_source=recognition_source,
        recognition_audit=recognition_audit or {},
        role=role,
    )


__all__ = [
    "assign_tokens",
    "assign_tokens_to_col_bands",
    "assignment_confidence",
    "assignment_method",
    "bbox_area",
    "bbox_intersection",
    "bbox_iou",
    "bbox_overlap_ratio",
    "build_cell",
    "cell_bbox",
    "dedupe_visual_tokens",
    "equal_col_bands",
    "expand_tokens_to_char_tokens",
    "split_token_to_char_tokens",
]
