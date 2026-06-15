# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Layout analysis — page-level region detection and row reconstruction.

Purpose: Detects borderless tables, analyzes page/document layout (including
parallel workers), and reconstructs text rows from raw chars.

Main components: ``analyze_page_layout``, ``analyze_document_layout``,
``_reconstruct_rows_from_chars``.

Upstream: Fitz page extraction, ``segment.layout_model``.

Downstream: ``segment.zone_segment``, ``extract.segmentation``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from docmirror.core.segment.zone_models import ALPageLayout, ContentRegion

logger = logging.getLogger(__name__)

def _detect_borderless_table(text_dict: dict, page_height: float) -> bool:
    """
    Heuristic detection of borderless tables.
    If >= 3 rows have >= 2 independent x segments -> determined as a borderless table.
    """
    spans = []
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                bbox = span["bbox"]
                spans.append(
                    {
                        "x0": bbox[0],
                        "x1": bbox[2],
                        "y_mid": (bbox[1] + bbox[3]) / 2,
                        "text": text,
                    }
                )

    if len(spans) < 6:
        return False

    spans.sort(key=lambda s: s["y_mid"])
    rows: list[list[dict]] = []
    current_row: list[dict] = [spans[0]]
    for s in spans[1:]:
        if abs(s["y_mid"] - current_row[-1]["y_mid"]) <= 3.0:
            current_row.append(s)
        else:
            rows.append(current_row)
            current_row = [s]
    rows.append(current_row)

    multi_col_rows = 0
    for row in rows:
        if len(row) < 2:
            continue
        row.sort(key=lambda s: s["x0"])
        segments = 1
        for i in range(1, len(row)):
            gap = row[i]["x0"] - row[i - 1]["x1"]
            if gap > 20:
                segments += 1
        if segments >= 2:
            multi_col_rows += 1

    return multi_col_rows >= 3


def analyze_page_layout(page, page_idx: int) -> ALPageLayout:
    """Analyze single page layout structure (~30ms/page)."""
    rect = page.rect
    layout = ALPageLayout(page_index=page_idx, width=rect.width, height=rect.height)

    text_dict = page.get_text("dict", flags=0)
    text_blocks = [b for b in text_dict.get("blocks", []) if b.get("type") == 0]
    image_blocks = [b for b in text_dict.get("blocks", []) if b.get("type") == 1]

    for b in text_blocks:
        bbox = (b["bbox"][0], b["bbox"][1], b["bbox"][2], b["bbox"][3])
        preview = ""
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                preview += span.get("text", "")
        preview = preview.strip()[:80]
        if preview:
            layout.regions.append(ContentRegion(type="text", bbox=bbox, page=page_idx, text_preview=preview))

    layout.text_region_count = len([r for r in layout.regions if r.type == "text"])

    for b in image_blocks:
        bbox = (b["bbox"][0], b["bbox"][1], b["bbox"][2], b["bbox"][3])
        layout.regions.append(
            ContentRegion(
                type="image",
                bbox=bbox,
                page=page_idx,
                text_preview=f"image_{b.get('width', 0)}x{b.get('height', 0)}",
            )
        )
    layout.image_count = len(image_blocks)

    # ── Fast table detection: line-count heuristic (~1ms vs ~2000ms) ──
    # The actual table extraction happens later in extract_tables_layered().
    # Here we only need a boolean has_table for routing decisions.
    try:
        drawings = page.get_drawings()
        v_lines = 0
        h_lines = 0
        for d in drawings:
            for item in d.get("items", []):
                if item[0] == "l":  # line item
                    p1, p2 = item[1], item[2]
                    dx = abs(p1.x - p2.x)
                    dy = abs(p1.y - p2.y)
                    if dx < 1 and dy > 5:
                        v_lines += 1
                    elif dy < 1 and dx > 5:
                        h_lines += 1
            if item[0] == "re":  # rectangle item → implies borders
                v_lines += 2
                h_lines += 2
        # Bordered table: has both vertical and horizontal lines
        if v_lines >= 2 and h_lines >= 2:
            layout.has_table = True
            layout.table_count = 1  # approximate; exact count not needed for routing
    except Exception as exc:
        logger.debug(f"fast table detection: suppressed {exc}")

    # Fallback: borderless table detection (existing heuristic)
    if not layout.has_table:
        if _detect_borderless_table(text_dict, rect.height):
            layout.has_table = True

    total_chars = sum(
        len(span.get("text", "")) for b in text_blocks for line in b.get("lines", []) for span in line.get("spans", [])
    )
    if total_chars < 50 and layout.image_count > 0:
        page_area = rect.width * rect.height
        for b in image_blocks:
            bx = b["bbox"]
            img_area = max(0, (bx[2] - bx[0]) * (bx[3] - bx[1]))
            if img_area > page_area * 0.4:
                layout.is_scanned = True
                break

    layout.regions.sort(key=lambda r: r.bbox[1])

    if layout.has_table:
        table_regions = [r for r in layout.regions if r.type == "table"]
        if table_regions:
            table_top = min(r.bbox[1] for r in table_regions)
            table_bottom = max(r.bbox[3] for r in table_regions)
            layout.header_text = " | ".join(
                r.text_preview for r in layout.regions if r.type == "text" and r.bbox[3] <= table_top + 5
            )
            layout.footer_text = " | ".join(
                r.text_preview for r in layout.regions if r.type == "text" and r.bbox[1] >= table_bottom - 5
            )

    if layout.has_table:
        table_regions = [r for r in layout.regions if r.type == "table"]
        if table_regions:
            earliest_table_top = min(r.bbox[1] for r in table_regions)
            above_table_text = sum(
                1 for r in layout.regions if r.type == "text" and r.bbox[3] <= earliest_table_top + 5
            )
            layout.is_continuation = earliest_table_top < rect.height * 0.15 and above_table_text <= 2

    return layout


def analyze_document_layout(fitz_doc) -> list[ALPageLayout]:
    """Analyze the layout structure of the entire document."""
    layouts = []
    for page_idx in range(len(fitz_doc)):
        layouts.append(analyze_page_layout(fitz_doc[page_idx], page_idx))

    if layouts and layouts[0].is_continuation:
        layouts[0].is_continuation = False

    logger.info(
        f"{len(layouts)} pages: "
        + " | ".join(
            f"P{l.page_index + 1}({'cont' if l.is_continuation else 'new'}:"
            f"T{l.table_count}/I{l.image_count}/Txt{l.text_region_count})"
            for l in layouts
        )
    )
    return layouts


def _analyze_page_layout_worker(args: tuple[str, int]) -> tuple[int, ALPageLayout]:
    """
    Worker for process-pool layout analysis: open PDF at path, analyze one page, return (page_idx, ALPageLayout).
    Must be a top-level function for pickle; used by analyze_document_layout_parallel.
    """
    path, page_idx = args
    import fitz

    doc = fitz.open(path)
    try:
        page = doc[page_idx]
        layout = analyze_page_layout(page, page_idx)
        return (page_idx, layout)
    finally:
        doc.close()


def analyze_document_layout_parallel(
    path: str,
    num_pages: int,
    max_workers: int = 4,
) -> list[ALPageLayout]:
    """
    Analyze document layout in parallel across pages using a process pool.
    Each process opens the PDF at path and runs analyze_page_layout for one page.
    Use when max_page_concurrency > 1 to reduce layout stage time on multi-page documents.
    """
    import os
    from concurrent.futures import ProcessPoolExecutor

    path = str(path)
    workers = min(max_workers, num_pages, os.cpu_count() or 4)
    if workers <= 1 or num_pages <= 1:
        # Fallback to sequential in caller by not using this path, or we could open and run here
        import fitz

        doc = fitz.open(path)
        try:
            layouts = [analyze_page_layout(doc[i], i) for i in range(num_pages)]
        finally:
            doc.close()
    else:
        args_list = [(path, i) for i in range(num_pages)]
        with ProcessPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(_analyze_page_layout_worker, args_list))
        layouts = [r[1] for r in sorted(results, key=lambda x: x[0])]

    if layouts and layouts[0].is_continuation:
        layouts[0].is_continuation = False

    logger.info(
        f"{len(layouts)} pages (parallel workers={workers}): "
        + " | ".join(
            f"P{l.page_index + 1}({'cont' if l.is_continuation else 'new'}:"
            f"T{l.table_count}/I{l.image_count}/Txt{l.text_region_count})"
            for l in layouts
        )
    )
    return layouts


# ═══════════════════════════════════════════════════════════════════════════════
# Module 1b: Spatial Partitioning
# ═══════════════════════════════════════════════════════════════════════════════


def _reconstruct_rows_from_chars(chars, col_gap: float = 8.0):
    """Fallback: Reconstruct table rows directly from chars."""
    if not chars:
        return []
    y_groups = defaultdict(list)
    for c in chars:
        y_key = round(c["top"] / 3) * 3
        y_groups[y_key].append(c)

    rows = []
    for y_key in sorted(y_groups.keys()):
        row_chars = sorted(y_groups[y_key], key=lambda c: c["x0"])

        def _chars_to_cell(cell_chars):
            if not cell_chars:
                return ""
            out = cell_chars[0]["text"]
            for j in range(1, len(cell_chars)):
                gap = cell_chars[j]["x0"] - cell_chars[j - 1]["x1"]
                if gap > 2.5:
                    out += " "
                out += cell_chars[j]["text"]
            return out.strip()

        cells = []
        current_cell = [row_chars[0]]
        for i in range(1, len(row_chars)):
            if row_chars[i]["x0"] - row_chars[i - 1]["x1"] > col_gap:
                cells.append(_chars_to_cell(current_cell))
                current_cell = [row_chars[i]]
            else:
                current_cell.append(row_chars[i])
        cells.append(_chars_to_cell(current_cell))
        if any(c for c in cells):
            rows.append(cells)
    return rows
