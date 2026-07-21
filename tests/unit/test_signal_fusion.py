"""Tests for signal fusion engine."""
from __future__ import annotations

import pytest

from docmirror.tables.signal_fusion import (
    FUSION_CONFIG,
    SIGNAL_WEIGHTS,
    fuse_column_signals,
    should_use_fusion,
)


class TestSignalFusion:
    """Test signal fusion engine."""

    def test_fuse_perfect_agreement(self):
        """Test fusion when all signals agree."""
        signals = {
            "header_anchors": [100.0, 200.0, 300.0, 400.0],
            "word_anchors": [100.5, 200.5, 300.5, 400.5],
            "data_voting": [99.5, 199.5, 299.5, 399.5],
            "whitespace_projection": [101.0, 201.0, 301.0, 401.0],
        }

        fused, confidence = fuse_column_signals(signals)

        assert len(fused) == 4
        assert confidence >= 0.8  # 高置信度
        # Boundaries should be around 100, 200, 300, 400
        assert 95 <= fused[0] <= 105
        assert 195 <= fused[1] <= 205
        assert 295 <= fused[2] <= 305
        assert 395 <= fused[3] <= 405

    def test_fuse_partial_agreement(self):
        """Test fusion when signals partially agree."""
        signals = {
            "header_anchors": [100.0, 200.0, 300.0],
            "word_anchors": [100.0, 200.0, 300.0],
            "data_voting": [100.0, 250.0, 300.0],  # 中间边界不同
        }

        fused, confidence = fuse_column_signals(signals)

        # Should have 2-3 boundaries (100 and 300 have 3 votes, 200/250 has split)
        assert len(fused) >= 2
        assert confidence >= 0.5  # 中置信度

    def test_fuse_no_agreement(self):
        """Test fusion when signals disagree."""
        signals = {
            "header_anchors": [100.0, 200.0, 300.0],
            "word_anchors": [150.0, 250.0, 350.0],  # 完全不同
            "data_voting": [120.0, 220.0, 320.0],
        }

        fused, confidence = fuse_column_signals(signals)

        # May not have enough votes
        assert confidence < 0.5  # 低置信度

    def test_fuse_single_signal(self):
        """Test fusion with only one signal source."""
        signals = {
            "header_anchors": [100.0, 200.0, 300.0],
        }

        fused, confidence = fuse_column_signals(signals)

        # Single source, cannot fuse
        assert len(fused) == 0 or confidence < 0.5

    def test_fuse_empty_signals(self):
        """Test fusion with empty signals."""
        signals = {}

        fused, confidence = fuse_column_signals(signals)

        assert len(fused) == 0
        assert confidence == 0.0

    def test_fuse_with_weights(self):
        """Test fusion with custom weights."""
        signals = {
            "header_anchors": [100.0, 200.0],
            "data_voting": [100.0, 200.0],
        }
        weights = {
            "header_anchors": 0.5,
            "data_voting": 0.5,
        }

        fused, confidence = fuse_column_signals(signals, weights=weights)

        assert len(fused) == 2
        assert confidence >= 0.7

    def test_fuse_cluster_tolerance(self):
        """Test boundary clustering with tolerance."""
        signals = {
            "header_anchors": [100.0, 100.1, 100.2],  # 应该聚类为一个
            "word_anchors": [100.3, 100.4],
        }

        fused, confidence = fuse_column_signals(signals)

        # All boundaries within tolerance, should cluster into one
        assert len(fused) == 1
        assert 99 <= fused[0] <= 101

    def test_fuse_outlier_removal(self):
        """Test outlier boundary removal."""
        signals = {
            "header_anchors": [100.0, 200.0, 300.0],
            "word_anchors": [100.0, 200.0, 300.0],
            "data_voting": [100.0, 200.0, 300.0],
            "whitespace_projection": [500.0],  # 孤立点
        }

        fused, confidence = fuse_column_signals(signals)

        # 500.0 should be removed (only 1 vote)
        assert 500.0 not in fused
        assert len(fused) == 3

    def test_fuse_deterministic(self):
        """Test fusion is deterministic."""
        signals = {
            "header_anchors": [100.0, 200.0, 300.0],
            "word_anchors": [100.5, 200.5, 300.5],
            "data_voting": [99.5, 199.5, 299.5],
        }

        fused1, conf1 = fuse_column_signals(signals)
        fused2, conf2 = fuse_column_signals(signals)

        assert fused1 == fused2
        assert conf1 == conf2


class TestFusionDecision:
    """Test fusion decision logic."""

    def test_high_confidence(self):
        """Test high confidence decision."""
        decision = should_use_fusion(0.85)
        assert decision == "use_fusion"

    def test_medium_confidence(self):
        """Test medium confidence decision."""
        decision = should_use_fusion(0.65)
        assert decision == "verify_with_signal"

    def test_low_confidence(self):
        """Test low confidence decision."""
        decision = should_use_fusion(0.3)
        assert decision == "fallback"

    def test_boundary_high(self):
        """Test boundary between high and medium."""
        decision = should_use_fusion(0.8)
        assert decision == "use_fusion"

    def test_boundary_medium(self):
        """Test boundary between medium and low."""
        decision = should_use_fusion(0.5)
        assert decision == "verify_with_signal"


class TestSignalWeights:
    """Test signal weight configuration."""

    def test_default_weights_sum_to_one(self):
        """Test default weights sum to 1.0."""
        total = sum(SIGNAL_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_data_voting_highest_weight(self):
        """Test data_voting has highest weight."""
        assert SIGNAL_WEIGHTS["data_voting"] == 0.30
        assert SIGNAL_WEIGHTS["data_voting"] > SIGNAL_WEIGHTS["header_anchors"]
        assert SIGNAL_WEIGHTS["data_voting"] > SIGNAL_WEIGHTS["word_anchors"]
        assert SIGNAL_WEIGHTS["data_voting"] > SIGNAL_WEIGHTS["whitespace_projection"]

    def test_all_methods_have_weights(self):
        """Test all methods have weights."""
        expected_methods = {"header_anchors", "word_anchors", "data_voting", "whitespace_projection"}
        assert set(SIGNAL_WEIGHTS.keys()) == expected_methods


class TestFusionConfig:
    """Test fusion configuration."""

    def test_cluster_tolerance_reasonable(self):
        """Test cluster tolerance is reasonable."""
        assert 3.0 <= FUSION_CONFIG["cluster_tolerance"] <= 10.0

    def test_min_votes_reasonable(self):
        """Test minimum votes is reasonable."""
        assert 2 <= FUSION_CONFIG["min_votes"] <= 3

    def test_thresholds_ordered(self):
        """Test confidence thresholds are properly ordered."""
        assert FUSION_CONFIG["high_confidence_threshold"] > FUSION_CONFIG["medium_confidence_threshold"]
        assert FUSION_CONFIG["medium_confidence_threshold"] > FUSION_CONFIG["outlier_threshold"]
