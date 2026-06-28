# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Header inferrer middleware — column-signature-based table header detection.

Infers header row positions by testing column type consistency rather than
matching fixed vocabulary lists. Runs after table extraction and before
validation; fuses confidence with lexicon-based strategies when both agree.
Designed to complement, not replace, institution-specific layout profiles.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from docmirror.framework.middlewares.base import BaseMiddleware
from docmirror.models.entities.parse_result import RowType
from docmirror.structure.tables.signature import TypeSignatureLibrary

if TYPE_CHECKING:
    from docmirror.models.entities.parse_result import ParseResult, RowType

logger = logging.getLogger(__name__)


class HeaderInferrerMiddleware(BaseMiddleware):
    """
    Header detection middleware based on column signature inference

    Core algorithm:
        1. For each candidate header row (typically first 3 rows), check the type consistency of data below it
        2. Infer type signatures for each column (date, amount, text, etc.)
        3. Compute the overall consistency score
        4. Select the candidate row with the highest score as the header

    Fusion strategy:
        - Runs in parallel with the existing vocabulary-based strategy
        - When both methods point to the same row, add +0.1 confidence bonus
        - When they disagree, use the higher-confidence result

    Configuration:
        min_data_rows: minimum data rows (default 3)
        max_lookback_rows: maximum lookback rows (default 15)
        consistency_threshold: 一致性阈值（默认0.7）
        weight_signature: 签名策略权重（默认0.4）
        weight_vocab: 词表策略权重（默认0.4）
        weight_consistency: 列一致性权重（默认0.2）
    """

    DEPENDS_ON: list[str] = []  # 无依赖，可独立运行
    PROVIDES: list[str] = ["header_inference", "column_signatures"]

    def __init__(self, config=None):
        super().__init__(config)
        self.min_data_rows = self.config.get("min_data_rows", 3)
        self.max_lookback_rows = self.config.get("max_lookback_rows", 15)
        self.consistency_threshold = self.config.get("consistency_threshold", 0.7)
        self.weight_signature = self.config.get("weight_signature", 0.4)
        self.weight_vocab = self.config.get("weight_vocab", 0.4)
        self.weight_consistency = self.config.get("weight_consistency", 0.2)

    def process(self, result: ParseResult) -> ParseResult:
        tables_processed = 0
        headers_inferred = 0

        for p_idx, page in enumerate(result.pages):
            for t_idx, table_block in enumerate(page.tables):
                if len(table_block.rows) < 2:
                    continue
                if _has_explicit_header_contract(table_block):
                    tables_processed += 1
                    continue

                # Try to infer header
                inferred_header_idx, signature_confidence = self._infer_header(table_block)

                if inferred_header_idx is not None:
                    headers_inferred += 1

                    current_header_idx = -1
                    for idx, row in enumerate(table_block.rows):
                        if row.row_type == RowType.HEADER:
                            current_header_idx = idx
                            break

                    table_block.rows[inferred_header_idx].row_type = RowType.HEADER
                    table_block.headers = [c.cleaned or c.text for c in table_block.rows[inferred_header_idx].cells]

                    if current_header_idx < 0:
                        table_block.confidence = min(1.0, signature_confidence)
                        result.record_mutation(
                            middleware_name=self.name,
                            target_block_id=table_block.table_id or f"table_{t_idx}",
                            field_changed=f"pages[{p_idx}].tables[{t_idx}].headers",
                            old_value=None,
                            new_value=f"inferred_row_{inferred_header_idx}",
                            reason=f"Column signature inference (confidence={signature_confidence:.2f})",
                        )
                    else:
                        if inferred_header_idx != current_header_idx:
                            table_block.rows[current_header_idx].row_type = RowType.DATA
                            result.record_mutation(
                                middleware_name=self.name,
                                target_block_id=table_block.table_id or f"table_{t_idx}",
                                field_changed=f"pages[{p_idx}].tables[{t_idx}].headers",
                                old_value=f"row_{current_header_idx}",
                                new_value=f"inferred_row_{inferred_header_idx}",
                                reason="Signature inference override",
                            )

                tables_processed += 1

        logger.info(f"[HeaderInferrer] Processed {tables_processed} tables, inferred {headers_inferred} headers")
        return result

    def _infer_header(self, table_block) -> tuple[int | None, float]:
        """
        推断表格的表头行索引

        Args:
            table_block: 表格内容对象

        Returns:
            (表头行索引, 置信度) 或 (None, 0)
        """
        rows = table_block.rows
        if len(rows) < self.min_data_rows + 1:
            return None, 0.0  # 行数太少，无法推断

        best_header_idx = None
        best_score = -1.0

        # Candidate header rows: typically within the first 3 rows
        max_candidate_rows = min(3, len(rows) - self.min_data_rows)

        for candidate_idx in range(max_candidate_rows):
            # Get data rows below the candidate row
            data_start = candidate_idx + 1
            data_end = min(data_start + self.max_lookback_rows, len(rows))
            data_rows = rows[data_start:data_end]

            # Extract text values from data rows
            data_values = []
            for row in data_rows:
                row_values = [cell.text for cell in row.cells]
                data_values.append(row_values)

            # Transpose to column format
            num_cols = max(len(row) for row in data_values)
            column_signatures = []

            for col_idx in range(num_cols):
                # Extract values for this column
                col_values = []
                for row_values in data_values:
                    if col_idx < len(row_values):
                        col_values.append(row_values[col_idx])
                    else:
                        col_values.append("")

                # Infer type signatures
                signature = TypeSignatureLibrary.infer_signature(col_values)
                column_signatures.append(signature)

            # Compute overall consistency score
            avg_confidence = sum(sig.confidence for sig in column_signatures) / len(column_signatures)
            non_empty_ratio = sum(1 for sig in column_signatures if sig.confidence > 0.3) / len(column_signatures)

            # Type diversity bonus
            unique_types = len(set(sig.type_name for sig in column_signatures if sig.confidence > 0.3))
            diversity_bonus = min(1.0, unique_types / 3.0)

            # ── Entropy signal (Tao Te Ching · Approach 15) ──
            # High entropy in the candidate row + high type consistency in
            # data rows below = strong header indicator.
            entropy_bonus = self._compute_entropy_bonus(
                [cell.text for cell in rows[candidate_idx].cells],
                data_values,
            )

            # Composite score (entropy_bonus adds up to +0.15)
            score = avg_confidence * non_empty_ratio * (0.7 + 0.3 * diversity_bonus) + entropy_bonus

            # FIX-4a: Penalize candidates whose first cell is a pure digit
            # (sequence numbers like "1", "2" are data rows, not headers)
            first_cell = rows[candidate_idx].cells[0].text.strip() if rows[candidate_idx].cells else ""
            if first_cell.isdigit():
                score -= 0.3

            # Record signature to candidate row metadata
            if score > best_score:
                best_score = score
                best_header_idx = candidate_idx

                # Store in table metadata (will be used later)

        # Only return if score exceeds threshold
        if best_score >= self.consistency_threshold:
            return best_header_idx, best_score

        return None, 0.0

    def _compute_entropy_bonus(
        self,
        candidate_row: list[str],
        data_rows: list[list[str]],
    ) -> float:
        """Compute an entropy-based bonus for a header candidate.

        Uses information entropy (from 道德经·方案15) to distinguish header
        rows (high vocabulary diversity) from data rows (type repetition).

        Returns:
            Bonus value 0.0 – 0.15.
        """
        from docmirror.input.extraction.entropy_header import EntropyHeaderDetector

        detector = EntropyHeaderDetector()

        # Header-row entropy (high = diverse text = header-like)
        row_entropy = detector.calculate_entropy(candidate_row)

        # Data-row type consistency (high = uniform types below candidate)
        type_consistency = detector.analyze_type_consistency(data_rows)

        # Only grant a bonus when BOTH signals are strong
        if row_entropy > 0.5 and type_consistency > 0.5:
            return 0.15 * row_entropy * type_consistency

        return 0.0

    def _compute_hybrid_confidence(
        self,
        table_block,
        signature_idx: int,
        signature_confidence: float,
        vocab_confidence: float,
        vocab_idx: int,
    ) -> float:
        """
        计算融合表头置信度

        公式：
            confidence = weight_vocab × vocab_score
                       + weight_signature × signature_score
                       + weight_consistency × column_consistency
                       + agreement_bonus (如果一致)

        Args:
            table_block: 表格对象
            signature_idx: 签名推断的表头索引
            signature_confidence: 签名置信度
            vocab_confidence: 词表置信度
            vocab_idx: 词表推断的表头索引

        Returns:
            融合置信度 0-1
        """
        # Consistency bonus
        agreement_bonus = 0.1 if signature_idx == vocab_idx else 0.0

        # Compute column consistency score (existing logic)
        column_consistency = self._compute_column_consistency(table_block)

        # Fusion formula
        hybrid_confidence = (
            self.weight_vocab * vocab_confidence
            + self.weight_signature * signature_confidence
            + self.weight_consistency * column_consistency
            + agreement_bonus
        )

        return min(1.0, hybrid_confidence)

    def _compute_column_consistency(self, table_block) -> float:
        """
        计算列一致性得分（各行列数与表头列数一致的比例）

        这是现有的Validator逻辑的简化版，用于融合置信度计算。
        """
        if not table_block.header_row:
            return 0.0

        header_col_count = len(table_block.header_row.cells)
        if header_col_count == 0:
            return 0.0

        consistent_rows = 0
        total_data_rows = 0

        for row in table_block.rows:
            if row.row_type == "data":
                total_data_rows += 1
                if len(row.cells) == header_col_count:
                    consistent_rows += 1

        if total_data_rows == 0:
            return 0.0

        return consistent_rows / total_data_rows


def _has_explicit_header_contract(table_block) -> bool:
    """Return whether upstream extraction supplied authoritative headers."""
    if not getattr(table_block, "headers", None):
        return False
    extraction_layer = str(getattr(table_block, "extraction_layer", "") or "")
    metadata = getattr(table_block, "metadata", None) or {}
    if metadata.get("preserve_headers"):
        return True
    return extraction_layer in {"scanned_ocr_statement_grid"}
