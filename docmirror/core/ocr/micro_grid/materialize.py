# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parse-time micro-grid materialization from OCR evidence (SMG registry)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

MicroGridMaterializer = Callable[
    ...,
    list[dict[str, Any]],
]

_MATERIALIZERS: list[MicroGridMaterializer] = []


def register_micro_grid_materializer(materializer: MicroGridMaterializer) -> MicroGridMaterializer:
    """Register a domain materializer that returns zero or more micro_grid dicts."""
    if materializer not in _MATERIALIZERS:
        _MATERIALIZERS.append(materializer)
    return materializer


def extract_micro_grid_structures(
    lines: Iterable[Any],
    *,
    tokens: Iterable[Any] | None = None,
    page: int,
    page_width: float | None = None,
    page_height: float | None = None,
    page_image: Any | None = None,
    enable_cell_ocr: bool = False,
) -> list[dict[str, Any]]:
    """Run registered SMG materializers for one OCR page."""
    structures: list[dict[str, Any]] = []
    for materializer in _MATERIALIZERS:
        try:
            grids = materializer(
                lines=lines,
                tokens=tokens,
                page=page,
                page_width=page_width,
                page_height=page_height,
                page_image=page_image,
                enable_cell_ocr=enable_cell_ocr,
            )
        except Exception:
            continue
        for grid in grids or []:
            if isinstance(grid, dict):
                structures.append(dict(grid))
    return structures
