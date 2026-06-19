# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for scanned local structure restoration."""

from __future__ import annotations

from typing import Any
from collections.abc import Iterable

from docmirror.core.ocr.local_structure.models import BBox
from docmirror.core.ocr.micro_grid.models import OCRToken


def bbox_of(obj: Any) -> BBox | None:
    raw = obj.get("bbox") if isinstance(obj, dict) else getattr(obj, "bbox", None)
    if raw and len(raw) == 4:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    return None


def text_of(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("content") or obj.get("text") or "").strip()
    return str(getattr(obj, "text", "") or "").strip()


def confidence_of(obj: Any) -> float:
    val = obj.get("confidence") if isinstance(obj, dict) else getattr(obj, "confidence", 1.0)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 1.0


def line_id_of(obj: Any, *, page: int, idx: int) -> str:
    if isinstance(obj, dict):
        return str(obj.get("line_id") or obj.get("evidence_id") or f"ls_p{page}_l{idx}")
    return str(getattr(obj, "line_id", "") or getattr(obj, "evidence_id", "") or f"ls_p{page}_l{idx}")


def line_items(lines: Iterable[Any], *, page: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, line in enumerate(lines or []):
        b = bbox_of(line)
        t = text_of(line)
        if not b or not t:
            continue
        out.append(
            {
                "idx": idx,
                "line_id": line_id_of(line, page=page, idx=idx),
                "text": t,
                "bbox": b,
                "confidence": confidence_of(line),
            }
        )
    return sorted(out, key=lambda x: (x["bbox"][1], x["bbox"][0]))


def coerce_token(obj: Any, *, page: int, idx: int) -> OCRToken | None:
    if isinstance(obj, OCRToken):
        return obj
    b = bbox_of(obj)
    t = text_of(obj)
    if not b or not t:
        return None
    raw_bbox = obj.get("raw_bbox") if isinstance(obj, dict) else getattr(obj, "raw_bbox", None)
    raw = None
    if raw_bbox and len(raw_bbox) == 4:
        raw = (float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3]))
    token_id = obj.get("token_id") if isinstance(obj, dict) else getattr(obj, "token_id", None)
    return OCRToken(
        token_id=str(token_id or f"ocr_p{page}_t{idx}"),
        text=t,
        bbox=b,
        confidence=confidence_of(obj),
        page=page,
        source=str(obj.get("source", "ocr") if isinstance(obj, dict) else getattr(obj, "source", "ocr")),
        coordinate_system=str(
            obj.get("coordinate_system", "pdf_points_top_left")
            if isinstance(obj, dict)
            else getattr(obj, "coordinate_system", "pdf_points_top_left")
        ),
        raw_bbox=raw,
        raw_coordinate_system=str(
            obj.get("raw_coordinate_system", "image_pixels")
            if isinstance(obj, dict)
            else getattr(obj, "raw_coordinate_system", "image_pixels")
        ),
    )


def coerce_tokens(tokens: Iterable[Any] | None, *, page: int) -> list[OCRToken]:
    out: list[OCRToken] = []
    for idx, token in enumerate(tokens or []):
        coerced = coerce_token(token, page=page, idx=idx)
        if coerced is not None:
            out.append(coerced)
    return out


def union_bbox(boxes: Iterable[BBox]) -> BBox:
    vals = list(boxes)
    return (
        min(b[0] for b in vals),
        min(b[1] for b in vals),
        max(b[2] for b in vals),
        max(b[3] for b in vals),
    )


def x_overlap_ratio(a: BBox, b: BBox) -> float:
    left = max(a[0], b[0])
    right = min(a[2], b[2])
    overlap = max(0.0, right - left)
    denom = max(1.0, min(a[2] - a[0], b[2] - b[0]))
    return overlap / denom
