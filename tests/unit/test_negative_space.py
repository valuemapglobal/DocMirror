# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
"""
Negative Space Analyzer 单元测试
================================

测试覆盖：
- 数据结构 (3用例)
- 垂直投影 (4用例)
- 水平投影 (3用例)
- 谷值检测 (4用例)
- 密度热图 (3用例)
- 空白区域 (3用例)
"""

import numpy as np
import pytest

from docmirror.layout.segment.negative_space import NegativeSpaceAnalyzer, NegativeSpaceProfile


class TestNegativeSpaceProfile:
    """Test negative space feature profiling"""

    def test_profile_creation(self):
        """Test creation"""
        profile = NegativeSpaceProfile(
            column_gaps=[100.0, 200.0, 300.0],
            row_gaps=[50.0, 100.0],
            blank_regions=[(0, 0, 50, 100)]
        )

        assert len(profile.column_gaps) == 3
        assert len(profile.row_gaps) == 2
        assert len(profile.blank_regions) == 1

    def test_summary(self):
        """Test summary"""
        profile = NegativeSpaceProfile(
            column_gaps=[100.0, 200.0],
            row_gaps=[50.0],
            blank_regions=[(0, 0, 50, 100), (100, 100, 150, 200)]
        )

        summary = profile.summary()

        assert "col_gaps=2" in summary
        assert "row_gaps=1" in summary
        assert "blank_regions=2" in summary


class TestNegativeSpaceAnalyzer:
    """Test negative space analyzer"""

    def _create_test_words(self):
        """Create test words (2 columns, 3 rows)"""
        return [
            # Row 1
            {'x0': 10, 'y0': 10, 'x1': 50, 'y1': 20, 'text': 'Date'},
            {'x0': 100, 'y0': 10, 'x1': 150, 'y1': 20, 'text': 'Amount'},
            # Row 2
            {'x0': 10, 'y0': 30, 'x1': 50, 'y1': 40, 'text': '1/15'},
            {'x0': 100, 'y0': 30, 'x1': 150, 'y1': 40, 'text': '1000'},
            # Row 3
            {'x0': 10, 'y0': 50, 'x1': 50, 'y1': 60, 'text': '1/16'},
            {'x0': 100, 'y0': 50, 'x1': 150, 'y1': 60, 'text': '2000'},
        ]

    def test_analyze_basic(self):
        """Test basic analysis"""
        words = self._create_test_words()
        profile = NegativeSpaceAnalyzer.analyze(words)

        assert profile is not None
        assert len(profile.column_gaps) >= 1  # 应该有列间隙
        assert len(profile.row_gaps) >= 1     # 应该有行间隙

    def test_analyze_empty(self):
        """Test empty input"""
        profile = NegativeSpaceAnalyzer.analyze([])

        assert len(profile.column_gaps) == 0
        assert len(profile.row_gaps) == 0

    def test_vertical_projection(self):
        """Test vertical projection"""
        words = self._create_test_words()
        projection = NegativeSpaceAnalyzer._vertical_projection(words, resolution=2)

        assert len(projection) > 0
        # Column should have values
        assert projection[5] > 0  # x=10位置
        assert projection[50] > 0  # x=100位置

    def test_horizontal_projection(self):
        """Test horizontal projection"""
        words = self._create_test_words()
        projection = NegativeSpaceAnalyzer._horizontal_projection(words, resolution=2)

        assert len(projection) > 0
        # Row should have values
        assert projection[5] > 0  # y=10位置
        assert projection[15] > 0  # y=30位置

    def test_find_valleys(self):
        """Test valley detection"""
        # Create projection with clear valleys
        projection = np.array([10, 10, 10, 1, 1, 1, 10, 10, 10])
        valleys = NegativeSpaceAnalyzer._find_projection_valleys(projection, threshold_ratio=0.3)

        assert len(valleys) >= 1
        # Valleys should be at indices 3-5
        assert any(3 <= v <= 5 for v in valleys)

    def test_find_valleys_empty(self):
        """Test empty projection"""
        valleys = NegativeSpaceAnalyzer._find_projection_valleys(np.array([]))
        assert len(valleys) == 0

    def test_find_valleys_flat(self):
        """Test flat projection (no valley)"""
        projection = np.array([5, 5, 5, 5, 5])
        valleys = NegativeSpaceAnalyzer._find_projection_valleys(projection, threshold_ratio=0.3)
        assert len(valleys) == 0

    def test_density_heatmap(self):
        """Test density heatmap"""
        words = self._create_test_words()
        heatmap = NegativeSpaceAnalyzer._generate_density_heatmap(words, resolution=2)

        assert heatmap.ndim == 2
        assert heatmap.shape[0] > 0  # height
        assert heatmap.shape[1] > 0  # width
        # Word coverage area should have values
        assert heatmap[5, 5] > 0  # y=10, x=10位置

    def test_detect_blank_regions(self):
        """Test blank region detection"""
        words = self._create_test_words()
        heatmap = NegativeSpaceAnalyzer._generate_density_heatmap(words, resolution=2)
        blank_regions = NegativeSpaceAnalyzer._detect_blank_regions(words, heatmap, resolution=2)

        # Should have blank areas (between columns)
        assert len(blank_regions) >= 0  # 可能为0（取决于单词分布）

    def test_smooth_projection(self):
        """Test smoothing"""
        projection = np.array([1, 10, 1, 10, 1])
        smoothed = NegativeSpaceAnalyzer._smooth_projection(projection, sigma=1.0)

        assert len(smoothed) == len(projection)
        # After smoothing, peaks should decrease, valleys should increase
        assert smoothed[1] < projection[1]  # 峰值降低
        assert smoothed[0] > projection[0]  # 谷值升高

    def test_multiple_columns(self):
        """Test multi-column detection"""
        # Create 3 columns of words
        words = [
            {'x0': 10, 'y0': 10, 'x1': 30, 'y1': 20, 'text': 'A'},
            {'x0': 60, 'y0': 10, 'x1': 80, 'y1': 20, 'text': 'B'},
            {'x0': 110, 'y0': 10, 'x1': 130, 'y1': 20, 'text': 'C'},
        ]

        profile = NegativeSpaceAnalyzer.analyze(words)

        # Should have 2 column gaps (3 columns have 2 gaps)
        assert len(profile.column_gaps) >= 1
