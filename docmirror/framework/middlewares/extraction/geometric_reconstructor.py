"""
GeometricReconstructor Middleware
================================

Reconstructs table structure from OCR text blocks using only geometric
(spatial) information — no ML models required.

When the traditional pipeline (layout analysis + table extraction) fails to
detect tables but produces text blocks with bounding box coordinates, this
middleware clusters the blocks by vertical and horizontal position to rebuild
the tabular structure.

Algorithm (three passes):

    Pass 1 — Y-Line Clustering
        Group text blocks by vertical center position. Blocks with similar
        Y coordinates are presumed to belong to the same document row.

    Pass 2 — X-Column Splitting
        Within each Y-line, sort blocks by X and detect column boundaries
        using an adaptive gap threshold (median_gap * 3 or 2% page width).

    Pass 3 — Alignment Validation
        Check that column positions are consistent across rows (covariance
        test). If the grid is regular enough, build a TableBlock and inject
        it into ParseResult.

Trigger:
    - table_count == 0
    - text_blocks >= 6
    - >= 80% blocks have valid bbox data
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

from docmirror.models.entities.parse_result import (
    CellValue,
    ParseResult,
    TableBlock,
    TableRow,
)
from ..base import BaseMiddleware

logger = logging.getLogger(__name__)

MIN_BLOCKS = 6
MIN_ROWS = 2
MIN_COLS = 2
Y_GAP_MULT = 1.5
X_GAP_MULT = 3.0
X_GAP_MIN_FRAC = 0.02


@dataclass
class _Cell:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0


def _cluster_y(cells: list[_Cell]) -> list[list[_Cell]]:
    if not cells:
        return []
    sc = sorted(cells, key=lambda c: c.cy)
    mh = statistics.median([c.h for c in sc]) if len(sc) > 1 else 12
    th = max(4.0, mh * Y_GAP_MULT)
    lines: list[list[_Cell]] = [[sc[0]]]
    for c in sc[1:]:
        if c.cy - lines[-1][-1].cy < th:
            lines[-1].append(c)
        else:
            lines.append([c])
    return lines


def _split_x(line: list[_Cell]) -> list[list[_Cell]]:
    """Split cells into columns using GCR (Geometry Column Reconstruction).

    Uses Otsu-like gap clustering instead of the legacy fixed-threshold
    approach, which generalises better across varied page widths and
    font sizes.
    """
    from docmirror.structure.ocr.reconstruct.gcr import GCRColumns
    return GCRColumns.split_line(line)


def _build_grid(lines: list[list[_Cell]]) -> list[list[str]]:
    if len(lines) < MIN_ROWS:
        return []
    col_groups = [_split_x(ln) for ln in lines]
    mc = statistics.median([len(g) for g in col_groups])
    if mc >= MIN_COLS:
        # Normal case: multi-column per line
        grid: list[list[str]] = []
        for g in col_groups:
            if abs(len(g) - mc) > 2:
                continue
            grid.append([" ".join(c.text for c in col) for col in g])
        return grid

    # Fallback: single column per line — try splitting each line's
    # text by whitespace to detect columnar structure.  This handles
    # cases where QGE already merged all cells of a row into one block.
    col_counts = [len(ln[0].text.split()) for ln in lines if ln]
    if not col_counts:
        return []
    mc2 = statistics.median(col_counts)
    if mc2 < MIN_COLS:
        return []
    grid = []
    for ln in lines:
        parts = ln[0].text.split()
        if abs(len(parts) - mc2) > 2:
            continue
        grid.append(parts)
    return grid


def _to_table(grid: list[list[str]]) -> TableBlock | None:
    if not grid or len(grid) < 2:
        return None
    nc = max(len(r) for r in grid)
    norm = [r + [""] * (nc - len(r)) for r in grid]
    has_num = any(
        any(c.replace(",", "").replace(".", "").replace("-", "").strip().isdigit()
            for c in row if c.strip())
        for row in norm[1:4]
    )
    headers = norm[0] if has_num else []
    rows_raw = norm[1:] if has_num else norm
    rows = [TableRow(cells=[CellValue(text=str(c)) for c in r]) for r in rows_raw]
    return TableBlock(
        table_id="geo_table_0", headers=headers, rows=rows, page=1,
        confidence=0.85, extraction_layer="geometric_reconstructor",
        metadata={"source": "geometric_reconstructor"},
    )


class GeometricReconstructor(BaseMiddleware):
    """Reconstruct table structure from OCR text blocks using spatial geometry."""

    PROVIDES = ["tables"]

    def should_skip(self, result: ParseResult) -> bool:
        if not result.pages:
            return True
        if sum(len(p.tables) for p in result.pages) > 0:
            return True
        total = bbox = 0
        for p in result.pages:
            for t in p.texts:
                total += 1
                if t.bbox and len(t.bbox) == 4:
                    bbox += 1
        if total < MIN_BLOCKS:
            return True
        if bbox / max(1, total) < 0.8:
            return True
        return False

    def _extract_tokens_from_bundles(self, result: ParseResult) -> list[_Cell]:
        """Extract token-level cells from page evidence bundles (GA1.0-01)."""
        ds = result.entities.domain_specific or {}
        bundles = ds.get("_page_evidence_bundles") or []
        cells: list[_Cell] = []
        for bundle in bundles:
            for token_dict in bundle.get("tokens") or []:
                cell = self._token_to_cell(token_dict)
                if cell is not None:
                    cells.append(cell)
        return cells

    @staticmethod
    def _token_to_cell(token_dict: dict) -> _Cell | None:
        """Convert an OCR token dict (from evidence bundle) to a _Cell."""
        text = str(token_dict.get("text") or "").strip()
        if not text:
            return None
        bbox = token_dict.get("bbox")
        if not bbox or len(bbox) != 4:
            return None
        try:
            return _Cell(
                text=text,
                x0=float(bbox[0]),
                y0=float(bbox[1]),
                x1=float(bbox[2]),
                y1=float(bbox[3]),
            )
        except (TypeError, ValueError):
            return None

    def process(self, result: ParseResult) -> ParseResult:
        if self.should_skip(result):
            return result

        # GA1.0-01 change 3: Try token-level evidence first
        cells = self._extract_tokens_from_bundles(result)
        if not cells or len(cells) < MIN_BLOCKS:
            # Fall back to line-level texts
            cells = [
                _Cell(text=t.content, x0=t.bbox[0], y0=t.bbox[1], x1=t.bbox[2], y1=t.bbox[3])
                for p in result.pages for t in p.texts
                if t.bbox and len(t.bbox) == 4 and t.content.strip()
            ]
        # (if both sources fail, cells remains empty and we return early below)
        if len(cells) < MIN_BLOCKS:
            return result

        grid = _build_grid(_cluster_y(cells))
        if len(grid) < MIN_ROWS:
            return result

        table = _to_table(grid)
        if table is None:
            return result

        result.pages[0].tables.append(table)
        result.record_mutation(
            "GeometricReconstructor", target_block_id="pages",
            field_changed="tables", old_value=[], new_value=f"{len(grid)}r x {len(grid[0])}c",
            reason="geometric_reconstructor",
        )
        logger.info(f"[GeometricReconstructor] {len(grid)}r x {len(grid[0])}c from {len(cells)} blocks")
        return result
