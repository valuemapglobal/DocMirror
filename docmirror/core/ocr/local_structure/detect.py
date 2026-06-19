# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic candidate detection for scanned local structures."""

from __future__ import annotations

import re
from typing import Any, Iterable

from docmirror.core.ocr.local_structure.models import LocalStructureCandidate
from docmirror.core.ocr.local_structure.utils import line_items, union_bbox
from docmirror.core.ocr.micro_grid.models import OCRToken

_NUMBERED_HEADING_RE = re.compile(r"^[^\W\d_]{1,8}\s*\d{1,3}$", re.UNICODE)
_LABEL_LIKE_RE = re.compile(r"(机构|标识|日期|币种|金额|种类|方式|状态|编号|名称|期限|频率|责任|类型|余额|用途|利率)")


def _is_numbered_heading(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text)
    return bool(_NUMBERED_HEADING_RE.match(normalized))


def _label_like_score(lines: list[dict[str, Any]]) -> int:
    return sum(1 for line in lines if _LABEL_LIKE_RE.search(line["text"]))


def _field_grid_likelihood(block_lines: list[dict[str, Any]]) -> float:
    label_rows = sum(1 for line in block_lines if _LABEL_LIKE_RE.search(line["text"]))
    if label_rows < 2:
        return 0.0
    return min(0.35 + 0.12 * label_rows, 0.85)


def _block_end_index(items: list[dict[str, Any]], start_idx: int, anchor_indices: list[int], seq: int) -> int:
    if seq + 1 < len(anchor_indices):
        return anchor_indices[seq + 1]
    start_y = items[start_idx]["bbox"][1]
    end = start_idx + 1
    large_gap = 48.0
    while end < len(items):
        if end > start_idx + 24:
            break
        prev = items[end - 1]["bbox"]
        curr = items[end]["bbox"]
        y_gap = curr[1] - prev[3]
        if y_gap > large_gap and end > start_idx + 4:
            break
        if _is_numbered_heading(items[end]["text"]) and end > start_idx + 2:
            break
        end += 1
    return min(len(items), max(end, start_idx + 3))


def detect_local_structure_candidates(
    lines: Iterable[Any],
    *,
    tokens: Iterable[OCRToken] | None = None,
    page: int,
    page_width: float | None = None,
    page_height: float | None = None,
) -> list[LocalStructureCandidate]:
    """Detect local label/value structure regions from OCR evidence."""
    del tokens
    del page_width
    del page_height
    items = line_items(lines, page=page)
    if not items:
        return []

    anchor_indices = [idx for idx, line in enumerate(items) if _is_numbered_heading(line["text"])]
    candidates: list[LocalStructureCandidate] = []
    for seq, start_idx in enumerate(anchor_indices):
        end_idx = _block_end_index(items, start_idx, anchor_indices, seq)
        block_lines = items[start_idx:end_idx]
        if len(block_lines) < 3:
            continue
        label_score = _label_like_score(block_lines)
        if label_score < 2:
            continue
        fg_score = _field_grid_likelihood(block_lines)
        score = min(0.45 + 0.08 * label_score + 0.02 * min(len(block_lines), 8) + fg_score * 0.15, 0.95)
        reasons = ["block_heading_numbered", "label_value_density"]
        if fg_score >= 0.5:
            reasons.append("field_grid_likely")
        if end_idx < len(items):
            reasons.append("next_block_boundary")
        candidates.append(
            LocalStructureCandidate(
                candidate_id=f"lscand_p{page}_{seq}",
                page=page,
                bbox=union_bbox(line["bbox"] for line in block_lines),
                anchors=(block_lines[0]["text"],),
                reason_codes=tuple(reasons),
                score=score,
                source_line_ids=tuple(line["line_id"] for line in block_lines),
            )
        )

    return sorted(candidates, key=lambda c: (c.bbox[1], c.bbox[0]))
