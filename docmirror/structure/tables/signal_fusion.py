"""
Signal fusion — votes among multiple column boundary signals.

Purpose: Clusters and fuses column boundary candidates from projection,
clustering, and anchor detectors into consensus dividers.

Main components: ``fuse_column_signals``, ``should_use_fusion``.

Upstream: Multiple column signal lists from extract char modules.

Downstream: ``extract.char_strategy`` final boundaries.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Signal source weight configuration
SIGNAL_WEIGHTS = {
    "header_anchors": 0.25,
    "word_anchors": 0.25,
    "data_voting": 0.30,
    "whitespace_projection": 0.20,
}

# Fusion parameters
FUSION_CONFIG = {
    "cluster_tolerance": 5.0,  # boundary clustering tolerance (pt)
    "min_votes": 2,  # minimum votes
    "high_confidence_threshold": 0.8,
    "medium_confidence_threshold": 0.5,
    "outlier_threshold": 0.3,  # outlier threshold
}


def fuse_column_signals(
    signals: dict[str, list[float]],
    weights: dict[str, float] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[list[float], float]:
    """Fuse multi-source column boundary signals.

    Args:
        signals: Signal source dict {method_name: [boundary_positions]}
        weights: Signal weight dict (optional, defaults to SIGNAL_WEIGHTS)
        config: Fusion config dict (optional, defaults to FUSION_CONFIG)

    Returns:
        (fused_boundaries, confidence): Fused boundary list and confidence score
    """
    weights = weights or SIGNAL_WEIGHTS
    config = config or FUSION_CONFIG

    # 1. Collect all boundary candidates
    all_candidates = _collect_candidates(signals, weights)

    if not all_candidates:
        return [], 0.0

    # 2. Cluster nearby boundaries (±tolerance)
    clusters = _cluster_boundaries(all_candidates, config["cluster_tolerance"])

    # 3. Compute weighted vote per cluster
    voted_boundaries = _vote_clusters(clusters, weights, config)

    if not voted_boundaries:
        return [], 0.0

    # 4. Denoise (remove low-vote boundaries)
    clean_boundaries = _remove_outliers(voted_boundaries, config)

    # 5. Compute overall confidence
    confidence = _calculate_confidence(clean_boundaries, weights)

    logger.debug(f"Signal fusion: {len(signals)} sources -> {len(clean_boundaries)} boundaries, confidence={confidence:.2f}")

    return sorted(clean_boundaries), confidence


def should_use_fusion(confidence: float, config: dict[str, Any] | None = None) -> str:
    """Decide whether to use the fusion result.

    Args:
        confidence: Fusion confidence score
        config: Configuration dict

    Returns:
        "use_fusion": Use the fusion result directly
        "verify_with_signal": Verify with signal processor
        "fallback": Fall back to a single method
    """
    config = config or FUSION_CONFIG

    if confidence >= config["high_confidence_threshold"]:
        return "use_fusion"
    elif confidence >= config["medium_confidence_threshold"]:
        return "verify_with_signal"
    else:
        return "fallback"


# ========== Private Methods ==========


def _collect_candidates(signals: dict[str, list[float]], weights: dict[str, float]) -> list[tuple[float, str, float]]:
    """Collect all boundary candidates.

    Returns:
        [(boundary_pos, method_name, weight), ...]
    """
    candidates = []

    for method_name, boundaries in signals.items():
        if not boundaries:
            continue

        weight = weights.get(method_name, 0.1)  # default weight 0.1

        for boundary in boundaries:
            candidates.append((boundary, method_name, weight))

    logger.debug(f"Collected {len(candidates)} boundary candidates")
    return candidates


def _cluster_boundaries(
    candidates: list[tuple[float, str, float]], tolerance: float
) -> list[list[tuple[float, str, float]]]:
    """Cluster nearby boundaries (±tolerance).

    Algorithm: Greedy clustering. Sort by position and merge candidates within tolerance.
    """
    if not candidates:
        return []

    # Sort by boundary position
    sorted_candidates = sorted(candidates, key=lambda x: x[0])

    clusters = []
    current_cluster = [sorted_candidates[0]]
    current_center = sorted_candidates[0][0]

    for candidate in sorted_candidates[1:]:
        pos = candidate[0]

        if pos - current_center <= tolerance:
            # Add to current cluster
            current_cluster.append(candidate)
            # Update cluster center (weighted average)
            total_weight = sum(w for _, _, w in current_cluster)
            current_center = sum(p * w for p, _, w in current_cluster) / total_weight
        else:
            # Start a new cluster
            clusters.append(current_cluster)
            current_cluster = [candidate]
            current_center = pos

    # Add the last cluster
    if current_cluster:
        clusters.append(current_cluster)

    logger.debug(f"Clustering: {len(candidates)} candidates -> {len(clusters)} clusters")
    return clusters


def _vote_clusters(
    clusters: list[list[tuple[float, str, float]]], weights: dict[str, float], config: dict[str, Any]
) -> list[tuple[float, float]]:
    """Perform weighted voting on each cluster.

    Returns:
        [(boundary_position, vote_score), ...]
    """
    voted = []
    min_votes = config.get("min_votes", 2)

    for cluster in clusters:
        # Compute weighted vote score
        vote_score = 0.0
        unique_methods = set()

        for pos, method, weight in cluster:
            vote_score += weight
            unique_methods.add(method)

        # At least min_votes distinct methods must support this boundary
        if len(unique_methods) >= min_votes:
            # Compute cluster center (weighted average)
            total_weight = sum(w for _, _, w in cluster)
            center_pos = sum(p * w for p, _, w in cluster) / total_weight

            # Normalize vote score (0-1)
            max_possible_score = sum(weights.values())
            normalized_score = vote_score / max_possible_score if max_possible_score > 0 else 0.0

            voted.append((center_pos, normalized_score))

    logger.debug(f"Voting: {len(clusters)} clusters -> {len(voted)} valid boundaries")
    return voted


def _remove_outliers(voted_boundaries: list[tuple[float, float]], config: dict[str, Any]) -> list[float]:
    """Remove outliers (low-vote boundaries).

    Uses simple threshold filtering; can be replaced with DBSCAN in the future.
    """
    outlier_threshold = config.get("outlier_threshold", 0.3)

    clean = []
    for pos, score in voted_boundaries:
        if score >= outlier_threshold:
            clean.append(pos)
        else:
            logger.debug(f"Removed outlier: pos={pos:.1f}, score={score:.2f}")

    logger.debug(f"Denoising: {len(voted_boundaries)} -> {len(clean)} boundaries")
    return clean


def _calculate_confidence(boundaries: list[float], _weights: dict[str, float]) -> float:
    """Compute fusion confidence score.

    Based on:
    1. Number of boundaries (more is better, up to a limit)
    2. Average vote score
    3. Signal source coverage
    """
    if not boundaries:
        return 0.0

    # 1. Boundary count score (3-10 boundaries is optimal)
    boundary_count = len(boundaries)
    if boundary_count < 2:
        count_score = 0.3
    elif boundary_count <= 10:
        count_score = 1.0
    else:
        count_score = 0.7  # too many boundaries indicates noise

    # 2. Average vote score (computed from boundaries vote_score)
    # Simplified to infer from boundary count
    avg_vote_score = min(1.0, boundary_count / 5.0)

    # 3. Signal source coverage (ideally all 4 sources contribute)
    # Simplified to a fixed value; should pass from the clustering stage
    coverage_score = 0.8

    # Weighted final confidence computation
    confidence = count_score * 0.4 + avg_vote_score * 0.4 + coverage_score * 0.2

    return min(confidence, 1.0)
