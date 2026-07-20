# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Credit-report micro-grid materializer registration."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from docmirror.ocr.micro_grid.materialize import register_micro_grid_materializer
from docmirror.plugins.credit_report.repayment_grid import extract_credit_repayment_records

_RANGE_ANCHOR_RE = re.compile(r"20\d{2}年\s*\d{1,2}月\s*[-—一至~～]\s*20\d{2}年\s*\d{1,2}月.*还款记录")
_CONTINUATION_BOUNDARY_RE = re.compile(
    r"^\s*(?:[A-Za-z]\s*)?(?:[（(][一二三四五六七八九十]+[）)]|账户\s*\d*(?:[（(]|\s)|授信协议|查询记录)"
)


def _text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or item.get("content") or "")
    return str(getattr(item, "text", "") or "")


def _bbox(item: Any) -> list[float]:
    raw = item.get("bbox") if isinstance(item, dict) else getattr(item, "bbox", None)
    if raw and len(raw) == 4:
        return [float(value) for value in raw]
    return [0.0, 0.0, 0.0, 0.0]


def _date_range_only_grid(
    anchor: Any,
    *,
    page: int,
    grid_index: int,
    page_width: float | None,
) -> dict[str, Any] | None:
    anchor_text = re.sub(r"\s+", "", _text(anchor))
    match = _RANGE_ANCHOR_RE.search(anchor_text)
    values = re.search(
        r"(20\d{2})年(\d{1,2})月[-—一至~～](20\d{2})年(\d{1,2})月",
        anchor_text,
    )
    if match is None or values is None:
        return None
    start_year, start_month, end_year, end_month = (int(value) for value in values.groups())
    width = max(float(page_width or 0.0), 120.0)
    left = min(40.0, width * 0.08)
    right = max(left + 12.0, width - left)
    step = (right - left) / 12.0
    return {
        "grid_id": f"mg_p{page}_repayment_{grid_index}",
        "structure_kind": "micro_grid",
        "page": page,
        "bbox": _bbox(anchor),
        "anchor_text": _text(anchor),
        "row_bands": [],
        "col_bands": [
            {
                "index": month,
                "header": str(month),
                "role": "month",
                "bbox": [left + step * (month - 1), 0.0, left + step * month, 0.0],
                "geometry_status": "unresolved",
            }
            for month in range(1, 13)
        ],
        "cells": [],
        "grid_type_hint": "credit_repayment_record",
        "geometry_source": "date_range_anchor_only",
        "confidence": 0.35,
        "audit": {
            "reason": "cross_page_or_unresolved_grid_geometry",
            "date_range": {
                "start_year": start_year,
                "start_month": start_month,
                "end_year": end_year,
                "end_month": end_month,
            },
        },
    }


def augment_credit_repayment_evidence_bundles(domain_specific: dict[str, Any]) -> None:
    """Append next-page leading grid rows using shifted y coordinates."""
    bundles = [item for item in domain_specific.get("_page_evidence_bundles") or [] if isinstance(item, dict)]
    bundles.sort(key=lambda item: int(item.get("page") or 0))
    for index, bundle in enumerate(bundles[:-1]):
        evidence = bundle.get("micro_grid_evidence")
        next_evidence = bundles[index + 1].get("micro_grid_evidence")
        if not isinstance(evidence, dict) or not isinstance(next_evidence, dict):
            continue
        if evidence.get("credit_cross_page_augmented"):
            continue
        lines = [dict(line) for line in evidence.get("lines") or [] if isinstance(line, dict)]
        if not any(_RANGE_ANCHOR_RE.search(re.sub(r"\s+", "", _text(line))) for line in lines):
            continue
        leading: list[dict[str, Any]] = []
        for line in next_evidence.get("lines") or []:
            if not isinstance(line, dict):
                continue
            text = _text(line)
            compact = re.sub(r"\s+", "", text)
            if _RANGE_ANCHOR_RE.search(compact) or _CONTINUATION_BOUNDARY_RE.search(text):
                break
            leading.append(dict(line))
        if not leading:
            continue
        shift = float(evidence.get("page_height") or bundle.get("page_height") or 0.0)
        next_page = int(next_evidence.get("page") or bundles[index + 1].get("page") or 0)
        shifted: list[dict[str, Any]] = []
        for line in leading:
            bbox = _bbox(line)
            shifted.append(
                {
                    **line,
                    "bbox": [bbox[0], bbox[1] + shift, bbox[2], bbox[3] + shift],
                    "source_logical_page": next_page,
                    "coordinate_status": "cross_page_y_shift",
                }
            )
        evidence["lines"] = [*lines, *shifted]
        evidence["credit_cross_page_augmented"] = True
        evidence["continuation_logical_pages"] = [next_page]


@register_micro_grid_materializer
def materialize_credit_repayment_micro_grids(
    *,
    lines: Iterable[Any],
    tokens: Iterable[Any] | None = None,
    page: int,
    page_width: float | None = None,
    page_height: float | None = None,
    page_image: Any | None = None,
    enable_cell_ocr: bool = False,
) -> list[dict[str, Any]]:
    line_list = list(lines or [])
    anchor_indices = [
        index for index, line in enumerate(line_list) if _RANGE_ANCHOR_RE.search(re.sub(r"\s+", "", _text(line)))
    ]
    grids: list[dict[str, Any]] = []
    for grid_index, start in enumerate(anchor_indices):
        end = anchor_indices[grid_index + 1] if grid_index + 1 < len(anchor_indices) else len(line_list)
        out = extract_credit_repayment_records(
            line_list[start:end],
            page=page,
            tokens=tokens,
            page_width=page_width,
            page_height=page_height,
            page_image=page_image,
            enable_cell_ocr=enable_cell_ocr,
            grid_index=grid_index,
        )
        grid = out.get("micro_grid")
        if isinstance(grid, dict):
            grids.append(grid)
        else:
            placeholder = _date_range_only_grid(
                line_list[start],
                page=page,
                grid_index=grid_index,
                page_width=page_width,
            )
            if placeholder is not None:
                grids.append(placeholder)
    return grids
