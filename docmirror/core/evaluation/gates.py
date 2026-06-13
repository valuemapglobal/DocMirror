# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Quality gate profiles and failure attribution (EFPA CCC-5)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from docmirror.models.entities.parse_result import ParseResult


class FailureClass(str, Enum):
    INPUT_QUALITY = "input_quality"
    LAYOUT_CONFLICT = "layout_conflict"
    OCR_INSUFFICIENT = "ocr_insufficient"
    TABLE_EXTRACTION = "table_extraction"
    PLUGIN_SCHEMA = "plugin_schema"
    VALIDATION_FAILED = "validation_failed"
    UNKNOWN = "unknown"


class QualityGateProfile(BaseModel):
    """Per document-category quality thresholds."""

    profile_id: str = "generic"
    min_char_preservation: float = 0.90
    min_reading_order: float = 0.70
    min_transaction_rows: int = 0
    min_table_count: int = 0
    max_empty_row_ratio: float = 0.50
    expected_merged_table: bool = False  # 跨页合并且合并后数据完整的文档跳过 page_loss
    min_merge_confidence: float = 0.65  # CROSS_PAGE_CHECK threshold for logical_tables
    min_row_preservation_ratio: float = 0.0  # EXTRACT_GATE: min logical/physical row ratio
    min_logical_rows: int = 0  # EXTRACT_GATE: absolute floor for ledger documents
    max_logical_rows: int = 0  # EXTRACT_GATE: absolute ceiling (0 = no cap)


GATE_PROFILES: dict[str, QualityGateProfile] = {
    "generic": QualityGateProfile(profile_id="generic"),
    "alipay_payment": QualityGateProfile(
        profile_id="alipay_payment",
        min_char_preservation=0.99,
        min_transaction_rows=10,
        min_table_count=1,
        max_empty_row_ratio=0.30,
        expected_merged_table=True,
        min_logical_rows=1400,
    ),
    "wechat_payment": QualityGateProfile(
        profile_id="wechat_payment",
        min_char_preservation=0.99,
        min_transaction_rows=10,
        min_table_count=1,
        max_empty_row_ratio=0.30,
        expected_merged_table=True,
        min_row_preservation_ratio=0.995,
        min_logical_rows=5111,
        max_logical_rows=5111,
    ),
    "bank_statement": QualityGateProfile(
        profile_id="bank_statement",
        min_char_preservation=0.95,
        min_transaction_rows=3,
    ),
    "credit_report": QualityGateProfile(
        profile_id="credit_report",
        min_char_preservation=0.98,
        min_reading_order=0.85,
    ),
}


class QualityGateResult(BaseModel):
    passed: bool = True
    failure_class: FailureClass | None = None
    failures: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    checks: dict[str, bool] = Field(default_factory=dict)


def cross_page_check(
    result: ParseResult,
    *,
    confidence_threshold: float = 0.7,
) -> QualityGateResult:
    """Enterprise CROSS_PAGE_CHECK — validate logical table merge quality."""
    failures: list[str] = []
    checks: dict[str, bool] = {}
    metrics: dict[str, float] = {}

    if not result.logical_tables:
        checks["has_logical_tables"] = False
        return QualityGateResult(passed=True, checks=checks, metrics=metrics)

    checks["has_logical_tables"] = True
    for lt in result.logical_tables:
        mc = lt.merge_confidence
        metrics[f"{lt.logical_id or lt.table_id}_merge_confidence"] = mc
        if len(lt.source_pages) > 1 and mc < confidence_threshold:
            failures.append(
                f"CROSS_PAGE_CHECK: {lt.logical_id or lt.table_id} "
                f"merge_confidence {mc:.3f} < {confidence_threshold}"
            )
            checks[f"{lt.table_id}_confidence_ok"] = False
        else:
            checks[f"{lt.table_id}_confidence_ok"] = True

        if len(lt.source_pages) > 1:
            sorted_pages = sorted(lt.source_pages)
            gaps = [
                sorted_pages[i + 1] - sorted_pages[i]
                for i in range(len(sorted_pages) - 1)
                if sorted_pages[i + 1] - sorted_pages[i] > 1
            ]
            gap_ok = len(gaps) == 0
            checks[f"{lt.table_id}_pages_continuous"] = gap_ok
            if not gap_ok:
                failures.append(
                    f"CROSS_PAGE_CHECK: {lt.logical_id or lt.table_id} source_pages have gaps"
                )

    return QualityGateResult(
        passed=len(failures) == 0,
        failure_class=FailureClass.TABLE_EXTRACTION if failures else None,
        failures=failures,
        metrics=metrics,
        checks=checks,
    )


def _primary_logical_row_count(result: ParseResult) -> int:
    """Row count for cross-page merged ledgers — primary table only, excludes quarantine."""
    if not result.logical_tables:
        return 0
    return max(lt.row_count for lt in result.logical_tables)


def extract_row_preservation_check(
    result: ParseResult,
    *,
    profile: QualityGateProfile | None = None,
    oracle_row_count: int = 0,
) -> QualityGateResult:
    """EXTRACT_GATE — validate physical/logical row counts vs thresholds."""
    failures: list[str] = []
    checks: dict[str, bool] = {}
    metrics: dict[str, float] = {}

    physical_rows = sum(
        len(tb.rows)
        for pg in result.pages
        for tb in pg.tables
    )
    if result.logical_tables:
        if profile and profile.expected_merged_table:
            logical_rows = _primary_logical_row_count(result)
            metrics["logical_table_count"] = float(len(result.logical_tables))
        else:
            logical_rows = sum(lt.row_count for lt in result.logical_tables)
    else:
        logical_rows = physical_rows
    metrics["physical_row_count"] = float(physical_rows)
    metrics["logical_row_count"] = float(logical_rows)

    if profile and profile.min_logical_rows and logical_rows < profile.min_logical_rows:
        failures.append(
            f"EXTRACT_GATE: logical_rows {logical_rows} < {profile.min_logical_rows}"
        )
        checks["min_logical_rows"] = False
    else:
        checks["min_logical_rows"] = True

    if profile and profile.max_logical_rows and logical_rows > profile.max_logical_rows:
        failures.append(
            f"EXTRACT_GATE: logical_rows {logical_rows} > {profile.max_logical_rows}"
        )
        checks["max_logical_rows"] = False
    else:
        checks["max_logical_rows"] = True

    if profile and profile.min_row_preservation_ratio > 0 and oracle_row_count > 0:
        ratio = logical_rows / oracle_row_count
        metrics["row_preservation_ratio"] = ratio
        checks["row_preservation"] = ratio >= profile.min_row_preservation_ratio
        if ratio < profile.min_row_preservation_ratio:
            failures.append(
                f"EXTRACT_GATE: row_preservation {ratio:.4f} < {profile.min_row_preservation_ratio}"
            )
    else:
        checks["row_preservation"] = True

    return QualityGateResult(
        passed=len(failures) == 0,
        failure_class=FailureClass.TABLE_EXTRACTION if failures else None,
        failures=failures,
        metrics=metrics,
        checks=checks,
    )


def evaluate_quality_gate(
    result: ParseResult,
    *,
    document_type: str = "generic",
    original_text: str = "",
    structured_data: dict[str, Any] | None = None,
) -> QualityGateResult:
    """Run quality gate for a parse result."""
    from docmirror.core.evaluation.metrics import compute_metrics

    profile = GATE_PROFILES.get(document_type, GATE_PROFILES["generic"])
    metrics = compute_metrics(result, original_text=original_text)
    failures: list[str] = []
    failure_class: FailureClass | None = None

    cp = metrics.get("char_preservation_rate", 1.0)
    ro = metrics.get("reading_order_score", 1.0)
    if cp < profile.min_char_preservation:
        failures.append(f"char_preservation {cp:.3f} < {profile.min_char_preservation}")
        failure_class = FailureClass.INPUT_QUALITY

    if ro < profile.min_reading_order:
        failures.append(f"reading_order {ro:.3f} < {profile.min_reading_order}")
        failure_class = failure_class or FailureClass.LAYOUT_CONFLICT

    if profile.min_table_count and result.total_tables < profile.min_table_count:
        failures.append(f"table_count {result.total_tables} < {profile.min_table_count}")
        failure_class = failure_class or FailureClass.TABLE_EXTRACTION

    if profile.expected_merged_table and result.logical_tables:
        logical_rows = sum(lt.row_count for lt in result.logical_tables)
        metrics["logical_row_count"] = float(logical_rows)
        if profile.min_transaction_rows and logical_rows < profile.min_transaction_rows:
            failures.append(
                f"logical_rows {logical_rows} < {profile.min_transaction_rows}"
            )
            failure_class = failure_class or FailureClass.PLUGIN_SCHEMA

        cp_result = cross_page_check(result, confidence_threshold=profile.min_merge_confidence)
        metrics.update(cp_result.metrics)
        if not cp_result.passed:
            failures.extend(cp_result.failures)
            failure_class = failure_class or FailureClass.TABLE_EXTRACTION

    txn_count = 0
    if structured_data:
        txn_count = structured_data.get("transaction_count") or len(structured_data.get("transactions") or [])
    if profile.min_transaction_rows and txn_count < profile.min_transaction_rows:
        failures.append(f"transaction_rows {txn_count} < {profile.min_transaction_rows}")
        failure_class = failure_class or FailureClass.PLUGIN_SCHEMA

    return QualityGateResult(
        passed=len(failures) == 0,
        failure_class=failure_class,
        failures=failures,
        metrics={k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))},
    )
