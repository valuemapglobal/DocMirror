# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Credit-report micro-grid materializer registration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from docmirror.structure.ocr.micro_grid.materialize import register_micro_grid_materializer
from docmirror.plugins.credit_report.repayment_grid import extract_credit_repayment_records


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
    out = extract_credit_repayment_records(
        lines,
        page=page,
        tokens=tokens,
        page_width=page_width,
        page_height=page_height,
        page_image=page_image,
        enable_cell_ocr=enable_cell_ocr,
    )
    grid = out.get("micro_grid")
    return [grid] if isinstance(grid, dict) else []
