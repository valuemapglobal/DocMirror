"""
Tests for GeometricReconstructor middleware.

Unit tests cover:
  - Y-line clustering
  - X-column splitting
  - Full grid reconstruction
  - should_skip logic
  - Integration with mocked ParseResult
"""

from __future__ import annotations

import pytest

from docmirror.framework.middlewares.extraction.geometric_reconstructor import (
    GeometricReconstructor,
    _build_grid,
    _Cell,
    _cluster_y,
    _split_x,
    _to_table,
)
from docmirror.models.entities.parse_result import (
    CellValue,
    PageContent,
    ParseResult,
    TableBlock,
    TableRow,
    TextBlock,
)

pytestmark = [pytest.mark.tier_unit]


# ── Core algorithm tests ──


class TestClusterY:
    """Verify Y-line clustering groups vertically-proximate cells."""

    def test_single_line(self):
        """Cells with similar Y → one line."""
        cells = [
            _Cell("a", 0, 100, 50, 120),
            _Cell("b", 60, 100, 110, 120),
            _Cell("c", 120, 101, 170, 121),
        ]
        lines = _cluster_y(cells)
        assert len(lines) == 1

    def test_two_lines(self):
        """Cells far apart in Y → two lines."""
        cells = [
            _Cell("h1", 0, 100, 50, 120),
            _Cell("h2", 60, 100, 110, 120),
            _Cell("d1", 0, 200, 50, 220),
            _Cell("d2", 60, 200, 110, 220),
        ]
        lines = _cluster_y(cells)
        assert len(lines) == 2

    def test_three_lines(self):
        """Three distinct Y groups."""
        cells = [
            _Cell(f"r{i}c{j}", j * 60, 100 + i * 100, j * 60 + 50, 100 + i * 100 + 20)
            for i in range(3) for j in range(2)
        ]
        lines = _cluster_y(cells)
        assert len(lines) == 3


class TestSplitX:
    """Verify X-column splitting detects column boundaries."""

    def test_single_column(self):
        """Cells close together → one column."""
        line = [
            _Cell("a", 0, 100, 50, 120),
            _Cell("b", 55, 100, 110, 120),
        ]
        cols = _split_x(line)
        assert len(cols) == 1

    def test_two_columns(self):
        """Cells with large X gap → two columns."""
        line = [
            _Cell("date", 0, 100, 80, 120),
            _Cell("amount", 300, 100, 400, 120),
        ]
        cols = _split_x(line)
        assert len(cols) == 2

    def test_three_columns(self):
        """Three distinct X groups."""
        line = [
            _Cell("a", 0, 100, 50, 120),
            _Cell("b", 300, 100, 350, 120),
            _Cell("c", 600, 100, 650, 120),
        ]
        cols = _split_x(line)
        assert len(cols) == 3


class TestBuildGrid:
    """Verify grid construction from Y-lines."""

    def test_2x2_table(self):
        """Two rows, two columns → valid grid."""
        cells = [
            _Cell("h1", 0, 100, 80, 120), _Cell("h2", 300, 100, 380, 120),
            _Cell("d1", 0, 200, 80, 220), _Cell("d2", 300, 200, 380, 220),
        ]
        grid = _build_grid(_cluster_y(cells))
        assert len(grid) == 2
        assert len(grid[0]) == 2

    def test_too_few_rows(self):
        """Fewer than MIN_ROWS → empty grid."""
        cells = [
            _Cell("a", 0, 100, 50, 120),
            _Cell("b", 300, 100, 350, 120),
        ]
        grid = _build_grid(_cluster_y(cells))
        assert grid == []


# ── Table construction tests ──

class TestToTable:
    """Verify _to_table builds valid TableBlock."""

    def test_basic_table(self):
        """2-column grid → TableBlock with headers and rows."""
        grid = [["日期", "金额"], ["2024-01-01", "100.00"]]
        table = _to_table(grid)
        assert table is not None
        assert table.headers == ["日期", "金额"]
        assert len(table.rows) == 1
        assert table.rows[0].cells[0].text == "2024-01-01"

    def test_infer_header_by_numeric_data(self):
        """Numeric data in rows → first row treated as header."""
        grid = [["Date", "Amount"], ["2024-01-01", "500"], ["2024-01-02", "300"]]
        table = _to_table(grid)
        assert table is not None
        assert table.headers == ["Date", "Amount"]


# ── should_skip tests ──

class TestShouldSkip:
    """Verify should_skip logic."""

    def test_skip_when_no_pages(self):
        """No pages → skip."""
        g = GeometricReconstructor()
        assert g.should_skip(ParseResult(pages=[])) is True

    def test_skip_when_tables_exist(self):
        """Tables already present → skip."""
        g = GeometricReconstructor()
        r = ParseResult(pages=[PageContent(
            page_number=1,
            tables=[TableBlock(table_id="t1", headers=["h"], rows=[TableRow(cells=[CellValue(text="v")])])],
        )])
        assert g.should_skip(r) is True

    def test_skip_when_few_blocks(self):
        """Fewer than MIN_BLOCKS → skip."""
        g = GeometricReconstructor()
        r = ParseResult(pages=[PageContent(page_number=1)])
        assert g.should_skip(r) is True

    def test_not_skip_with_enough_bbox_blocks(self):
        """Enough blocks with bbox → do NOT skip."""
        g = GeometricReconstructor()
        blocks = [TextBlock(content=f"t{i}", bbox=[i*50, 100, i*50+40, 120]) for i in range(8)]
        r = ParseResult(pages=[PageContent(page_number=1, texts=blocks)])
        assert g.should_skip(r) is False


# ── Integration test ──

class TestProcess:
    """Verify process() reconstructs tables from text blocks."""

    def test_reconstructs_table_from_bbox_data(self):
        """8 blocks forming 2 rows × 4 cols → table injected."""
        blocks = []
        for row in range(2):
            for col in range(4):
                blocks.append(TextBlock(
                    content=f"r{row}c{col}",
                    bbox=[col * 80, 100 + row * 50, col * 80 + 60, 100 + row * 50 + 30],
                ))
        r = ParseResult(pages=[PageContent(page_number=1, texts=blocks)])
        g = GeometricReconstructor()
        result = g.process(r)
        assert len(result.pages[0].tables) == 1
        table = result.pages[0].tables[0]
        assert len(table.headers) > 0 or len(table.rows) > 0

    def test_no_table_when_blocks_misaligned(self):
        """Random bbox positions → no table."""
        blocks = [TextBlock(content=str(i), bbox=[i * 30, i * 40, i * 30 + 20, i * 40 + 15]) for i in range(10)]
        r = ParseResult(pages=[PageContent(page_number=1, texts=blocks)])
        g = GeometricReconstructor()
        result = g.process(r)
        assert len(result.pages[0].tables) == 0
