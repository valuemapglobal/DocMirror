# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Table column utilities — effective column counting helpers.

Purpose: Computes pipe-delimited and effective column counts for validating
table width consistency across tiers.

Main components: ``effective_table_column_count``, ``_pipe_column_count``.

Upstream: Raw table row strings.

Downstream: ``extract.best_candidate``, ``table.merge.merger``.
"""

from __future__ import annotations


def _pipe_column_count(text: str) -> int:
    if "|" not in text:
        return 0
    return len([part for part in text.split("|") if part.strip()])


def effective_table_column_count(table) -> int:
    """Return best-effort column count for scrubbing / quality metrics."""
    counts: list[int] = []
    headers = list(getattr(table, "headers", []) or [])
    if headers:
        if len(headers) == 1 and "|" in str(headers[0]):
            counts.append(_pipe_column_count(str(headers[0])))
        else:
            counts.append(len(headers))

    for row in getattr(table, "rows", []) or []:
        cells = getattr(row, "cells", []) or []
        counts.append(len(cells))
        for cell in cells:
            text = (getattr(cell, "text", "") or getattr(cell, "cleaned", "") or "").strip()
            pipe_cols = _pipe_column_count(text)
            if pipe_cols:
                counts.append(pipe_cols)

    return max(counts) if counts else 0
