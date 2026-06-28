"""
Cross-page table predictor — detects truncated tables spanning pages.

Purpose: Predicts when a table continues on the next page and validates merge
candidates using column profiles and truncation heuristics.

Main components: ``CrossPageTablePredictor``, ``TruncationInfo``,
``NextPagePrediction``.

Upstream: Sequential page table blocks, ``table.signature``.

Downstream: ``structure.fusion``, ``table.compose``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from docmirror.models.entities.domain import PageLayout

logger = logging.getLogger(__name__)


@dataclass
class TruncationInfo:
    """Truncation info for page N."""

    incomplete_rows: int = 0  # incomplete rows count
    incomplete_row_indices: list[int] = field(default_factory=list)
    last_col_signature: dict[str, Any] = field(default_factory=dict)
    cross_page_header: dict[str, Any] = field(default_factory=dict)
    col_types: list[str] = field(default_factory=list)
    col_count: int = 0
    page_idx: int = 0
    has_trailing_continuation: bool = False  # whether trailing continuation marker exists ("续", "...")


@dataclass
class NextPagePrediction:
    """Prediction info for page N+1."""

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
    """Merge and verify results."""

    is_valid: bool = False
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CrossPageTablePredictor:
    """Cross-page table prediction engine.

    Principles:
      - After extracting page N, record truncation information
      - Before extracting page N+1, predict the table structure
      - Guide the extractor using prediction information
    """

    def __init__(self, confidence_threshold: float = 0.7):
        """Initialize the prediction engine.

        Args:
            confidence_threshold: confidence threshold (predictions below this are ignored)
        """
        self.confidence_threshold = confidence_threshold
        self._state: TruncationInfo | None = None
        self._prediction_history: list[tuple[TruncationInfo, NextPagePrediction]] = []

    def record_truncation(self, page_layout: PageLayout, extraction_result: Any, page_idx: int = 0) -> TruncationInfo:
        """Record truncation info for page N.

        Args:
            page_layout: Page layout
            extraction_result: Extraction result (TableExtractionResult)
            page_idx: Page index

        Returns:
            TruncationInfo: Truncation info
        """
        info = TruncationInfo(page_idx=page_idx)

        # 1. Detect incomplete rows (missing closing bracket/period)
        info.incomplete_rows = self._detect_incomplete_rows(page_layout)

        # 2. Record last column structure
        if hasattr(extraction_result, "structured_data") and extraction_result.structured_data:
            table = extraction_result.structured_data[0] if extraction_result.structured_data else None
            if table and hasattr(table, "columns"):
                info.col_count = len(table.columns)
                info.last_col_signature = self._extract_col_signature(table, page_layout)
                info.col_types = self._infer_col_types(table)

        # 3. Detect continuation markers ("续", "...", etc.)
        info.has_trailing_continuation = self._detect_continuation_markers(page_layout)

        # 4. Detect potential cross-page headers
        info.cross_page_header = self._detect_cross_page_header(page_layout)

        # Save state
        self._state = info

        logger.debug(
            f"📊 Record truncation info for page {page_idx}: "
            f"cols={info.col_count}, "
            f"incomplete_rows={info.incomplete_rows}, "
            f"continuation={info.has_trailing_continuation}"
        )

        return info

    def predict_next_page(self, truncation_info: TruncationInfo) -> NextPagePrediction:
        """Predict table structure for page N+1.

        Args:
            truncation_info: Page N truncation info

        Returns:
            NextPagePrediction: Prediction info
        """
        prediction = NextPagePrediction()

        # 1. Predict column count
        prediction.predicted_col_count = truncation_info.col_count

        # 2. Predict column types
        prediction.predicted_col_types = truncation_info.col_types.copy()

        # 3. Compute confidence
        confidence = self._calculate_prediction_confidence(truncation_info)
        prediction.confidence = confidence

        # 4. Predict merge pattern
        if truncation_info.incomplete_rows > 0 or truncation_info.has_trailing_continuation:
            prediction.predicted_merge_pattern = "append"
        else:
            prediction.predicted_merge_pattern = "new_table"

        # 5. Generate warnings
        if confidence < self.confidence_threshold:
            prediction.warnings.append(f"Prediction confidence too low ({confidence:.2f} < {self.confidence_threshold})")

        if truncation_info.col_count == 0:
            prediction.warnings.append("Page N: no table columns detected")

        # Save history
        self._prediction_history.append((truncation_info, prediction))

        logger.debug(
            f"🔮 Predicting page N+1: "
            f"cols={prediction.predicted_col_count}, "
            f"confidence={confidence:.2f}, "
            f"merge_pattern={prediction.predicted_merge_pattern}"
        )

        return prediction

    def validate_merge(self, truncation_info: TruncationInfo, next_page_result: Any) -> MergeValidation:
        """Validate cross-page merge effectiveness.

        Args:
            truncation_info: Page N truncation info
            next_page_result: Page N+1 extraction result

        Returns:
            MergeValidation: Validation result
        """
        validation = MergeValidation()
        score = 0.0
        max_score = 0.0

        # 1. Column count validation (weight 40%)
        max_score += 40
        if truncation_info.col_count > 0 and next_page_result:
            next_col_count = self._get_result_col_count(next_page_result)
            if next_col_count > 0:
                col_diff = abs(truncation_info.col_count - next_col_count)
                if col_diff == 0:
                    score += 40
                    validation.reasons.append("Column count exact match")
                elif col_diff == 1:
                    score += 25  # permit 1-column diff (possibly merged cells)
                    validation.warnings.append(f"Column count diff of 1 ({truncation_info.col_count} vs {next_col_count})")
                else:
                    validation.reasons.append(f"Column count diff too large ({col_diff})")
            else:
                validation.warnings.append("Page N+1: no columns detected")

        # 2. Column type validation (weight 30%)
        max_score += 30
        if truncation_info.col_types and next_page_result:
            next_col_types = self._get_result_col_types(next_page_result)
            if next_col_types:
                type_matches = sum(1 for t1, t2 in zip(truncation_info.col_types, next_col_types) if t1 == t2)
                type_match_rate = type_matches / max(len(truncation_info.col_types), len(next_col_types))
                score += 30 * type_match_rate

                if type_match_rate >= 0.8:
                    validation.reasons.append(f"Column type match rate high ({type_match_rate:.2f})")
                elif type_match_rate >= 0.5:
                    validation.warnings.append(f"Column type match rate medium ({type_match_rate:.2f})")
                else:
                    validation.warnings.append(f"Column type match rate low ({type_match_rate:.2f})")

        # 3. Continuation marker validation (weight 20%)
        max_score += 20
        if truncation_info.has_trailing_continuation:
            score += 20
            validation.reasons.append("Continuation marker detected, merge supported")

        # 4. Incomplete row validation (weight 10%)
        max_score += 10
        if truncation_info.incomplete_rows > 0:
            score += 10
            validation.reasons.append(f"Detected {truncation_info.incomplete_rows} incomplete rows")

        # Compute final score
        validation.score = score / max_score if max_score > 0 else 0.0
        validation.is_valid = validation.score >= self.confidence_threshold

        logger.debug(f"✅ Merge validation: score={validation.score:.2f}, valid={validation.is_valid}, reasons={validation.reasons}")

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

    def validate_table_row_boundary_merge(
        self,
        prev_rows: list[Any],
        next_rows: list[Any],
        *,
        prev_page_no: int = 0,
        next_page_no: int = 0,
        deviation_threshold_px: float = 5.0,
    ) -> MergeValidation:
        """Validate cross-page merge using row text plus median column boundaries.

        If table cells carry geometry, this adds the design-01 median boundary
        check: build a robust column-boundary profile for each page and flag
        pages whose boundary drift exceeds ``deviation_threshold_px``. When
        geometry is missing, the method falls back to raw row validation.
        """
        prev_text_rows = [_row_texts(row) for row in prev_rows]
        next_text_rows = [_row_texts(row) for row in next_rows]
        validation = self.validate_raw_table_merge(
            prev_text_rows,
            next_text_rows,
            prev_page_no=prev_page_no,
            next_page_no=next_page_no,
        )

        prev_boundaries = _median_column_boundaries(prev_rows)
        next_boundaries = _median_column_boundaries(next_rows)
        if not prev_boundaries or not next_boundaries:
            validation.warnings.append("Column boundary verification skipped: missing cell geometry")
            return validation

        if len(prev_boundaries) != len(next_boundaries):
            validation.is_valid = False
            validation.score = min(validation.score, 0.4)
            validation.reasons.append(
                f"Column boundary count mismatch ({len(prev_boundaries)} vs {len(next_boundaries)})"
            )
            return validation

        deviations = [abs(left - right) for left, right in zip(prev_boundaries, next_boundaries)]
        max_deviation = max(deviations, default=0.0)
        avg_deviation = sum(deviations) / len(deviations) if deviations else 0.0
        if max_deviation <= deviation_threshold_px:
            validation.score = max(validation.score, 0.85)
            validation.is_valid = validation.score >= self.confidence_threshold
            validation.reasons.append(
                f"Column boundaries stable (max deviation {max_deviation:.1f}px, avg {avg_deviation:.1f}px)"
            )
        else:
            validation.is_valid = False
            validation.score = min(validation.score, 0.65)
            validation.warnings.append(
                f"Column boundary deviation too large ({max_deviation:.1f}px > {deviation_threshold_px:.1f}px)"
            )
        return validation

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
        """Reset prediction state."""
        self._state = None
        self._prediction_history.clear()

    def get_prediction_history(self) -> list[tuple[TruncationInfo, NextPagePrediction]]:
        """Get prediction history.

        Returns:
            List of prediction history records
        """
        return self._prediction_history.copy()

    # ========== Private Methods ==========

    def _detect_incomplete_rows(self, page_layout: PageLayout) -> int:
        """Detect incomplete rows (missing closing bracket/period at end)."""
        incomplete_count = 0

        for block in page_layout.blocks:
            # Simplified check: no BlockType dependency
            if not hasattr(block, "block_type"):
                continue

            block_type_value = block.block_type.value if hasattr(block.block_type, "value") else str(block.block_type)
            if block_type_value != "table":
                continue

            if not hasattr(block, "text"):
                continue

            # Check the last row of the table
            lines = block.text.strip().split("\n")
            if lines:
                last_line = lines[-1].strip()
                if self._is_incomplete_line(last_line):
                    incomplete_count += 1

        return incomplete_count

    def _is_incomplete_line(self, line: str) -> bool:
        """Determine whether a row is incomplete."""
        if not line:
            return False

        # Check if ending marker is missing
        incomplete_markers = [
            not line.endswith(("。", "；", "）", ")", "」", "】", ".", ";", ")", "]")),
            line.endswith(("...", "…", "续", "接")),  # continuation marker check
        ]

        return any(incomplete_markers)

    def _detect_continuation_markers(self, page_layout: PageLayout) -> bool:
        """Detect whether a page has continuation markers."""
        for block in page_layout.blocks:
            if not hasattr(block, "text"):
                continue

            text = block.text.lower()
            if any(marker in text for marker in ["续", "续表", "...", "…", "continued"]):
                return True

        return False

    def _detect_cross_page_header(self, page_layout: PageLayout) -> dict[str, Any]:
        """Detect possible cross-page headers."""
        # Simplified implementation: check first row of first table
        for block in page_layout.blocks:
            # Simplified check: no BlockType dependency
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
        """Extract column signature."""
        # Simplified implementation: return column count and names
        signature = {
            "col_count": len(table.columns) if hasattr(table, "columns") else 0,
        }

        if hasattr(table, "columns"):
            signature["col_names"] = [c.get("name", "") for c in table.columns]

        return signature

    def _infer_col_types(self, table: Any) -> list[str]:
        """Infer column types."""
        # Simplified implementation: infer from column names or sample data
        col_types = []

        if hasattr(table, "columns"):
            for col in table.columns:
                col_name = col.get("name", "").lower() if isinstance(col, dict) else str(col).lower()

                # Infer from column names
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
        """Compute prediction confidence."""
        confidence = 0.5  # base confidence

        # Has explicit column count
        if truncation_info.col_count > 0:
            confidence += 0.2

        # Has continuation marker
        if truncation_info.has_trailing_continuation:
            confidence += 0.15

        # Has incomplete rows
        if truncation_info.incomplete_rows > 0:
            confidence += 0.1

        # Has column type information
        if truncation_info.col_types:
            confidence += 0.05

        return min(confidence, 1.0)

    def _get_result_col_count(self, result: Any) -> int:
        """Get column count from extraction result."""
        if hasattr(result, "structured_data") and result.structured_data:
            table = result.structured_data[0]
            if hasattr(table, "columns"):
                return len(table.columns)
        return 0

    def _get_result_col_types(self, result: Any) -> list[str]:
        """Get column types from extraction result."""
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


def _row_texts(row: Any) -> list[str]:
    cells = getattr(row, "cells", None)
    if cells is not None:
        return [str(getattr(cell, "text", cell)) for cell in cells]
    if isinstance(row, list | tuple):
        return [str(cell) for cell in row]
    return [str(row)]


def _median_column_boundaries(rows: list[Any]) -> list[float]:
    """Return median [left, separators..., right] boundaries from cell bboxes."""
    samples: list[list[float]] = []
    for row in rows:
        cells = list(getattr(row, "cells", []) or [])
        positioned = [
            cell
            for cell in cells
            if isinstance(getattr(cell, "bbox", None), list | tuple) and len(getattr(cell, "bbox", [])) >= 4
        ]
        if len(positioned) < 2:
            continue
        positioned.sort(key=lambda cell: (
            getattr(cell, "col_index", None) if getattr(cell, "col_index", None) is not None else 10_000,
            float(getattr(cell, "bbox")[0]),
        ))
        boundaries = [float(positioned[0].bbox[0])]
        for left, right in zip(positioned, positioned[1:]):
            boundaries.append((float(left.bbox[2]) + float(right.bbox[0])) / 2.0)
        boundaries.append(float(positioned[-1].bbox[2]))
        if len(boundaries) >= 3:
            samples.append(boundaries)

    if not samples:
        return []
    width = len(samples[0])
    compatible = [sample for sample in samples if len(sample) == width]
    if not compatible:
        return []
    return [float(median(sample[i] for sample in compatible)) for i in range(width)]
