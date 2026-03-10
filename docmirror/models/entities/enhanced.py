"""
EnhancedResult — 增强后的最终Result
==================================

这是MiddlewarePipeline的Output，Aggregation了:
    1. 原始 BaseResult 的Immutable引用
    2. 经过增强的结构化Data
    3. Detect出的Document场景
    4. 完整的 Mutation 变换历史

提供 ``to_parser_output()`` Method桥接回 v1 的 ``ParserOutput``，
ensure与现有 ``ParserDispatcher`` 和 ``PerceptionResult`` 完全兼容。
"""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import Any, Dict, List, Literal, Optional

from .domain import BaseResult
from ..tracking.mutation import Mutation

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class EnhancedResult:
    """
    Enhanced result — MiddlewarePipeline的最终产出。

    Design principles:
        - base_result Read-only引用，永不修改
        - enhanced_data 由eachMiddleware渐进式填充
        - mutations 记录all变换操作
        - status 反映PipelineExecuteStatus
    """
    document_id: str = ""
    base_result: Optional[BaseResult] = None
    enhanced_data: Dict[str, Any] = dataclasses.field(default_factory=dict)
    scene: str = "unknown"
    institution: Optional[str] = None  # L2 机构 id，如 cc b / citic
    mutations: List[Mutation] = dataclasses.field(default_factory=list)
    status: Literal["success", "partial", "failed"] = "success"
    processing_time: float = 0.0
    errors: List[str] = dataclasses.field(default_factory=list)

    # ── MiddlewareHelperMethod ──

    def add_mutation(self, mutation: Mutation) -> None:
        """add一条变换记录。"""
        self.mutations.append(mutation)

    def record_mutation(
        self,
        middleware_name: str,
        target_block_id: str,
        field_changed: str,
        old_value: Any,
        new_value: Any,
        confidence: float = 1.0,
        reason: str = "",
    ) -> None:
        """便捷Method — Create并add Mutation。"""
        self.mutations.append(
            Mutation.create(
                middleware_name=middleware_name,
                target_block_id=target_block_id,
                field_changed=field_changed,
                old_value=old_value,
                new_value=new_value,
                confidence=confidence,
                reason=reason,
            )
        )

    def add_error(self, error: str) -> None:
        """记录Error并DowngradeStatus。"""
        self.errors.append(error)
        if self.status == "success":
            self.status = "partial"

    # ── Data访问快捷Method ──

    @property
    def standardized_tables(self) -> List[Dict[str, Any]]:
        """获取allStandard化Table (多 table结构)。"""
        return self.enhanced_data.get("standardized_tables", [])

    @property
    def standardized_table(self) -> Optional[List[List[str]]]:
        """获取Standard化后的主Table (含Table header行, Backward compatible)。"""
        return self.enhanced_data.get("standardized_table")

    @property
    def standardized_headers(self) -> List[str]:
        """获取Standard化后的Table header。"""
        return self.enhanced_data.get("standardized_headers", [])

    @property
    def validation_result(self) -> Optional[Dict[str, Any]]:
        """获取Validation result。"""
        return self.enhanced_data.get("validation")

    @property
    def mutation_count(self) -> int:
        return len(self.mutations)

    @property
    def mutation_summary(self) -> Dict[str, int]:
        """按Middleware统计 Mutation 数量。"""
        summary: Dict[str, int] = {}
        for m in self.mutations:
            summary[m.middleware_name] = summary.get(m.middleware_name, 0) + 1
        return summary

    # ── v1 兼容桥接 ──

    def to_parser_output(self):
        """
        [DEPRECATED] 桥接到 v1 的 ParserOutput。

        请using PerceptionResultBuilder.build() 替代。
        retain此Method仅为Backward compatible parse() 旧Interface。
        """
        import warnings
        warnings.warn(
            "to_parser_output() is deprecated, use PerceptionResultBuilder.build() instead",
            DeprecationWarning, stacklevel=2,
        )
        # 尝试Import v1 桥接Type
        ParserOutput = None
        ParserStatus = None
        try:
            from docmirror.framework.base import (
                ParserOutput as _PO,
                ParserStatus as _PS,
            )
            ParserOutput = _PO
            ParserStatus = _PS
        except ImportError:
            pass

        if self.base_result is None:
            if ParserOutput and ParserStatus:
                return ParserOutput(
                    status=ParserStatus.FAILURE,
                    error="No base result available",
                )
            return {"status": "failure", "error": "No base result available"}

        # StatusMap
        status_map = {
            "success": ParserStatus.SUCCESS,
            "partial": ParserStatus.PARTIAL_SUCCESS,
            "failed": ParserStatus.FAILURE,
        }

        # 构建 document_structure — 从 enhanced_data 或 base_result
        doc_structure = []
        for block in self.base_result.all_blocks:
            entry: Dict[str, Any] = {
                "type": block.block_type,
                "page": block.page,
            }
            if block.block_type == "table":
                table_data = block.raw_content
                if isinstance(table_data, list) and table_data:
                    entry["headers"] = table_data[0] if table_data else []
                    entry["rows"] = table_data[1:] if len(table_data) > 1 else []
                    entry["data"] = table_data
            elif block.block_type == "key_value":
                entry["pairs"] = block.raw_content if isinstance(block.raw_content, dict) else {}
            elif block.block_type in ("text", "title", "footer"):
                entry["text"] = block.raw_content if isinstance(block.raw_content, str) else ""

            doc_structure.append(entry)

        # 如果有Standard化Table，replace主 table
        std_tables = self.standardized_tables
        if std_tables and doc_structure:
            # 用最大 tablereplace第一个 table entry
            main = max(std_tables, key=lambda t: t.get("row_count", 0))
            for entry in doc_structure:
                if entry.get("type") == "table":
                    entry["headers"] = main.get("headers", [])
                    entry["rows"] = main.get("rows", [])
                    entry["data"] = [main.get("headers", [])] + main.get("rows", [])
                    break

        # 构建 metadata
        metadata = dict(self.base_result.metadata)
        metadata.update({
            "parser": "DocMirror",
            "scene": self.scene,
            "enhance_mode": self.enhanced_data.get("enhance_mode", "unknown"),
            "page_count": self.base_result.page_count,
            "mutation_count": self.mutation_count,
            "mutation_summary": self.mutation_summary,
            "processing_time_ms": round(self.processing_time, 1),
            "errors": self.errors,
        })

        # Merge identity Information (兼容 v1 消费方)；机构优先用 L2 RecognizeResult
        entities = self.base_result.entities
        institution_value = self.institution or self.enhanced_data.get("institution")
        if not institution_value and isinstance(entities, dict):
            institution_value = entities.get("bank_name", entities.get("Bank name", ""))
        metadata["institution"] = institution_value
        metadata["identity"] = {
            "document_type": self.scene,
            "institution": institution_value,
            "account_holder": entities.get("Account name", entities.get("Account name", "")),
            "account_number": entities.get("Account number", entities.get("Card number", "")),
            "query_period": entities.get("Query period", entities.get("Period", "")),
            "currency": entities.get("Currency", "CNY"),
        }

        # ValidateInformation
        validation = self.validation_result
        if validation:
            metadata["l2_score"] = validation.get("total_score")
            metadata["l2_passed"] = validation.get("passed")

        # SealInformation (来自 CoreExtractor OptionalDetect)，带入 trust 供 API using
        if self.base_result.metadata.get("seal_info"):
            metadata["trust"] = metadata.get("trust") or {}
            metadata["trust"]["seal_info"] = self.base_result.metadata["seal_info"]

        # ── Returns ──
        if ParserOutput and ParserStatus:
            return ParserOutput(
                status=status_map.get(self.status, ParserStatus.FAILURE),
                confidence=1.0 if self.status == "success" else (0.5 if self.status == "partial" else 0.0),
                structured_text=self.base_result.full_text,
                key_entities=entities,
                document_structure=doc_structure,
                metadata=metadata,
            )

        # 独立Mode: Returns等价 dict
        return {
            "status": self.status,
            "confidence": 1.0 if self.status == "success" else (0.5 if self.status == "partial" else 0.0),
            "structured_text": self.base_result.full_text,
            "key_entities": entities,
            "document_structure": doc_structure,
            "metadata": metadata,
        }

    @classmethod
    def from_base_result(cls, base_result: BaseResult) -> EnhancedResult:
        """从 BaseResult Create初始 EnhancedResult。"""
        return cls(
            document_id=base_result.document_id,
            base_result=base_result,
        )
