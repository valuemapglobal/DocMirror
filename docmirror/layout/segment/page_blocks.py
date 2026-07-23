# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""vNext geometric page segmentation.

Clusters OCR lines into blocks by y-gap, scores morphology (grid / field /
prose) from geometry, and emits region candidates without domain-specific regex.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from docmirror.ocr.local_structure.utils import bbox_of, line_items, text_of, union_bbox
from docmirror.ocr.micro_grid.models import OCRToken

_DEFAULT_BLOCK_GAP = 40.0
_MIN_BLOCK_LINES = 3


@dataclass(frozen=True)
class PageBlock:
    block_id: str
    page: int
    bbox: tuple[float, float, float, float]
    line_indices: tuple[int, ...]
    grid_score: float
    field_score: float
    predicted_kind: str
    score: float
    reason_codes: tuple[str, ...]
    anchor_text: str


def _tokens_in_bbox(
    tokens: Iterable[OCRToken],
    bbox: tuple[float, float, float, float],
    *,
    margin: float = 4.0,
) -> list[OCRToken]:
    x0, y0, x1, y1 = bbox
    out: list[OCRToken] = []
    for token in tokens:
        cx, cy = token.center
        if x0 - margin <= cx <= x1 + margin and y0 - margin <= cy <= y1 + margin:
            out.append(token)
    return out


def _cluster_rows(tokens: list[OCRToken], *, gap: float = 10.0) -> list[list[OCRToken]]:
    if not tokens:
        return []
    ordered = sorted(tokens, key=lambda t: (t.center[1], t.center[0]))
    rows: list[list[OCRToken]] = [[ordered[0]]]
    for token in ordered[1:]:
        prev_y = rows[-1][-1].center[1]
        if token.center[1] - prev_y > gap:
            rows.append([token])
        else:
            rows[-1].append(token)
    return rows


def _grid_morphology_score(
    block_lines: list[dict[str, Any]],
    tokens: list[OCRToken],
) -> tuple[float, tuple[str, ...]]:
    reasons: list[str] = []
    if len(tokens) < 8:
        return 0.0, tuple(reasons)
    rows = _cluster_rows(tokens)
    if len(rows) < 2:
        return 0.0, tuple(reasons)
    row_counts = [len(row) for row in rows]
    avg_count = sum(row_counts) / len(row_counts)
    if avg_count < 3.0:
        return 0.0, tuple(reasons)
    count_spread = max(row_counts) - min(row_counts)
    if count_spread > max(2, avg_count * 0.5):
        return 0.0, tuple(reasons)
    short_ratio = sum(1 for token in tokens if len(token.text.strip()) <= 3) / len(tokens)
    if short_ratio < 0.45:
        return 0.0, tuple(reasons)
    reasons.extend(["token_lattice", "short_token_density", "stable_row_width"])
    score = min(
        0.35 + 0.08 * min(len(rows), 8) + 0.25 * short_ratio + 0.05 * min(avg_count, 8),
        0.95,
    )
    if block_lines and len(block_lines[0]["text"]) <= 32:
        reasons.append("compact_header_line")
        score = min(score + 0.05, 0.95)
    return score, tuple(reasons)


def _line_two_column_hint(line: dict[str, Any], block_bbox: tuple[float, float, float, float]) -> bool:
    x0, _, x1, _ = line["bbox"]
    block_x0, _, block_x1, _ = block_bbox
    block_mid = (block_x0 + block_x1) / 2.0
    line_w = max(x1 - x0, 1e-6)
    if x0 - block_x0 > 24.0:
        return False
    if x1 <= block_mid:
        return False
    left_span = block_mid - x0
    return left_span / line_w <= 0.42


def _paired_row_two_column(
    block_lines: list[dict[str, Any]],
    index: int,
    block_bbox: tuple[float, float, float, float],
) -> bool:
    if index + 1 >= len(block_lines):
        return False
    left = block_lines[index]
    right = block_lines[index + 1]
    ly0, ry0 = left["bbox"][1], right["bbox"][1]
    if abs(ly0 - ry0) > 10.0:
        return False
    if left["bbox"][2] > right["bbox"][0] + 6.0:
        return False
    if left["bbox"][0] - block_bbox[0] > 24.0:
        return False
    if right["bbox"][2] - left["bbox"][2] < 20.0:
        return False
    return True


def _field_morphology_score(
    block_lines: list[dict[str, Any]],
    block_bbox: tuple[float, float, float, float],
) -> tuple[float, tuple[str, ...]]:
    if len(block_lines) < _MIN_BLOCK_LINES:
        return 0.0, ()
    left_edges = [line["bbox"][0] for line in block_lines]
    left_spread = max(left_edges) - min(left_edges)
    two_col_rows = sum(1 for line in block_lines if _line_two_column_hint(line, block_bbox))
    paired_rows = sum(1 for idx in range(len(block_lines)) if _paired_row_two_column(block_lines, idx, block_bbox))
    layout_rows = two_col_rows + paired_rows
    if layout_rows < 2:
        return 0.0, ()
    reasons = ["two_column_rows", "left_edge_cluster"]
    if paired_rows >= 2:
        reasons.append("label_value_row_pairs")
    score = min(0.40 + 0.10 * layout_rows + (0.10 if left_spread <= 18.0 else 0.0), 0.92)
    if left_spread <= 12.0:
        reasons.append("tight_label_column")
        score = min(score + 0.05, 0.92)
    return score, tuple(reasons)


def cluster_line_blocks(
    items: list[dict[str, Any]],
    *,
    gap_threshold: float = _DEFAULT_BLOCK_GAP,
) -> list[list[dict[str, Any]]]:
    if not items:
        return []
    blocks: list[list[dict[str, Any]]] = [[items[0]]]
    for line in items[1:]:
        prev = blocks[-1][-1]
        gap = line["bbox"][1] - prev["bbox"][3]
        if gap > gap_threshold:
            blocks.append([line])
        else:
            blocks[-1].append(line)
    return blocks


def segment_page_blocks(
    lines: Iterable[Any],
    *,
    tokens: Iterable[OCRToken] | None = None,
    page: int,
    page_width: float | None = None,
    page_height: float | None = None,
    gap_threshold: float = _DEFAULT_BLOCK_GAP,
) -> list[PageBlock]:
    """Segment a page into geometric blocks with morphology scores."""
    del page_width
    del page_height
    items = line_items(lines, page=page)
    token_list = list(tokens or [])
    blocks: list[PageBlock] = []
    for block_idx, block_lines in enumerate(cluster_line_blocks(items, gap_threshold=gap_threshold)):
        if len(block_lines) < _MIN_BLOCK_LINES:
            continue
        block_bbox = union_bbox(line["bbox"] for line in block_lines)
        block_tokens = _tokens_in_bbox(token_list, block_bbox)
        grid_score, grid_reasons = _grid_morphology_score(block_lines, block_tokens)
        field_score, field_reasons = _field_morphology_score(block_lines, block_bbox)
        if max(grid_score, field_score) < 0.45:
            continue
        if grid_score >= field_score:
            predicted_kind = "micro_grid"
            score = grid_score
            reason_codes = grid_reasons
        else:
            predicted_kind = "field_grid"
            score = field_score
            reason_codes = field_reasons
        line_indices = tuple(line["idx"] for line in block_lines)
        blocks.append(
            PageBlock(
                block_id=f"blk_p{page}_{block_idx}",
                page=page,
                bbox=block_bbox,
                line_indices=line_indices,
                grid_score=grid_score,
                field_score=field_score,
                predicted_kind=predicted_kind,
                score=score,
                reason_codes=reason_codes,
                anchor_text=block_lines[0]["text"],
            )
        )
    return blocks


def lines_to_synthetic_tokens(lines: Iterable[Any], *, page: int) -> list[OCRToken]:
    """Split line text into pseudo-tokens for morphology scoring in tests."""
    tokens: list[OCRToken] = []
    token_idx = 0
    for line_idx, line in enumerate(lines or []):
        bbox = bbox_of(line)
        text = text_of(line)
        if bbox is None or not text:
            continue
        parts = [part for part in text.replace("　", " ").split() if part]
        if len(parts) <= 1:
            parts = list(text)
        x0, y0, x1, y1 = bbox
        line_w = max(x1 - x0, 1.0)
        slot_w = line_w / max(len(parts), 1)
        for part_idx, part in enumerate(parts):
            tx0 = x0 + part_idx * slot_w
            tx1 = tx0 + max(slot_w * 0.9, 1.0)
            tokens.append(
                OCRToken(
                    token_id=f"syn_p{page}_l{line_idx}_t{token_idx}",
                    text=part,
                    bbox=(tx0, y0, min(tx1, x1), y1),
                    confidence=1.0,
                    page=page,
                )
            )
            token_idx += 1
    return tokens
