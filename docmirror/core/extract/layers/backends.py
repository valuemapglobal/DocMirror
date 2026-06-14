# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Optional extraction backends: PyMuPDF native, RapidTable HTML."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

def extract_by_pymupdf(
    fitz_page,
    table_zone_bbox: tuple[float, float, float, float] | None = None,
) -> list[list[list[str]]] | None:
    """L0.8: PyMuPDF native table detection (C implementation).

    Uses PyMuPDF's built-in ``page.find_tables()`` which is implemented in C
    and is typically 50-70% faster than pdfplumber's Python-level extraction.

    Args:
        fitz_page: PyMuPDF (fitz) page object.
        table_zone_bbox: Optional crop region (x0, y0, x1, y1).

    Returns:
        List of 2-D table arrays, or None if no tables found.
    """
    try:
        import fitz

        # Optionally crop to table zone
        clip = None
        if table_zone_bbox:
            x0, y0, x1, y1 = table_zone_bbox
            clip = fitz.Rect(x0, y0, x1, y1)

        # PyMuPDF find_tables() — C-native, very fast
        tab_finder = fitz_page.find_tables(clip=clip)
        if not tab_finder or not tab_finder.tables:
            return None

        tables = []
        for tab in tab_finder.tables:
            # Extract table data using PyMuPDF's built-in extract method
            try:
                data = tab.extract()
                if data and len(data) >= 2:
                    # Clean cells: replace None with empty string
                    clean_data = [[(cell or "").strip() for cell in row] for row in data]
                    tables.append(clean_data)
            except Exception:
                continue

        return tables if tables else None

    except Exception as exc:
        logger.debug("_extract_by_pymupdf: %s", exc)
        return None


def extract_by_rapid_table(page_plum) -> list[list[str]] | None:
    """L1.8: table structure extraction using RapidTable ONNX vision model.

    RapidTable is a dedicated table-structure recognition model (CPU ONNX v3)
    that excels at borderless tables, three-line tables, and complex headers.
    Uses a singleton engine to avoid reloading the model.

    Returns:
        2-D table list, or ``None`` when not installed / recognition fails.
    """
    from docmirror.core.extract.rapid_table_engine import get_rapid_table_engine

    engine = get_rapid_table_engine()
    if not engine.is_available:
        return None

    try:
        import numpy as np

        # Render pdfplumber page to image (200 DPI)
        img = page_plum.to_image(resolution=200)
        img_np = np.array(img.original)

        # Call RapidTable v3
        result = engine(img_np)
        if result is None or not result.pred_htmls:
            return None

        html_str = result.pred_htmls[0]
        if not html_str:
            return None

        # Parse HTML → 2-D array
        return parse_html_table(html_str)

    except Exception as e:
        logger.debug(f"RapidTable error: {e}")
        return None


def parse_html_table(html_str: str) -> list[list[str]] | None:
    """Parse RapidTable HTML output into a 2-D array with colspan/rowspan support."""
    try:
        import re as _re

        row_pattern = _re.compile(r"<tr>(.*?)</tr>", _re.DOTALL)
        cell_pattern = _re.compile(r"(<t[dh][^>]*>)(.*?)</t[dh]>", _re.DOTALL)
        tag_cleaner = _re.compile(r"<[^>]+>")

        raw_rows = []  # [(col_idx, text, colspan, rowspan), ...] per row
        for row_match in row_pattern.finditer(html_str):
            cells = []
            for cell_match in cell_pattern.finditer(row_match.group(1)):
                tag = cell_match.group(1)
                text = tag_cleaner.sub("", cell_match.group(2)).strip()

                colspan_m = _re.search(r'colspan="(\d+)"', tag)
                rowspan_m = _re.search(r'rowspan="(\d+)"', tag)
                colspan = int(colspan_m.group(1)) if colspan_m else 1
                rowspan = int(rowspan_m.group(1)) if rowspan_m else 1

                cells.append((text, colspan, rowspan))
            if cells:
                raw_rows.append(cells)

        if len(raw_rows) < 2:
            return None

        # Expand colspan/rowspan into a 2-D grid
        grid: list = []  # List[List[str]]
        carry: dict = {}  # {col_idx: (text, remaining_rowspan)}

        for raw_cells in raw_rows:
            row_out: list = []
            col_idx = 0

            cell_iter = iter(raw_cells)
            current_cell = next(cell_iter, None)

            while current_cell is not None or col_idx in carry:
                # Fill in rowspan carry-over from previous rows
                if col_idx in carry:
                    text, remaining = carry[col_idx]
                    row_out.append(text)
                    if remaining > 1:
                        carry[col_idx] = (text, remaining - 1)
                    else:
                        del carry[col_idx]
                    col_idx += 1
                    continue

                if current_cell is None:
                    break

                text, colspan, rowspan = current_cell
                for ci in range(colspan):
                    actual_col = col_idx + ci
                    # Skip positions occupied by carry
                    while actual_col in carry:
                        ct, cr = carry[actual_col]
                        row_out.append(ct)
                        if cr > 1:
                            carry[actual_col] = (ct, cr - 1)
                        else:
                            del carry[actual_col]
                        actual_col += 1
                    row_out.append(text if ci == 0 else "")
                    if rowspan > 1:
                        carry[actual_col] = (text, rowspan - 1)

                col_idx = len(row_out)
                current_cell = next(cell_iter, None)

            # Process trailing carry entries
            while col_idx in carry:
                text, remaining = carry[col_idx]
                row_out.append(text)
                if remaining > 1:
                    carry[col_idx] = (text, remaining - 1)
                else:
                    del carry[col_idx]
                col_idx += 1

            grid.append(row_out)

        # Align column counts
        if grid:
            max_cols = max(len(r) for r in grid)
            for row in grid:
                while len(row) < max_cols:
                    row.append("")

        return grid if len(grid) >= 2 else None
    except Exception as exc:
        logger.debug(f"operation: suppressed {exc}")
        return None
