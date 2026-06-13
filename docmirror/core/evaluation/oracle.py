# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Extract-layer oracle helpers for relative row-preservation gates."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _sample_page_indices(num_pages: int, sample_count: int) -> list[int]:
    """0-based page indices for oracle sampling (skip page 0 title band when possible)."""
    if num_pages <= 0:
        return []
    if num_pages <= sample_count:
        return list(range(num_pages))
    step = max(1, (num_pages - 2) // sample_count)
    indices: list[int] = []
    idx = 1
    while len(indices) < sample_count and idx < num_pages:
        indices.append(idx)
        idx += step
    return indices[:sample_count]


def pdfplumber_full_page_sample_oracle(
    pdf_path: Path | str,
    *,
    num_pages: int | None = None,
    sample_count: int = 3,
) -> int:
    """Estimate total data rows via evenly spaced pdfplumber full-page samples.

    Matches the design-doc ``oracle_mode=pdfplumber_full_page_sample`` approach:
    sample N continuation-heavy pages, average data rows, extrapolate to ``num_pages``.
    """
    from docmirror.core.table.extraction.best_candidate import count_data_rows

    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    import pdfplumber

    with pdfplumber.open(path) as doc:
        total = num_pages if num_pages is not None else len(doc.pages)
        if total <= 0:
            return 0
        indices = _sample_page_indices(total, sample_count)
        if not indices:
            return 0

        sample_rows = 0
        for page_idx in indices:
            if page_idx >= len(doc.pages):
                continue
            page = doc.pages[page_idx]
            try:
                tables = page.extract_tables() or []
            except Exception as exc:
                logger.debug("[Oracle] page %d extract_tables failed: %s", page_idx + 1, exc)
                continue
            if not tables or not tables[0]:
                continue
            sample_rows += count_data_rows(tables[0])

        if not indices:
            return 0
        avg = sample_rows / len(indices)
        return int(round(avg * total))
