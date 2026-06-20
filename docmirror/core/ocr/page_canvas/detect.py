# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Merge SMG + SLSR region candidates for a single page canvas."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from docmirror.core.ocr.local_structure.detect import detect_local_structure_candidates
from docmirror.core.ocr.micro_grid.detect import detect_micro_grid_candidates
from docmirror.core.ocr.micro_grid.models import OCRToken
from docmirror.core.ocr.page_canvas.page_segment import segment_page_blocks


@dataclass(frozen=True)
class RegionCandidate:
    candidate_id: str
    page: int
    kind: str
    bbox: tuple[float, float, float, float]
    anchors: tuple[str, ...]
    score: float
    reason_codes: tuple[str, ...] = ()


def _bbox(obj: Any) -> tuple[float, float, float, float] | None:
    raw = obj.get("bbox") if isinstance(obj, dict) else getattr(obj, "bbox", None)
    if raw and len(raw) == 4:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    return None


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _anchor_key(anchors: Iterable[str]) -> str:
    return " ".join(sorted(str(a).strip() for a in anchors if str(a).strip()))


def detect_page_region_candidates(
    lines: Iterable[Any],
    *,
    tokens: Iterable[OCRToken] | None = None,
    page: int,
    page_width: float | None = None,
    page_height: float | None = None,
) -> list[RegionCandidate]:
    """Run geometric segmenter + legacy SMG/SLSR detectors (Design 19 §4.4 / P1)."""
    token_list = list(tokens or [])
    segmented_blocks = segment_page_blocks(
        lines,
        tokens=token_list,
        page=page,
        page_width=page_width,
        page_height=page_height,
    )
    micro = detect_micro_grid_candidates(
        token_list,
        lines=lines,
        page=page,
        page_width=page_width,
        page_height=page_height,
    )
    local = detect_local_structure_candidates(
        lines,
        tokens=token_list,
        page=page,
        page_width=page_width,
        page_height=page_height,
    )

    merged: list[RegionCandidate] = []
    for block in segmented_blocks:
        merged.append(
            RegionCandidate(
                candidate_id=block.block_id,
                page=block.page,
                kind=block.predicted_kind,
                bbox=block.bbox,
                anchors=(block.anchor_text,),
                score=block.score,
                reason_codes=block.reason_codes,
            )
        )
    for cand in micro:
        merged.append(
            RegionCandidate(
                candidate_id=cand.candidate_id,
                page=cand.page,
                kind="micro_grid",
                bbox=cand.bbox,
                anchors=cand.anchors,
                score=cand.score,
                reason_codes=cand.reason_codes,
            )
        )
    for cand in local:
        merged.append(
            RegionCandidate(
                candidate_id=cand.candidate_id,
                page=cand.page,
                kind="field_grid",
                bbox=cand.bbox,
                anchors=cand.anchors,
                score=cand.score,
                reason_codes=cand.reason_codes,
            )
        )

    merged.sort(key=lambda c: (-c.score, c.bbox[1], c.bbox[0]))
    kept: list[RegionCandidate] = []
    for cand in merged:
        duplicate = False
        for existing in kept:
            if _anchor_key(existing.anchors) and _anchor_key(existing.anchors) == _anchor_key(cand.anchors):
                if cand.score <= existing.score:
                    duplicate = True
                    break
                kept.remove(existing)
                break
            if existing.kind != cand.kind and _iou(existing.bbox, cand.bbox) > 0.5:
                continue
        if not duplicate:
            kept.append(cand)
    kept.sort(key=lambda c: (c.bbox[1], c.bbox[0]))
    return kept


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = bbox
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def annotate_region_nested_in_audit(regions: list[Any]) -> None:
    """Mark smaller overlapping regions with audit.nested_in (Design 19 §4.4)."""
    for i, nested in enumerate(regions):
        nested_bbox = tuple(nested.bbox)
        nested_area = _bbox_area(nested_bbox)
        for j, parent in enumerate(regions):
            if i == j:
                continue
            parent_bbox = tuple(parent.bbox)
            if _iou(nested_bbox, parent_bbox) <= 0.5:
                continue
            if nested_area >= _bbox_area(parent_bbox):
                continue
            nested.audit = dict(nested.audit)
            nested.audit["nested_in"] = parent.region_id
            break


def annotate_regions_with_detect_candidates(
    regions: list[Any],
    candidates: list[RegionCandidate],
) -> None:
    """Attach detect candidate cross-check metadata and nested_in audit."""
    for region in regions:
        region_bbox = tuple(region.bbox)
        matched: list[str] = []
        for cand in candidates:
            if cand.kind == region.kind:
                continue
            if _iou(region_bbox, cand.bbox) > 0.5:
                matched.append(cand.candidate_id)
        if matched:
            region.audit = dict(region.audit)
            region.audit["detect_overlap_candidates"] = matched
    annotate_region_nested_in_audit(regions)
