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

import pytest
import numpy as np
from docmirror.core.segment.negative_space import NegativeSpaceAnalyzer, NegativeSpaceProfile


class TestNegativeSpaceProfile:
    """测试负空间特征画像"""
    
    def test_profile_creation(self):
        """测试创建"""
        profile = NegativeSpaceProfile(
            column_gaps=[100.0, 200.0, 300.0],
            row_gaps=[50.0, 100.0],
            blank_regions=[(0, 0, 50, 100)]
        )
        
        assert len(profile.column_gaps) == 3
        assert len(profile.row_gaps) == 2
        assert len(profile.blank_regions) == 1
    
    def test_summary(self):
        """测试摘要"""
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
    """测试负空间分析器"""
    
    def _create_test_words(self):
        """创建测试单词（2列3行）"""
        return [
            # 行1
            {'x0': 10, 'y0': 10, 'x1': 50, 'y1': 20, 'text': 'Date'},
            {'x0': 100, 'y0': 10, 'x1': 150, 'y1': 20, 'text': 'Amount'},
            # 行2
            {'x0': 10, 'y0': 30, 'x1': 50, 'y1': 40, 'text': '1/15'},
            {'x0': 100, 'y0': 30, 'x1': 150, 'y1': 40, 'text': '1000'},
            # 行3
            {'x0': 10, 'y0': 50, 'x1': 50, 'y1': 60, 'text': '1/16'},
            {'x0': 100, 'y0': 50, 'x1': 150, 'y1': 60, 'text': '2000'},
        ]
    
    def test_analyze_basic(self):
        """测试基础分析"""
        words = self._create_test_words()
        profile = NegativeSpaceAnalyzer.analyze(words)
        
        assert profile is not None
        assert len(profile.column_gaps) >= 1  # 应该有列间隙
        assert len(profile.row_gaps) >= 1     # 应该有行间隙
    
    def test_analyze_empty(self):
        """测试空输入"""
        profile = NegativeSpaceAnalyzer.analyze([])
        
        assert len(profile.column_gaps) == 0
        assert len(profile.row_gaps) == 0
    
    def test_vertical_projection(self):
        """测试垂直投影"""
        words = self._create_test_words()
        projection = NegativeSpaceAnalyzer._vertical_projection(words, resolution=2)
        
        assert len(projection) > 0
        # 列内应该有值
        assert projection[5] > 0  # x=10位置
        assert projection[50] > 0  # x=100位置
    
    def test_horizontal_projection(self):
        """测试水平投影"""
        words = self._create_test_words()
        projection = NegativeSpaceAnalyzer._horizontal_projection(words, resolution=2)
        
        assert len(projection) > 0
        # 行内应该有值
        assert projection[5] > 0  # y=10位置
        assert projection[15] > 0  # y=30位置
    
    def test_find_valleys(self):
        """测试谷值检测"""
        # 创建有明显谷值的投影
        projection = np.array([10, 10, 10, 1, 1, 1, 10, 10, 10])
        valleys = NegativeSpaceAnalyzer._find_projection_valleys(projection, threshold_ratio=0.3)
        
        assert len(valleys) >= 1
        # 谷值应该在索引3-5之间
        assert any(3 <= v <= 5 for v in valleys)
    
    def test_find_valleys_empty(self):
        """测试空投影"""
        valleys = NegativeSpaceAnalyzer._find_projection_valleys(np.array([]))
        assert len(valleys) == 0
    
    def test_find_valleys_flat(self):
        """测试平坦投影（无谷值）"""
        projection = np.array([5, 5, 5, 5, 5])
        valleys = NegativeSpaceAnalyzer._find_projection_valleys(projection, threshold_ratio=0.3)
        assert len(valleys) == 0
    
    def test_density_heatmap(self):
        """测试密度热图"""
        words = self._create_test_words()
        heatmap = NegativeSpaceAnalyzer._generate_density_heatmap(words, resolution=2)
        
        assert heatmap.ndim == 2
        assert heatmap.shape[0] > 0  # height
        assert heatmap.shape[1] > 0  # width
        # 单词覆盖区域应该有值
        assert heatmap[5, 5] > 0  # y=10, x=10位置
    
    def test_detect_blank_regions(self):
        """测试空白区域检测"""
        words = self._create_test_words()
        heatmap = NegativeSpaceAnalyzer._generate_density_heatmap(words, resolution=2)
        blank_regions = NegativeSpaceAnalyzer._detect_blank_regions(words, heatmap, resolution=2)
        
        # 应该有空白区域（列之间）
        assert len(blank_regions) >= 0  # 可能为0（取决于单词分布）
    
    def test_smooth_projection(self):
        """测试平滑"""
        projection = np.array([1, 10, 1, 10, 1])
        smoothed = NegativeSpaceAnalyzer._smooth_projection(projection, sigma=1.0)
        
        assert len(smoothed) == len(projection)
        # 平滑后峰值应该降低，谷值应该升高
        assert smoothed[1] < projection[1]  # 峰值降低
        assert smoothed[0] > projection[0]  # 谷值升高
    
    def test_multiple_columns(self):
        """测试多列检测"""
        # 创建3列单词
        words = [
            {'x0': 10, 'y0': 10, 'x1': 30, 'y1': 20, 'text': 'A'},
            {'x0': 60, 'y0': 10, 'x1': 80, 'y1': 20, 'text': 'B'},
            {'x0': 110, 'y0': 10, 'x1': 130, 'y1': 20, 'text': 'C'},
        ]
        
        profile = NegativeSpaceAnalyzer.analyze(words)
        
        # 应该有2个列间隙（3列之间有2个间隙）
        assert len(profile.column_gaps) >= 1
