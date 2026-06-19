# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Result fusion engine — merges competing table extraction results.

Purpose: Fuses multiple table candidates (different tiers/engines) into one
best grid using cell-level voting and structure agreement.

Main components: ``ResultFusionEngine``.

Upstream: Multiple ``ExtractCandidate`` outputs.

Downstream: ``extract.best_candidate``, ``table.signal_fusion``.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Result Fusion Engine
# ═══════════════════════════════════════════════════════════════════════════════


class ResultFusionEngine:
    """
    结果融合引擎

    当多层策略都有输出时，不是简单替代，而是融合共识。

    融合策略：
        1. 表头行投票：多层都识别为表头的行 → 高置信度
        2. 列边界对齐：取多层列边界的加权平均
        3. 单元格内容选择：优先选择高置信度层的内容
        4. 冲突解决：投票机制
        5. 置信度校准：融合后的置信度通常高于单一层
    """

    @classmethod
    def fuse(cls, results: list[dict[str, Any]]) -> dict[str, Any]:
        """
        融合多个提取结果

        Args:
            results: 各层的提取结果列表，每个结果包含：
                - tables: 表格列表
                - confidence: 置信度
                - metadata: 元数据

        Returns:
            融合后的结果
        """
        if not results:
            return {"tables": [], "confidence": 0.0, "metadata": {}}

        if len(results) == 1:
            return results[0]

        try:
            # 1. 表头行投票
            fused_header = cls._vote_header(results)

            # 2. 列边界融合
            fused_columns = cls._merge_column_boundaries(results)

            # 3. 选择最佳表格（基于融合策略）
            fused_tables = cls._select_best_tables(results, fused_header, fused_columns)

            # 4. 置信度校准
            fused_confidence = cls._calibrate_confidence(results)

            # 5. 构建融合元数据
            fusion_metadata = {
                "fusion_method": "weighted_consensus",
                "layer_count": len(results),
                "layer_confidences": [r.get("confidence", 0) for r in results],
                "header_votes": fused_header.get("votes", {}),
                "fusion_improvement": fused_confidence - max(r.get("confidence", 0) for r in results),
            }

            fused_result = {
                "tables": fused_tables,
                "confidence": fused_confidence,
                "metadata": {**results[0].get("metadata", {}), "fusion": fusion_metadata},
            }

            logger.debug(
                f"[ResultFusion] Fused {len(results)} layers, "
                f"confidence: {fused_confidence:.3f} "
                f"(best single: {max(r.get('confidence', 0) for r in results):.3f})"
            )

            return fused_result

        except Exception as e:
            logger.warning(f"[ResultFusion] Fusion failed: {e}, falling back to best result")
            # 降级：返回置信度最高的单一结果
            return max(results, key=lambda r: r.get("confidence", 0))

    @classmethod
    def _vote_header(cls, results: list[dict[str, Any]]) -> dict[str, Any]:
        """
        表头行投票

        Args:
            results: 各层提取结果

        Returns:
            {'row_index': int, 'votes': int, 'confidence': float}
        """
        header_votes = Counter()
        header_confidence = defaultdict(list)

        for result in results:
            tables = result.get("tables", [])
            if not tables:
                continue

            # 获取每层识别的表头行
            for table in tables:
                header_idx = cls._extract_header_index(table)
                if header_idx is not None:
                    header_votes[header_idx] += 1
                    header_confidence[header_idx].append(result.get("confidence", 0))

        if not header_votes:
            return {"row_index": 0, "votes": 0, "confidence": 0.0}

        # 选择得票最多，且平均置信度最高的行
        best_row = max(
            header_votes.keys(),
            key=lambda r: (header_votes[r], np.mean(header_confidence[r]) if header_confidence[r] else 0),
        )

        return {
            "row_index": best_row,
            "votes": header_votes[best_row],
            "confidence": np.mean(header_confidence[best_row]) if header_confidence[best_row] else 0.0,
        }

    @classmethod
    def _merge_column_boundaries(cls, results: list[dict[str, Any]]) -> list[float]:
        """
        融合列边界（加权平均）

        Args:
            results: 各层提取结果

        Returns:
            融合后的列边界列表
        """
        all_boundaries = []
        all_confidences = []

        for result in results:
            tables = result.get("tables", [])
            if not tables:
                continue

            # 获取第一张表的列边界
            table = tables[0]
            col_bounds = cls._extract_column_boundaries(table)

            if col_bounds:
                all_boundaries.append(col_bounds)
                all_confidences.append(result.get("confidence", 0))

        if not all_boundaries:
            return []

        # 对齐列数（取最大列数）
        max_cols = max(len(b) for b in all_boundaries)

        fused_bounds = []
        for col_idx in range(max_cols):
            # 收集所有层在该列的边界
            bounds_at_col = []
            weights_at_col = []

            for bounds, conf in zip(all_boundaries, all_confidences):
                if col_idx < len(bounds):
                    bounds_at_col.append(bounds[col_idx])
                    weights_at_col.append(conf)

            # 加权平均（高置信度层权重更大）
            if bounds_at_col:
                weights = np.array(weights_at_col)
                weights = weights / weights.sum()  # 归一化
                fused_bound = np.average(bounds_at_col, weights=weights)
                fused_bounds.append(fused_bound)

        return fused_bounds

    @classmethod
    def _select_best_tables(
        cls, results: list[dict[str, Any]], header_info: dict[str, Any], fused_columns: list[float]
    ) -> list[dict[str, Any]]:
        """
        选择最佳表格（或融合多个表格）

        Args:
            results: 各层提取结果
            header_info: 表头投票结果
            fused_columns: 融合后的列边界

        Returns:
            融合后的表格列表
        """
        # 简单策略：选择置信度最高的表格
        # 复杂策略：融合多个表格的单元格（未来扩展）

        if not results:
            return []

        # 按置信度排序
        sorted_results = sorted(results, key=lambda r: r.get("confidence", 0), reverse=True)
        best_result = sorted_results[0]

        # 处理tables可能是列表的情况
        tables = best_result.get("tables", [])
        if not tables:
            return []

        # 如果tables是字典列表
        if isinstance(tables, list) and len(tables) > 0:
            if isinstance(tables[0], dict):
                pass  # OK
            elif isinstance(tables[0], list):
                # 转换为字典格式
                tables = [{"data": tables, "metadata": {}}]

        # 如果有多层结果，尝试优化最佳表格
        if len(results) > 1:
            # 应用融合后的表头和列边界
            tables = cls._optimize_tables(tables, header_info, fused_columns)

        return tables

    @classmethod
    def _optimize_tables(cls, tables: list[dict], header_info: dict, fused_columns: list[float]) -> list[dict]:
        """优化表格（应用融合后的表头和列边界）"""
        if not tables:
            return tables

        optimized = []
        for table in tables:
            # 创建副本
            opt_table = table.copy()

            # 应用融合后的表头（如果有）
            if header_info.get("votes", 0) > 1:
                opt_table["fused_header"] = header_info

            # 应用融合后的列边界（如果有）
            if fused_columns:
                opt_table["fused_columns"] = fused_columns

            optimized.append(opt_table)

        return optimized

    @classmethod
    def _calibrate_confidence(cls, results: list[dict[str, Any]]) -> float:
        """
        校准融合后的置信度

        算法：
        1. 如果多层结果一致（表头相同），置信度提升
        2. 如果多层结果差异大，取加权平均
        3. 融合后置信度通常高于最佳单一结果
        """
        if not results:
            return 0.0

        if len(results) == 1:
            return results[0].get("confidence", 0)

        # 获取各层置信度
        confidences = [r.get("confidence", 0) for r in results]
        best_conf = max(confidences)
        avg_conf = np.mean(confidences)

        # 检查一致性（表头投票）
        header_votes = Counter()
        for result in results:
            tables = result.get("tables", [])
            if tables:
                header_idx = cls._extract_header_index(tables[0])
                if header_idx is not None:
                    header_votes[header_idx] += 1

        # 一致性奖励
        agreement_bonus = 0.0
        if header_votes:
            max_votes = max(header_votes.values())
            if max_votes == len(results):
                # 所有层一致
                agreement_bonus = 0.05
            elif max_votes >= len(results) * 0.6:
                # 多数一致
                agreement_bonus = 0.03

        # Weighted blend: best layer 60%, mean 40%, plus agreement bonus
        fused_conf = best_conf * 0.6 + avg_conf * 0.4 + agreement_bonus

        # Clamp to unit interval
        return min(1.0, max(0.0, fused_conf))

    @classmethod
    def _extract_header_index(cls, table: dict[str, Any]) -> int | None:
        """从表格中提取表头行索引"""
        metadata = table.get("metadata", {})

        # 尝试从列签名推断结果中获取
        header_inference = metadata.get("header_inference", {})
        if header_inference:
            return header_inference.get("header_row_index")

        # 尝试从传统方法获取
        header_row = table.get("header_row")
        if header_row is not None:
            return header_row

        # 默认第0行
        return 0

    @classmethod
    def _extract_column_boundaries(cls, table: dict[str, Any]) -> list[float]:
        """从表格中提取列边界"""
        metadata = table.get("metadata", {})

        # 尝试从融合列边界获取
        fused_columns = metadata.get("fused_columns", [])
        if fused_columns:
            return fused_columns

        # 尝试从列边界元数据获取
        col_bounds = metadata.get("column_boundaries", [])
        if col_bounds:
            return col_bounds

        # 尝试从表头提取
        header = table.get("header", [])
        if header:
            # 返回占位符（实际应该从bbox计算）
            return [i * 100.0 for i in range(len(header))]

        return []

    @classmethod
    def _calculate_agreement_score(cls, results: list[dict[str, Any]]) -> float:
        """
        计算多层结果的一致性得分

        Returns:
            0.0 (完全不一致) - 1.0 (完全一致)
        """
        if len(results) < 2:
            return 1.0

        # 提取各层的表头行
        header_indices = []
        for result in results:
            tables = result.get("tables", [])
            if tables:
                header_idx = cls._extract_header_index(tables[0])
                if header_idx is not None:
                    header_indices.append(header_idx)

        if not header_indices:
            return 0.0

        # 计算一致性（得票最多的比例）
        votes = Counter(header_indices)
        max_votes = max(votes.values())

        return max_votes / len(header_indices)
