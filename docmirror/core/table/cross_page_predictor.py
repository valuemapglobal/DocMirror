"""
Cross-page table predictor — detects truncated tables spanning pages.

Purpose: Predicts when a table continues on the next page and validates merge
candidates using column profiles and truncation heuristics.

Main components: ``CrossPageTablePredictor``, ``TruncationInfo``,
``NextPagePrediction``.

Upstream: Sequential page table blocks, ``table.signature``.

Downstream: ``table.merge.merger``, ``table.compose``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from docmirror.models.entities.domain import PageLayout

logger = logging.getLogger(__name__)


@dataclass
class TruncationInfo:
    """第N页的截断信息。"""

    incomplete_rows: int = 0  # 未完成行数
    incomplete_row_indices: list[int] = field(default_factory=list)
    last_col_signature: dict[str, Any] = field(default_factory=dict)
    cross_page_header: dict[str, Any] = field(default_factory=dict)
    col_types: list[str] = field(default_factory=list)
    col_count: int = 0
    page_idx: int = 0
    has_trailing_continuation: bool = False  # 是否有延续标记（"续"、"...")


@dataclass
class NextPagePrediction:
    """第N+1页的预测信息。"""

    predicted_col_count: int = 0
    predicted_col_types: list[str] = field(default_factory=list)
    predicted_header: dict[str, Any] = field(default_factory=dict)
    predicted_merge_pattern: str = "unknown"  # "append", "new_table", "unknown"
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def col_count(self) -> int:
        return self.predicted_col_count


@dataclass
class MergeValidation:
    """合并验证结果。"""

    is_valid: bool = False
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CrossPageTablePredictor:
    """跨页表格预测引擎。

    道法自然 · 第十六重境界:
      - 第N页提取完成后，记录截断信息
      - 第N+1页提取前，预测表格结构
      - 指导提取器使用预测信息
    """

    def __init__(self, confidence_threshold: float = 0.7):
        """初始化预测引擎。

        Args:
            confidence_threshold: 置信度阈值（低于此值不使用预测）
        """
        self.confidence_threshold = confidence_threshold
        self._state: TruncationInfo | None = None
        self._prediction_history: list[tuple[TruncationInfo, NextPagePrediction]] = []

    def record_truncation(self, page_layout: PageLayout, extraction_result: Any, page_idx: int = 0) -> TruncationInfo:
        """记录第N页的截断信息。

        Args:
            page_layout: 页面布局
            extraction_result: 提取结果（TableExtractionResult）
            page_idx: 页面索引

        Returns:
            TruncationInfo: 截断信息
        """
        info = TruncationInfo(page_idx=page_idx)

        # 1. 检测未完成行（行尾缺少右括号/句号）
        info.incomplete_rows = self._detect_incomplete_rows(page_layout)

        # 2. 记录最后列结构
        if hasattr(extraction_result, "structured_data") and extraction_result.structured_data:
            table = extraction_result.structured_data[0] if extraction_result.structured_data else None
            if table and hasattr(table, "columns"):
                info.col_count = len(table.columns)
                info.last_col_signature = self._extract_col_signature(table, page_layout)
                info.col_types = self._infer_col_types(table)

        # 3. 检测延续标记（"续"、"..."等）
        info.has_trailing_continuation = self._detect_continuation_markers(page_layout)

        # 4. 检测可能的跨页表头
        info.cross_page_header = self._detect_cross_page_header(page_layout)

        # 保存状态
        self._state = info

        logger.debug(
            f"📊 记录第{page_idx}页截断信息: "
            f"列数={info.col_count}, "
            f"未完成行={info.incomplete_rows}, "
            f"延续标记={info.has_trailing_continuation}"
        )

        return info

    def predict_next_page(self, truncation_info: TruncationInfo) -> NextPagePrediction:
        """预测第N+1页的表格结构。

        Args:
            truncation_info: 第N页的截断信息

        Returns:
            NextPagePrediction: 预测信息
        """
        prediction = NextPagePrediction()

        # 1. 预测列数
        prediction.predicted_col_count = truncation_info.col_count

        # 2. 预测列类型
        prediction.predicted_col_types = truncation_info.col_types.copy()

        # 3. 计算置信度
        confidence = self._calculate_prediction_confidence(truncation_info)
        prediction.confidence = confidence

        # 4. 预测合并模式
        if truncation_info.incomplete_rows > 0 or truncation_info.has_trailing_continuation:
            prediction.predicted_merge_pattern = "append"
        else:
            prediction.predicted_merge_pattern = "new_table"

        # 5. 生成警告
        if confidence < self.confidence_threshold:
            prediction.warnings.append(f"预测置信度低 ({confidence:.2f} < {self.confidence_threshold})")

        if truncation_info.col_count == 0:
            prediction.warnings.append("第N页未检测到表格列数")

        # 保存历史
        self._prediction_history.append((truncation_info, prediction))

        logger.debug(
            f"🔮 预测第N+1页: "
            f"列数={prediction.predicted_col_count}, "
            f"置信度={confidence:.2f}, "
            f"合并模式={prediction.predicted_merge_pattern}"
        )

        return prediction

    def validate_merge(self, truncation_info: TruncationInfo, next_page_result: Any) -> MergeValidation:
        """验证跨页合并是否有效。

        Args:
            truncation_info: 第N页的截断信息
            next_page_result: 第N+1页的提取结果

        Returns:
            MergeValidation: 验证结果
        """
        validation = MergeValidation()
        score = 0.0
        max_score = 0.0

        # 1. 列数验证（权重 40%）
        max_score += 40
        if truncation_info.col_count > 0 and next_page_result:
            next_col_count = self._get_result_col_count(next_page_result)
            if next_col_count > 0:
                col_diff = abs(truncation_info.col_count - next_col_count)
                if col_diff == 0:
                    score += 40
                    validation.reasons.append("列数完全匹配")
                elif col_diff == 1:
                    score += 25  # 允许1列差异（可能是合并单元格）
                    validation.warnings.append(f"列数差异1 ({truncation_info.col_count} vs {next_col_count})")
                else:
                    validation.reasons.append(f"列数差异过大 ({col_diff})")
            else:
                validation.warnings.append("第N+1页未检测到列数")

        # 2. 列类型验证（权重 30%）
        max_score += 30
        if truncation_info.col_types and next_page_result:
            next_col_types = self._get_result_col_types(next_page_result)
            if next_col_types:
                type_matches = sum(1 for t1, t2 in zip(truncation_info.col_types, next_col_types) if t1 == t2)
                type_match_rate = type_matches / max(len(truncation_info.col_types), len(next_col_types))
                score += 30 * type_match_rate

                if type_match_rate >= 0.8:
                    validation.reasons.append(f"列类型匹配度高 ({type_match_rate:.2f})")
                elif type_match_rate >= 0.5:
                    validation.warnings.append(f"列类型匹配度中等 ({type_match_rate:.2f})")
                else:
                    validation.warnings.append(f"列类型匹配度低 ({type_match_rate:.2f})")

        # 3. 延续标记验证（权重 20%）
        max_score += 20
        if truncation_info.has_trailing_continuation:
            score += 20
            validation.reasons.append("检测到延续标记，支持合并")

        # 4. 未完成行验证（权重 10%）
        max_score += 10
        if truncation_info.incomplete_rows > 0:
            score += 10
            validation.reasons.append(f"检测到{truncation_info.incomplete_rows}个未完成行")

        # 计算最终得分
        validation.score = score / max_score if max_score > 0 else 0.0
        validation.is_valid = validation.score >= self.confidence_threshold

        logger.debug(f"✅ 合并验证: 得分={validation.score:.2f}, 有效={validation.is_valid}, 原因={validation.reasons}")

        return validation

    def validate_raw_table_merge(
        self,
        prev_rows: list[list],
        next_rows: list[list],
        *,
        prev_page_no: int = 0,
        next_page_no: int = 0,
    ) -> MergeValidation:
        """Validate cross-page merge using raw table row matrices (PageLayout path)."""
        logger.debug(
            "validate_raw_table_merge pages %s -> %s",
            prev_page_no,
            next_page_no,
        )
        info = TruncationInfo(
            page_idx=prev_page_no,
            col_count=len(prev_rows[0]) if prev_rows else 0,
            col_types=self._infer_col_types_from_header(prev_rows[0] if prev_rows else []),
            has_trailing_continuation=self._rows_have_continuation_marker(prev_rows),
        )
        return self.validate_merge(info, _RawTableExtractionResult(next_rows))

    @staticmethod
    def _infer_col_types_from_header(header_row: list) -> list[str]:
        col_types = []
        for cell in header_row:
            name = str(cell).lower()
            if any(k in name for k in ("金额", "amount", "余额", "balance")):
                col_types.append("currency")
            elif any(k in name for k in ("日期", "date", "时间", "time")):
                col_types.append("date")
            elif any(k in name for k in ("序号", "编号", "no", "index")):
                col_types.append("number")
            else:
                col_types.append("text")
        return col_types

    @staticmethod
    def _rows_have_continuation_marker(rows: list[list]) -> bool:
        for row in rows[-3:]:
            text = " ".join(str(c) for c in row).lower()
            if any(m in text for m in ("续", "续表", "...", "…", "continued")):
                return True
        return False

    def reset(self) -> None:
        """重置预测状态。"""
        self._state = None
        self._prediction_history.clear()

    def get_prediction_history(self) -> list[tuple[TruncationInfo, NextPagePrediction]]:
        """获取预测历史。

        Returns:
            预测历史记录列表
        """
        return self._prediction_history.copy()

    # ========== Private Methods ==========

    def _detect_incomplete_rows(self, page_layout: PageLayout) -> int:
        """检测未完成行（行尾缺少右括号/句号）。"""
        incomplete_count = 0

        for block in page_layout.blocks:
            # 简化检查：不依赖BlockType
            if not hasattr(block, "block_type"):
                continue

            block_type_value = block.block_type.value if hasattr(block.block_type, "value") else str(block.block_type)
            if block_type_value != "table":
                continue

            if not hasattr(block, "text"):
                continue

            # 检查表格最后一行
            lines = block.text.strip().split("\n")
            if lines:
                last_line = lines[-1].strip()
                if self._is_incomplete_line(last_line):
                    incomplete_count += 1

        return incomplete_count

    def _is_incomplete_line(self, line: str) -> bool:
        """判断行是否未完成。"""
        if not line:
            return False

        # 检查是否缺少结束符号
        incomplete_markers = [
            not line.endswith(("。", "；", "）", ")", "」", "】", ".", ";", ")", "]")),
            line.endswith(("...", "…", "续", "接")),  # 延续标记
        ]

        return any(incomplete_markers)

    def _detect_continuation_markers(self, page_layout: PageLayout) -> bool:
        """检测页面是否有延续标记。"""
        for block in page_layout.blocks:
            if not hasattr(block, "text"):
                continue

            text = block.text.lower()
            if any(marker in text for marker in ["续", "续表", "...", "…", "continued"]):
                return True

        return False

    def _detect_cross_page_header(self, page_layout: PageLayout) -> dict[str, Any]:
        """检测可能的跨页表头。"""
        # 简化实现：检查第一个表格的第一行
        for block in page_layout.blocks:
            # 简化检查：不依赖BlockType
            if not hasattr(block, "block_type"):
                continue

            block_type_value = block.block_type.value if hasattr(block.block_type, "value") else str(block.block_type)
            if block_type_value != "table":
                continue

            if hasattr(block, "header_row"):
                return {
                    "detected": True,
                    "header": block.header_row,
                }

        return {"detected": False}

    def _extract_col_signature(self, table: Any, _page_layout: PageLayout) -> dict[str, Any]:
        """提取列签名。"""
        # 简化实现：返回列数和列名
        signature = {
            "col_count": len(table.columns) if hasattr(table, "columns") else 0,
        }

        if hasattr(table, "columns"):
            signature["col_names"] = [c.get("name", "") for c in table.columns]

        return signature

    def _infer_col_types(self, table: Any) -> list[str]:
        """推断列类型。"""
        # 简化实现：基于列名或样本数据推断
        col_types = []

        if hasattr(table, "columns"):
            for col in table.columns:
                col_name = col.get("name", "").lower() if isinstance(col, dict) else str(col).lower()

                # 基于列名推断
                if any(keyword in col_name for keyword in ["金额", "amount", "余额", "balance"]):
                    col_types.append("currency")
                elif any(keyword in col_name for keyword in ["日期", "date", "时间", "time"]):
                    col_types.append("date")
                elif any(keyword in col_name for keyword in ["序号", "编号", "no", "index"]):
                    col_types.append("number")
                else:
                    col_types.append("text")

        return col_types

    def _calculate_prediction_confidence(self, truncation_info: TruncationInfo) -> float:
        """计算预测置信度。"""
        confidence = 0.5  # 基础置信度

        # 有明确的列数
        if truncation_info.col_count > 0:
            confidence += 0.2

        # 有延续标记
        if truncation_info.has_trailing_continuation:
            confidence += 0.15

        # 有未完成行
        if truncation_info.incomplete_rows > 0:
            confidence += 0.1

        # 有列类型信息
        if truncation_info.col_types:
            confidence += 0.05

        return min(confidence, 1.0)

    def _get_result_col_count(self, result: Any) -> int:
        """从提取结果获取列数。"""
        if hasattr(result, "structured_data") and result.structured_data:
            table = result.structured_data[0]
            if hasattr(table, "columns"):
                return len(table.columns)
        return 0

    def _get_result_col_types(self, result: Any) -> list[str]:
        """从提取结果获取列类型。"""
        if hasattr(result, "structured_data") and result.structured_data:
            table = result.structured_data[0]
            if hasattr(table, "columns"):
                return self._infer_col_types(table)
        return []


@dataclass
class _RawTableColumn:
    name: str


@dataclass
class _RawTableData:
    columns: list[_RawTableColumn]


@dataclass
class _RawTableExtractionResult:
    """Minimal adapter so validate_merge works with raw row matrices."""

    rows: list[list]

    @property
    def structured_data(self) -> list[_RawTableData]:
        if not self.rows:
            return []
        header = self.rows[0]
        return [_RawTableData(columns=[_RawTableColumn(name=str(c)) for c in header])]
