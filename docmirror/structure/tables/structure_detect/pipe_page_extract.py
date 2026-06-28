# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Geometric pipe-delimited table extraction from pdfplumber pages (SDU SSOT).

Mirrors legacy ``pipe_strategy`` grid-consistency algorithm; used by ``extract.engine``
Layer 0.5 when G1–G4 gates pass.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from docmirror.structure.tables.pipe_row_merge import merge_pipe_continuation_rows
from docmirror.structure.tables.row_kind import filter_pipe_table_rows
from docmirror.structure.tables.structure_detect.pipe_grid import page_has_no_drawing_primitives
from docmirror.structure.utils.vocabulary import _ALL_BORDER_CHARS, PIPE_CHARS

logger = logging.getLogger(__name__)


def extract_pipe_delimited_table(page_plum) -> list[list[str]] | None:
    """Extract a pipe grid table from a pdfplumber page (G1–G4 gates)."""
    if not page_has_no_drawing_primitives(page_plum):
        return None

    chars = page_plum.chars
    if not chars:
        return None

    y_groups: dict[int, list[dict]] = defaultdict(list)
    for c in chars:
        y_key = round(c["top"] / 3) * 3
        y_groups[y_key].append(c)

    if len(y_groups) < 3:
        return None

    data_rows_ys: list[int] = []
    hline_rows_ys: list[int] = []
    all_pipe_x_by_row: dict[int, list[float]] = {}

    for y_key in sorted(y_groups.keys()):
        row_chars = y_groups[y_key]
        row_text = "".join(c["text"] for c in sorted(row_chars, key=lambda c: c["x0"]))

        non_space = [c for c in row_text if c.strip()]
        if non_space:
            border_ratio = sum(1 for c in non_space if c in _ALL_BORDER_CHARS) / len(non_space)
            if border_ratio >= 0.8:
                hline_rows_ys.append(y_key)
                continue

        pipe_xs = [round(c["x0"], 1) for c in row_chars if c.get("text") in PIPE_CHARS]
        if len(pipe_xs) >= 2:
            data_rows_ys.append(y_key)
            all_pipe_x_by_row[y_key] = sorted(pipe_xs)

    if len(data_rows_ys) < 3:
        return None

    all_pipe_xs: list[float] = []
    for xs in all_pipe_x_by_row.values():
        all_pipe_xs.extend(xs)

    if not all_pipe_xs:
        return None

    snap = 5.0
    x_clusters: dict[float, list[float]] = defaultdict(list)
    for x in sorted(all_pipe_xs):
        snapped = round(x / snap) * snap
        x_clusters[snapped].append(x)

    sorted_centers = sorted(x_clusters.keys())
    merged_clusters: list[list[float]] = []
    for center in sorted_centers:
        if merged_clusters and center - sum(merged_clusters[-1]) / len(merged_clusters[-1]) < 8:
            merged_clusters[-1].extend(x_clusters[center])
        else:
            merged_clusters.append(list(x_clusters[center]))

    n_data_rows = len(data_rows_ys)
    consistent_grid_lines: list[float] = []

    for cluster in merged_clusters:
        rows_with_this_x = set()
        for y_key, pipe_xs in all_pipe_x_by_row.items():
            if any(abs(px - sum(cluster) / len(cluster)) < 8 for px in pipe_xs):
                rows_with_this_x.add(y_key)

        presence_ratio = len(rows_with_this_x) / n_data_rows
        if presence_ratio < 0.7:
            continue

        mean_x = sum(cluster) / len(cluster)
        variance = sum((x - mean_x) ** 2 for x in cluster) / len(cluster)
        std_x = variance**0.5
        if std_x > 3.0:
            continue

        consistent_grid_lines.append(mean_x)

    if len(consistent_grid_lines) < 3:
        return None

    consistent_grid_lines.sort()
    n_cols = len(consistent_grid_lines) - 1
    if n_cols < 2:
        return None

    logger.info(
        "pipe_delimited: detected %s grid lines, %s cols, %s data rows, %s hline rows",
        len(consistent_grid_lines),
        n_cols,
        n_data_rows,
        len(hline_rows_ys),
    )

    col_intervals = [(consistent_grid_lines[i], consistent_grid_lines[i + 1]) for i in range(n_cols)]

    table: list[list[str]] = []
    for y_key in sorted(data_rows_ys):
        row_chars = sorted(y_groups[y_key], key=lambda c: c["x0"])
        content_chars = [c for c in row_chars if c.get("text") not in PIPE_CHARS]

        cells = [""] * n_cols
        for c in content_chars:
            cx = c["x0"]
            assigned = False
            for col_idx, (left, right) in enumerate(col_intervals):
                if left - 3 <= cx < right + 3:
                    cells[col_idx] += c["text"]
                    assigned = True
                    break
            if not assigned:
                distances = [abs(cx - (l + r) / 2) for l, r in col_intervals]
                nearest = distances.index(min(distances))
                cells[nearest] += c["text"]

        table.append([cell.strip() for cell in cells])

    if len(table) < 3:
        return None

    table = merge_pipe_continuation_rows(table)
    table = filter_pipe_table_rows(table)

    if len(table) < 3:
        return None

    logger.info("pipe_delimited: extracted %s rows x %s cols", len(table), n_cols)
    return table
