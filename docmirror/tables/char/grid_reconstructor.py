# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Grid reconstructor — detect column AND row boundaries for borderless tables.

Purpose: Reconstructs the implicit grid of a borderless table by analyzing
character position projection profiles.  Column boundaries = valleys in the
X-projection density.  Row boundaries = gaps in the Y-projection density.

Main components: ``detect_table_via_grid``.

Upstream: pdfplumber page chars.

Downstream: ``extract.char_strategy``, ``extract.engine``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from docmirror.structure.utils.text_utils import _is_cjk_char
from docmirror.structure.utils.vocabulary import _score_header_by_vocabulary
from docmirror.structure.utils.watermark import is_watermark_char
from docmirror.tables.utils import _group_chars_into_rows

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"^(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}$|^(?:19|20)\d{6}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
_SEQ_RE = re.compile(r"^\d{1,5}$")
_AMOUNT_RE = re.compile(r"^[+-]?\d[\d,]*(?:\.\d+)?$")
_FOOTER_RE = re.compile(r"^(?:第?\d+页|第\d+页/共\d+页|page\d+(?:of\d+)?)$", re.IGNORECASE)
_ANCHOR_HEADER_RE = re.compile(
    r"(序号|编号|流水|日期|时间|date|time|no\.?|number|index)",
    re.IGNORECASE,
)


@dataclass
class TableGrid:
    """Reconstructed grid: column and row dividers (x and y coordinates)."""
    col_dividers: list[float]
    row_dividers: list[float]

    @property
    def num_cols(self) -> int:
        return len(self.col_dividers) - 1

    @property
    def num_rows(self) -> int:
        return len(self.row_dividers) - 1


def _find_gaps(values: list[float]) -> list[tuple[float, float]]:
    """(midpoint, width) for adjacent sorted values."""
    gaps = []
    for i in range(len(values) - 1):
        gap = values[i + 1] - values[i]
        if gap > 0:
            gaps.append(((values[i] + values[i + 1]) / 2, gap))
    return gaps


def _cluster_gaps(gaps: list[tuple[float, float]], multiplier: float = 2.0) -> list[float]:
    """Bimodal gap clustering: small=intra-column, large=inter-column."""
    widths = sorted(g[1] for g in gaps)
    if len(widths) < 3:
        threshold = widths[len(widths) // 2] * multiplier if widths else 5
        return sorted(g[0] for g in gaps if g[1] > threshold)

    max_jump, jump_idx = 0, -1
    for i in range(len(widths) - 1):
        jump = widths[i + 1] - widths[i]
        if jump > max_jump:
            max_jump, jump_idx = jump, i

    med = widths[len(widths) // 2]
    if max_jump > med * 1.5 and jump_idx >= 0:
        threshold = (widths[jump_idx] + widths[jump_idx + 1]) / 2
    else:
        threshold = med * multiplier
    return sorted(g[0] for g in gaps if g[1] > threshold)


def detect_column_grid(chars: list[dict], min_cols: int = 3) -> list[float]:
    """Find column dividers from x-projection gap clustering."""
    xs = sorted(set(round(c["x0"], 1) for c in chars if c.get("text","") and not is_watermark_char(c)))
    if len(xs) < min_cols * 2:
        return []
    dividers = _cluster_gaps(_find_gaps(xs))
    all_x0 = [c["x0"] for c in chars if c.get("text","")]
    all_x1 = [c["x1"] for c in chars if c.get("text","")]
    if not all_x0:
        return []
    dividers = [d for d in dividers if min(all_x0) < d < max(all_x1)]
    if len(dividers) + 1 < min_cols:
        return []
    return [min(all_x0)] + dividers + [max(all_x1)]


def detect_row_grid(chars: list[dict], min_rows: int = 2) -> list[float]:
    """Find row dividers from y-proximity clustering."""
    tc = [c for c in chars if c.get("text","") and not is_watermark_char(c)]
    if len(tc) < 10:
        return []
    by_y = sorted(tc, key=lambda c: c["top"])
    rows, cur, cur_top = [], [by_y[0]], by_y[0]["top"]
    heights = [c["bottom"] - c["top"] for c in tc if c["bottom"] - c["top"] > 0]
    y_tol = max(2, (sorted(heights)[len(heights)//2] if heights else 10) * 0.5)
    for c in by_y[1:]:
        if c["top"] - cur_top <= y_tol:
            cur.append(c)
        else:
            rows.append(cur)
            cur, cur_top = [c], c["top"]
    if cur:
        rows.append(cur)
    centers = [(min(c["top"] for c in r) + max(c["bottom"] for c in r)) / 2 for r in rows]
    if len(centers) < min_rows:
        return []
    divs = [(centers[i] + centers[i+1]) / 2 for i in range(len(centers) - 1)]
    min_y = min(c["top"] for c in tc)
    max_y = max(c["bottom"] for c in tc)
    return [min_y] + divs + [max_y]


def assign_cell(chars: list[dict], col_d: list[float], row_d: list[float], col: int, row: int) -> str:
    """Extract text from a grid cell defined by column and row dividers."""
    cc = [c for c in chars if col_d[col] <= c["x0"] <= col_d[col+1]
          and row_d[row] <= (c["top"] + c["bottom"]) / 2 <= row_d[row+1]]
    cc.sort(key=lambda c: c["x0"])
    return "".join(c.get("text", "") for c in cc).strip()


def _estimate_font_size(chars: list[dict]) -> float:
    heights = [
        c.get("bottom", 0) - c.get("top", 0)
        for c in chars
        if c.get("bottom", 0) > c.get("top", 0) and 3 <= c.get("bottom", 0) - c.get("top", 0) <= 30
    ]
    if not heights:
        return 10.0
    heights.sort()
    return heights[len(heights) // 2]


def _word_rows(words: list[dict], row_tol: float) -> list[tuple[float, list[dict]]]:
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (w.get("top", 0), w.get("x0", 0)))
    rows: list[tuple[float, list[dict]]] = []
    cur = [ordered[0]]
    cur_y = float(ordered[0].get("top", 0))
    for w in ordered[1:]:
        top = float(w.get("top", 0))
        if abs(top - cur_y) <= row_tol:
            cur.append(w)
        else:
            y_mid = sum(float(x.get("top", 0)) for x in cur) / len(cur)
            rows.append((y_mid, sorted(cur, key=lambda x: x.get("x0", 0))))
            cur = [w]
            cur_y = top
    if cur:
        y_mid = sum(float(x.get("top", 0)) for x in cur) / len(cur)
        rows.append((y_mid, sorted(cur, key=lambda x: x.get("x0", 0))))
    return rows


# ── Column-dividers cache for cross-page grid propagation ──
_saved_dividers: dict[str, list[float]] = {}


def _find_header_words(page_plum, chars: list[dict]) -> tuple[list[dict], float] | None:
    """Find the strongest vocabulary header row as word anchors."""
    font_size = _estimate_font_size(chars)
    x_tol = max(3.0, font_size * 0.9)
    y_tol = max(3.0, font_size * 0.4)
    try:
        words = page_plum.extract_words(keep_blank_chars=True, x_tolerance=x_tol, y_tolerance=y_tol)
    except Exception as exc:
        logger.debug("grid-reconstructor word extraction failed: %s", exc)
        return None
    rows = _word_rows(words, max(4.0, font_size * 0.5))
    best_score = 0
    best_words: list[dict] = []
    best_y = 0.0
    for y_mid, row_words in rows[:20]:
        texts = [str(w.get("text", "")).strip() for w in row_words if str(w.get("text", "")).strip()]
        if len(texts) < 3:
            continue
        score = _score_header_by_vocabulary(texts)
        if score > best_score:
            best_score = score
            best_words = row_words
            best_y = y_mid
    if best_score < 3 or len(best_words) < 3:
        return None
    return sorted(best_words, key=lambda w: w.get("x0", 0)), best_y


def _column_dividers_from_header(header_words: list[dict], chars: list[dict]) -> list[float]:
    """Convert header word boxes into vertical divider lines."""
    header_words = sorted(header_words, key=lambda w: w.get("x0", 0))
    if len(header_words) < 2:
        return []
    x0s = [float(w.get("x0", 0)) for w in header_words]
    x1s = [float(w.get("x1", w.get("x0", 0))) for w in header_words]
    char_x0 = min((float(c.get("x0", 0)) for c in chars), default=x0s[0])
    char_x1 = max((float(c.get("x1", c.get("x0", 0))) for c in chars), default=x1s[-1])
    first_gap = x0s[1] - x0s[0]
    last_gap = x0s[-1] - x0s[-2]
    left = min(char_x0, max(0.0, x0s[0] - max(6.0, first_gap * 0.55)))
    right = max(char_x1, x1s[-1] + max(6.0, last_gap * 0.55))
    dividers = [left]
    for i in range(len(header_words) - 1):
        dividers.append((x1s[i] + x0s[i + 1]) / 2)
    dividers.append(right)
    return dividers


def _cell_join(left: str, right: str) -> str:
    left = (left or "").strip()
    right = (right or "").strip()
    if not left:
        return right
    if not right:
        return left
    if left[-1].isdigit() and right[0].isdigit():
        return left + right
    if _is_cjk_char(left[-1]) or _is_cjk_char(right[0]):
        return left + right
    return left + " " + right


def _assign_chars_to_dividers(chars: list[dict], dividers: list[float]) -> list[str]:
    """Assign characters by character center, splitting text that spans dividers."""
    if len(dividers) < 2:
        return []
    cells = ["" for _ in range(len(dividers) - 1)]
    for c in sorted(chars, key=lambda x: (x.get("top", 0), x.get("x0", 0))):
        text = str(c.get("text", ""))
        if not text.strip():
            continue
        center = (float(c.get("x0", 0)) + float(c.get("x1", c.get("x0", 0)))) / 2
        idx = 0
        for i in range(len(dividers) - 1):
            if dividers[i] <= center <= dividers[i + 1]:
                idx = i
                break
            if center > dividers[i + 1]:
                idx = min(i + 1, len(cells) - 1)
        cells[idx] += text
    return [cell.strip() for cell in cells]


def _merge_line_cells(target: list[str], line_cells: list[str]) -> None:
    for idx, value in enumerate(line_cells):
        if idx >= len(target):
            break
        if value:
            target[idx] = _cell_join(target[idx], value)


def _looks_like_record_start(cells: list[str], anchor_cols: list[int]) -> bool:
    if not cells or not any(cells):
        return False
    anchor_values = [cells[i].strip() for i in anchor_cols if i < len(cells) and cells[i].strip()]
    if not anchor_values:
        return False
    first = cells[0].strip() if cells else ""
    has_date = any(_DATE_RE.match(v) for v in anchor_values)
    has_time = any(_TIME_RE.match(v) for v in anchor_values)
    has_seq = bool(first and _SEQ_RE.match(first))
    leading_non_empty = sum(1 for i in range(min(3, len(cells))) if cells[i].strip())
    if has_date or (has_seq and (has_time or leading_non_empty >= 2)):
        return True
    non_empty = sum(1 for c in cells if c.strip())
    has_amount = any(_AMOUNT_RE.match(c.replace(",", "")) for c in cells if c.strip())
    return leading_non_empty >= 2 and (non_empty >= 3 or has_amount)


def _is_footer_or_junk_line(cells: list[str]) -> bool:
    compact = "".join(str(c or "").strip() for c in cells)
    compact = re.sub(r"\s+", "", compact)
    return bool(compact and _FOOTER_RE.match(compact))


def _anchor_columns(headers: list[str]) -> list[int]:
    anchors = [idx for idx, text in enumerate(headers) if _ANCHOR_HEADER_RE.search(text or "")]
    if anchors:
        return anchors[: max(2, min(4, len(anchors)))]
    return list(range(min(3, len(headers))))


def _detect_table_via_header_grid(page_plum, chars: list[dict]) -> list[list[str]] | None:
    """Reconstruct an implicit table grid from header anchors and logical row bands."""
    header = _find_header_words(page_plum, chars)
    dividers: list[float] | None = None

    if header is not None:
        header_words, header_y = header
        headers = [str(w.get("text", "")).strip() for w in header_words]
        if _score_header_by_vocabulary(headers) >= 3:
            dividers = _column_dividers_from_header(header_words, chars)
            if dividers is not None and len(dividers) != len(headers) + 1:
                dividers = None
    else:
        header_y = 0.0

    # No fresh header detected — try saved dividers from a previous page
    if dividers is None:
        page_width = float(getattr(page_plum, "width", 0) or 0)
        saved = _saved_dividers.get(str(page_width))
        if saved is not None:
            dividers = list(saved)
            # Infer header text from the saved dividers on the first data row
            header_y = 0.0
            headers = ["" for _ in range(len(saved) - 1)]

    if dividers is None or len(dividers) < 3:
        return None

    row_lines = _group_chars_into_rows(chars, y_tolerance=0)
    if len(row_lines) < 2:
        return None

    physical_rows: list[tuple[float, list[str]]] = []
    for y_mid, row_chars in row_lines:
        if y_mid <= header_y + 1:
            continue
        line_cells = _assign_chars_to_dividers(row_chars, dividers)
        if _is_footer_or_junk_line(line_cells):
            continue
        if any(line_cells):
            physical_rows.append((y_mid, line_cells))
    if not physical_rows:
        return None

    anchor_cols = _anchor_columns(headers)
    logical_rows: list[list[str]] = []
    current: list[str] | None = None
    for _y_mid, line_cells in physical_rows:
        is_start = _looks_like_record_start(line_cells, anchor_cols)
        if is_start:
            if current and any(current):
                logical_rows.append(current)
            current = ["" for _ in headers]
            _merge_line_cells(current, line_cells)
        elif current is not None:
            _merge_line_cells(current, line_cells)
        elif sum(1 for c in line_cells if c.strip()) >= max(2, len(headers) // 3):
            current = ["" for _ in headers]
            _merge_line_cells(current, line_cells)
    if current and any(current):
        logical_rows.append(current)

    if len(logical_rows) < 1:
        return None

    table = [headers] + logical_rows
    # Relax density check for continuation pages (saved dividers with no header)
    if headers and any(headers):
        data_density = sum(1 for row in logical_rows if sum(1 for c in row if c.strip()) >= 2) / max(len(logical_rows), 1)
        if data_density < 0.8:
            return None
    else:
        # Continuation page: only require some non-empty cells
        if not any(any(c.strip() for c in row) for row in logical_rows):
            return None
    # Save column dividers for cross-page propagation.
    # This allows continuation pages (without headers) to reuse the
    # same column structure, dramatically improving accuracy.
    page_width = float(getattr(page_plum, "width", 0) or 0)
    if page_width > 0:
        _saved_dividers[str(page_width)] = dividers
    logger.info(
        "grid-reconstructor: header-grid %d rows x %d cols (vocab=%d)",
        len(table),
        len(headers),
        _score_header_by_vocabulary(headers),
    )
    return table


def detect_table_via_grid(page_plum) -> list[list[str]] | None:
    """Extract a borderless table as a grid of cells.

    1. Detect column boundaries from x-projection gap clustering.
    2. Detect row boundaries from y-proximity text line clustering.
    3. Assign each character to a grid cell (col × row intersection).
    4. Validate: header row vocabulary score >= 3.
    """
    chars = page_plum.chars
    if not chars:
        return None
    chars = [c for c in chars if c.get("text", "") and not is_watermark_char(c)]
    if not chars:
        return None

    header_grid = _detect_table_via_header_grid(page_plum, chars)
    if header_grid is not None:
        return header_grid

    col_d = detect_column_grid(chars)
    row_d = detect_row_grid(chars)
    if len(col_d) < 4 or len(row_d) < 3:
        return None

    table = []
    for ri in range(len(row_d) - 1):
        row = [assign_cell(chars, col_d, row_d, ci, ri) for ci in range(len(col_d) - 1)]
        table.append(row)

    if len(table) < 2 or _score_header_by_vocabulary(table[0]) < 3:
        return None

    logger.info(
        "grid-detected: %d rows x %d cols (vocab=%d)",
        len(table),
        len(col_d) - 1,
        _score_header_by_vocabulary(table[0]),
    )
    return table
