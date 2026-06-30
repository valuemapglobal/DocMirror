"""Tests for cross-page table predictor."""
from __future__ import annotations

import pytest

from docmirror.tables.cross_page_predictor import (
    CrossPageTablePredictor,
    NextPagePrediction,
    TruncationInfo,
)


class TestTruncationInfo:
    """Test TruncationInfo dataclass."""

    def test_default_values(self):
        info = TruncationInfo()
        assert info.incomplete_rows == 0
        assert info.col_count == 0
        assert info.col_types == []
        assert info.has_trailing_continuation is False


class TestNextPagePrediction:
    """Test NextPagePrediction dataclass."""

    def test_default_values(self):
        pred = NextPagePrediction()
        assert pred.predicted_col_count == 0
        assert pred.confidence == 0.0
        assert pred.predicted_merge_pattern == "unknown"

    def test_col_count_property(self):
        pred = NextPagePrediction(predicted_col_count=5)
        assert pred.col_count == 5


class TestCrossPageTablePredictor:
    """Test CrossPageTablePredictor."""

    def test_init(self):
        predictor = CrossPageTablePredictor(confidence_threshold=0.8)
        assert predictor.confidence_threshold == 0.8

    def test_record_truncation_basic(self, mock_page_layout, mock_extraction_result):
        """Test basic truncation recording."""
        predictor = CrossPageTablePredictor()
        info = predictor.record_truncation(mock_page_layout, mock_extraction_result, page_idx=0)

        assert info.page_idx == 0
        assert info.col_count >= 0
        assert isinstance(info.incomplete_rows, int)

    def test_predict_next_page(self):
        """Test next page prediction."""
        predictor = CrossPageTablePredictor()
        truncation = TruncationInfo(
            col_count=5,
            col_types=["text", "currency", "date", "number", "text"],
            has_trailing_continuation=True,
            incomplete_rows=1,
        )

        prediction = predictor.predict_next_page(truncation)

        assert prediction.predicted_col_count == 5
        assert prediction.predicted_col_types == ["text", "currency", "date", "number", "text"]
        assert prediction.predicted_merge_pattern == "append"  # 有延续标记
        assert prediction.confidence > 0.7  # 应该高置信度

    def test_predict_next_page_no_continuation(self):
        """Test prediction without continuation markers."""
        predictor = CrossPageTablePredictor()
        truncation = TruncationInfo(
            col_count=3,
            col_types=["text", "number", "date"],
            has_trailing_continuation=False,
            incomplete_rows=0,
        )

        prediction = predictor.predict_next_page(truncation)

        assert prediction.predicted_col_count == 3
        assert prediction.predicted_merge_pattern == "new_table"  # 无延续标记

    def test_validate_merge_perfect_match(self):
        """Test validation with perfect match."""
        predictor = CrossPageTablePredictor()
        truncation = TruncationInfo(
            col_count=5,
            col_types=["text", "currency", "date", "number", "text"],
            has_trailing_continuation=True,
            incomplete_rows=1,
        )

        # Mock next page result with same structure
        next_result = self._mock_result_with_columns(5)

        validation = predictor.validate_merge(truncation, next_result)

        assert validation.is_valid is True
        assert validation.score >= 0.8
        assert "Column count exact match" in validation.reasons

    def test_validate_merge_col_mismatch(self):
        """Test validation with column mismatch."""
        predictor = CrossPageTablePredictor()
        truncation = TruncationInfo(
            col_count=5,
            col_types=["text", "currency", "date", "number", "text"],
        )

        # Mock next page result with different column count
        next_result = self._mock_result_with_columns(8)

        validation = predictor.validate_merge(truncation, next_result)

        assert validation.is_valid is False  # 列数差异过大
        assert any("Column count diff too large" in r for r in validation.reasons)

    def test_validate_merge_partial_match(self):
        """Test validation with partial match."""
        predictor = CrossPageTablePredictor()
        truncation = TruncationInfo(
            col_count=5,
            col_types=["text", "currency", "date", "number", "text"],
        )

        # Mock next page result with 1 column difference
        next_result = self._mock_result_with_columns(6)

        validation = predictor.validate_merge(truncation, next_result)

        # Should have warning about column difference
        assert validation.score >= 0.3  # 降低阈值
        assert any("Column count diff of 1" in w for w in validation.warnings)

    def test_validate_table_row_boundary_merge_stable(self):
        """Median boundary verification passes when cross-page geometry is stable."""
        predictor = CrossPageTablePredictor()
        prev_rows = [_bbox_row(["A", "B", "C"], 0)]
        next_rows = [_bbox_row(["1", "2", "3"], 2)]

        validation = predictor.validate_table_row_boundary_merge(prev_rows, next_rows)

        assert validation.is_valid is True
        assert validation.score >= 0.85
        assert any("Column boundaries stable" in reason for reason in validation.reasons)

    def test_validate_table_row_boundary_merge_flags_drift(self):
        """Median boundary verification flags pages whose columns drift too far."""
        predictor = CrossPageTablePredictor()
        prev_rows = [_bbox_row(["A", "B", "C"], 0)]
        next_rows = [_bbox_row(["1", "2", "3"], 20)]

        validation = predictor.validate_table_row_boundary_merge(prev_rows, next_rows)

        assert validation.is_valid is False
        assert any("Column boundary deviation too large" in warning for warning in validation.warnings)

    def test_reset(self):
        """Test reset functionality."""
        predictor = CrossPageTablePredictor()
        truncation = TruncationInfo(col_count=5)
        # Don't record truncation, predict directly
        predictor.predict_next_page(truncation)

        predictor.reset()

        assert predictor._state is None
        assert len(predictor.get_prediction_history()) == 0

    def test_prediction_history(self):
        """Test prediction history tracking."""
        predictor = CrossPageTablePredictor()

        for i in range(3):
            truncation = TruncationInfo(col_count=5, page_idx=i)
            # Don't record truncation, predict directly
            predictor.predict_next_page(truncation)

        history = predictor.get_prediction_history()
        assert len(history) == 3
        assert all(isinstance(h[0], TruncationInfo) for h in history)
        assert all(isinstance(h[1], NextPagePrediction) for h in history)

    def test_confidence_calculation_high(self):
        """Test high confidence scenario."""
        predictor = CrossPageTablePredictor()
        truncation = TruncationInfo(
            col_count=5,
            col_types=["text", "currency", "date"],
            has_trailing_continuation=True,
            incomplete_rows=2,
        )

        prediction = predictor.predict_next_page(truncation)

        assert prediction.confidence >= 0.8  # 多项指标都满足

    def test_confidence_calculation_low(self):
        """Test low confidence scenario."""
        predictor = CrossPageTablePredictor()
        truncation = TruncationInfo(
            col_count=0,  # 未知列数
            col_types=[],
            has_trailing_continuation=False,
            incomplete_rows=0,
        )

        prediction = predictor.predict_next_page(truncation)

        assert prediction.confidence < 0.7  # 基础置信度
        assert len(prediction.warnings) > 0

    # ========== Helper Methods ==========

    def _mock_result_with_columns(self, col_count: int):
        """Mock extraction result with specified column count."""
        class MockColumn:
            def __init__(self, name: str):
                self.data = {"name": name}

            def get(self, key, default=None):
                return self.data.get(key, default)

        class MockTable:
            def __init__(self, count: int):
                self.columns = [MockColumn(f"col_{i}") for i in range(count)]

        class MockResult:
            def __init__(self, count: int):
                self.structured_data = [MockTable(count)]

        return MockResult(col_count)


# ========== Fixtures ==========

@pytest.fixture
def mock_page_layout():
    """Mock PageLayout for testing."""
    from docmirror.models.entities.domain import PageLayout

    class MockBlock:
        def __init__(self):
            self.block_type = type('obj', (object,), {'value': 'table'})
            self.text = "row1|data1|data2\nrow2|data3|data4"

    class MockPage:
        def __init__(self):
            self.blocks = [MockBlock()]

    return MockPage()


@pytest.fixture
def mock_extraction_result():
    """Mock extraction result for testing."""
    class MockColumn:
        def __init__(self, name: str):
            self.data = {"name": name}

        def get(self, key, default=None):
            return self.data.get(key, default)

    class MockTable:
        def __init__(self):
            self.columns = [
                MockColumn("日期"),
                MockColumn("交易金额"),
                MockColumn("余额"),
            ]

    class MockResult:
        def __init__(self):
            self.structured_data = [MockTable()]

    return MockResult()


def _bbox_row(values: list[str], shift: float):
    from docmirror.models.entities.parse_result import CellValue, TableRow

    cells = []
    for index, value in enumerate(values):
        x0 = shift + index * 50.0
        cells.append(
            CellValue(
                text=value,
                row_index=0,
                col_index=index,
                bbox=[x0, 0.0, x0 + 40.0, 10.0],
            )
        )
    return TableRow(cells=cells)
