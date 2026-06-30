# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
"""
Result Fusion Engine 单元测试
==============================

测试覆盖：
- 数据融合 (5用例)
- 表头投票 (4用例)
- 列边界合并 (3用例)
- 表格选择 (3用例)
- 置信度校准 (4用例)
- 边界条件 (3用例)
"""

import pytest
from docmirror.tables.fusion import ResultFusionEngine


# ═══════════════════════════════════════════════════════════════════════════════
# Test Result Fusion
# ═══════════════════════════════════════════════════════════════════════════════

class TestResultFusion:
    """Test result fusion"""
    
    def test_fuse_empty_results(self):
        """Test empty result fusion"""
        result = ResultFusionEngine.fuse([])
        
        assert result['tables'] == []
        assert result['confidence'] == 0.0
    
    def test_fuse_single_result(self):
        """Test single result (no fusion needed)"""
        result = {
            'tables': [{'header': ['A', 'B'], 'rows': []}],
            'confidence': 0.85,
            'metadata': {}
        }
        
        fused = ResultFusionEngine.fuse([result])
        
        assert fused == result
    
    def test_fuse_multiple_results(self):
        """Test multi-result fusion"""
        results = [
            {'tables': [{'header': ['A', 'B'], 'rows': []}], 'confidence': 0.80, 'metadata': {}},
            {'tables': [{'header': ['A', 'B'], 'rows': []}], 'confidence': 0.75, 'metadata': {}},
            {'tables': [{'header': ['A', 'B'], 'rows': []}], 'confidence': 0.82, 'metadata': {}},
        ]
        
        fused = ResultFusionEngine.fuse(results)
        
        assert fused['confidence'] > 0.80  # 融合后应高于最佳单一结果
        assert 'fusion' in fused['metadata']
    
    def test_fuse_metadata(self):
        """Test fusion metadata"""
        results = [
            {'tables': [{'header': ['A', 'B']}], 'confidence': 0.80},
            {'tables': [{'header': ['A', 'B']}], 'confidence': 0.85},
        ]
        
        fused = ResultFusionEngine.fuse(results)
        
        assert fused['metadata']['fusion']['fusion_method'] == 'weighted_consensus'
        assert fused['metadata']['fusion']['layer_count'] == 2
    
    def test_fuse_fallback_on_error(self):
        """Test fallback to best result on exception"""
        results = [
            {'tables': [], 'confidence': 0.50},
            {'tables': [{'header': ['A']}], 'confidence': 0.80},
        ]
        
        fused = ResultFusionEngine.fuse(results)
        
        # On downgrade, should return highest confidence result (close to 0.80)
        assert fused['confidence'] >= 0.70  # 允许融合计算导致的差异


# ═══════════════════════════════════════════════════════════════════════════════
# Test Header Voting
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeaderVoting:
    """Test header voting"""
    
    def test_vote_unanimous(self):
        """Test unanimous voting (all layers identify same row)"""
        results = [
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}], 'confidence': 0.80},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}], 'confidence': 0.85},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}], 'confidence': 0.82},
        ]
        
        header = ResultFusionEngine._vote_header(results)
        
        assert header['row_index'] == 0
        assert header['votes'] == 3
    
    def test_vote_majority(self):
        """Test majority voting"""
        results = [
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}], 'confidence': 0.80},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}], 'confidence': 0.85},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 1}}}], 'confidence': 0.82},
        ]
        
        header = ResultFusionEngine._vote_header(results)
        
        assert header['row_index'] == 0  # 2票胜出
        assert header['votes'] == 2
    
    def test_vote_no_headers(self):
        """Test no header identification"""
        results = [
            {'tables': [], 'confidence': 0.80},
            {'tables': [], 'confidence': 0.85},
        ]
        
        header = ResultFusionEngine._vote_header(results)
        
        assert header['row_index'] == 0
        assert header['votes'] == 0
    
    def test_vote_with_confidence(self):
        """Test confidence-weighted voting"""
        results = [
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}], 'confidence': 0.60},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 1}}}], 'confidence': 0.90},
        ]
        
        header = ResultFusionEngine._vote_header(results)
        
        # Both have 1 vote, but row 1 has higher confidence
        assert header['row_index'] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Test Column Boundary Merging
# ═══════════════════════════════════════════════════════════════════════════════

class TestColumnMerging:
    """Test column boundary merging"""
    
    def test_merge_same_columns(self):
        """Test same-column-count merging"""
        results = [
            {
                'tables': [{'metadata': {'column_boundaries': [100.0, 200.0, 300.0]}}],
                'confidence': 0.80
            },
            {
                'tables': [{'metadata': {'column_boundaries': [105.0, 205.0, 305.0]}}],
                'confidence': 0.85
            },
        ]
        
        fused = ResultFusionEngine._merge_column_boundaries(results)
        
        assert len(fused) == 3
        assert 100.0 <= fused[0] <= 105.0  # 加权平均
        assert 200.0 <= fused[1] <= 205.0
    
    def test_merge_different_columns(self):
        """Test different-column-count merging"""
        results = [
            {
                'tables': [{'metadata': {'column_boundaries': [100.0, 200.0]}}],
                'confidence': 0.80
            },
            {
                'tables': [{'metadata': {'column_boundaries': [105.0, 205.0, 305.0]}}],
                'confidence': 0.85
            },
        ]
        
        fused = ResultFusionEngine._merge_column_boundaries(results)
        
        # Should take the maximum column count
        assert len(fused) == 3
    
    def test_merge_no_boundaries(self):
        """Test no column boundaries"""
        results = [
            {'tables': [{'metadata': {}}], 'confidence': 0.80},
            {'tables': [{'metadata': {}}], 'confidence': 0.85},
        ]
        
        fused = ResultFusionEngine._merge_column_boundaries(results)
        
        assert fused == []


# ═══════════════════════════════════════════════════════════════════════════════
# Test Confidence Calibration
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfidenceCalibration:
    """Test confidence calibration"""
    
    def test_calibrate_unanimous(self):
        """Test confidence boost on perfect match"""
        results = [
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}], 'confidence': 0.80},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}], 'confidence': 0.85},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}], 'confidence': 0.82},
        ]
        
        fused_conf = ResultFusionEngine._calibrate_confidence(results)
        
        best_single = 0.85
        assert fused_conf > best_single  # 一致时应该提升
        assert fused_conf <= 1.0
    
    def test_calibrate_divergent(self):
        """Test confidence on result divergence"""
        results = [
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}], 'confidence': 0.80},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 1}}}], 'confidence': 0.85},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 2}}}], 'confidence': 0.82},
        ]
        
        fused_conf = ResultFusionEngine._calibrate_confidence(results)
        
        # Should not have extra bonus for disagreement
        assert fused_conf <= 0.85 + 0.05  # 不超过best + bonus
    
    def test_calibrate_single_result(self):
        """Test single result"""
        results = [{'tables': [], 'confidence': 0.75}]
        
        fused_conf = ResultFusionEngine._calibrate_confidence(results)
        
        assert fused_conf == 0.75
    
    def test_calibrate_bounds(self):
        """Test confidence boundaries"""
        results = [
            {'tables': [], 'confidence': 0.99},
            {'tables': [], 'confidence': 0.98},
        ]
        
        fused_conf = ResultFusionEngine._calibrate_confidence(results)
        
        assert 0.0 <= fused_conf <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Test Agreement Score
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgreementScore:
    """Test consistency score"""
    
    def test_agreement_unanimous(self):
        """Test full consistency"""
        results = [
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}]},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}]},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}]},
        ]
        
        score = ResultFusionEngine._calculate_agreement_score(results)
        
        assert score == 1.0
    
    def test_agreement_majority(self):
        """Test majority consistency"""
        results = [
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}]},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 0}}}]},
            {'tables': [{'metadata': {'header_inference': {'header_row_index': 1}}}]},
        ]
        
        score = ResultFusionEngine._calculate_agreement_score(results)
        
        assert score == pytest.approx(2/3, abs=0.01)
    
    def test_agreement_single(self):
        """Test single result"""
        results = [{'tables': []}]
        
        score = ResultFusionEngine._calculate_agreement_score(results)
        
        assert score == 1.0
