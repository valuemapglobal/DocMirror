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

# 信号源权重配置
SIGNAL_WEIGHTS = {
    "header_anchors": 0.25,
    "word_anchors": 0.25,
    "data_voting": 0.30,
    "whitespace_projection": 0.20,
}

# 融合参数
FUSION_CONFIG = {
    "cluster_tolerance": 5.0,  # 边界聚类容差（pt）
    "min_votes": 2,  # 最小投票数
    "high_confidence_threshold": 0.8,
    "medium_confidence_threshold": 0.5,
    "outlier_threshold": 0.3,  # 孤立点阈值
}


def fuse_column_signals(
    signals: dict[str, list[float]],
    weights: dict[str, float] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[list[float], float]:
    """融合多源列边界信号。

    Args:
        signals: 信号源字典 {method_name: [boundary_positions]}
        weights: 信号权重字典（可选，默认使用SIGNAL_WEIGHTS）
        config: 融合参数配置（可选，默认使用FUSION_CONFIG）

    Returns:
        (fused_boundaries, confidence): 融合后的边界列表和置信度
    """
    weights = weights or SIGNAL_WEIGHTS
    config = config or FUSION_CONFIG

    # 1. 收集所有边界候选
    all_candidates = _collect_candidates(signals, weights)

    if not all_candidates:
        return [], 0.0

    # 2. 聚类相近边界（±容差）
    clusters = _cluster_boundaries(all_candidates, config["cluster_tolerance"])

    # 3. 计算每个簇的加权投票
    voted_boundaries = _vote_clusters(clusters, weights, config)

    if not voted_boundaries:
        return [], 0.0

    # 4. 去噪（移除低投票边界）
    clean_boundaries = _remove_outliers(voted_boundaries, config)

    # 5. 计算整体置信度
    confidence = _calculate_confidence(clean_boundaries, weights)

    logger.debug(f"🔮 信号融合: {len(signals)} 个信号源 → {len(clean_boundaries)} 个边界, 置信度={confidence:.2f}")

    return sorted(clean_boundaries), confidence


def should_use_fusion(confidence: float, config: dict[str, Any] | None = None) -> str:
    """判断是否应该使用融合结果。

    Args:
        confidence: 融合置信度
        config: 配置参数

    Returns:
        "use_fusion": 使用融合结果
        "verify_with_signal": 用信号处理器验证
        "fallback": 降级到单一方法
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
    """收集所有边界候选。

    Returns:
        [(boundary_pos, method_name, weight), ...]
    """
    candidates = []

    for method_name, boundaries in signals.items():
        if not boundaries:
            continue

        weight = weights.get(method_name, 0.1)  # 默认权重0.1

        for boundary in boundaries:
            candidates.append((boundary, method_name, weight))

    logger.debug(f"📊 收集到 {len(candidates)} 个边界候选")
    return candidates


def _cluster_boundaries(
    candidates: list[tuple[float, str, float]], tolerance: float
) -> list[list[tuple[float, str, float]]]:
    """聚类相近边界（±容差）。

    算法: 贪心聚类，按位置排序后合并距离<tolerance的候选
    """
    if not candidates:
        return []

    # 按边界位置排序
    sorted_candidates = sorted(candidates, key=lambda x: x[0])

    clusters = []
    current_cluster = [sorted_candidates[0]]
    current_center = sorted_candidates[0][0]

    for candidate in sorted_candidates[1:]:
        pos = candidate[0]

        if pos - current_center <= tolerance:
            # 加入当前簇
            current_cluster.append(candidate)
            # 更新簇中心（加权平均）
            total_weight = sum(w for _, _, w in current_cluster)
            current_center = sum(p * w for p, _, w in current_cluster) / total_weight
        else:
            # 开始新簇
            clusters.append(current_cluster)
            current_cluster = [candidate]
            current_center = pos

    # 添加最后一个簇
    if current_cluster:
        clusters.append(current_cluster)

    logger.debug(f"🔗 聚类: {len(candidates)} 候选 → {len(clusters)} 簇")
    return clusters


def _vote_clusters(
    clusters: list[list[tuple[float, str, float]]], weights: dict[str, float], config: dict[str, Any]
) -> list[tuple[float, float]]:
    """对每个簇进行加权投票。

    Returns:
        [(boundary_position, vote_score), ...]
    """
    voted = []
    min_votes = config.get("min_votes", 2)

    for cluster in clusters:
        # 计算加权投票分数
        vote_score = 0.0
        unique_methods = set()

        for pos, method, weight in cluster:
            vote_score += weight
            unique_methods.add(method)

        # 至少需要min_votes个不同方法支持
        if len(unique_methods) >= min_votes:
            # 计算簇中心位置（加权平均）
            total_weight = sum(w for _, _, w in cluster)
            center_pos = sum(p * w for p, _, w in cluster) / total_weight

            # 归一化投票分数（0-1）
            max_possible_score = sum(weights.values())
            normalized_score = vote_score / max_possible_score if max_possible_score > 0 else 0.0

            voted.append((center_pos, normalized_score))

    logger.debug(f"🗳️ 投票: {len(clusters)} 簇 → {len(voted)} 个有效边界")
    return voted


def _remove_outliers(voted_boundaries: list[tuple[float, float]], config: dict[str, Any]) -> list[float]:
    """移除孤立点（低投票边界）。

    使用简单的阈值过滤，未来可替换为DBSCAN
    """
    outlier_threshold = config.get("outlier_threshold", 0.3)

    clean = []
    for pos, score in voted_boundaries:
        if score >= outlier_threshold:
            clean.append(pos)
        else:
            logger.debug(f"🚫 移除孤立边界: pos={pos:.1f}, score={score:.2f}")

    logger.debug(f"🧹 去噪: {len(voted_boundaries)} → {len(clean)} 个边界")
    return clean


def _calculate_confidence(boundaries: list[float], _weights: dict[str, float]) -> float:
    """计算融合置信度。

    基于:
    1. 边界数量（越多越可信，但有上限）
    2. 平均投票分数
    3. 信号源覆盖率
    """
    if not boundaries:
        return 0.0

    # 1. 边界数量得分（3-10个边界最佳）
    boundary_count = len(boundaries)
    if boundary_count < 2:
        count_score = 0.3
    elif boundary_count <= 10:
        count_score = 1.0
    else:
        count_score = 0.7  # 过多边界可能是噪声

    # 2. 平均投票分数（从boundaries的vote_score计算）
    # 这里简化为使用边界数量推断
    avg_vote_score = min(1.0, boundary_count / 5.0)

    # 3. 信号源覆盖率（理想情况4个信号源都有贡献）
    # 这里简化为固定值，实际应该从聚类阶段传递
    coverage_score = 0.8

    # 加权计算最终置信度
    confidence = count_score * 0.4 + avg_vote_score * 0.4 + coverage_score * 0.2

    return min(confidence, 1.0)
