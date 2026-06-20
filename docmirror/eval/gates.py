# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Quality gate profiles and failure attribution (EFPA CCC-5).

Defines gate tiers (extract, mirror, semantic, licensing), oracle modes for
expected row counts, and ``FailureClass`` taxonomy so benchmark and TQG runs
can attribute misses to adapter, middleware, or plugin layers. Gate YAML
profiles are loaded from ``configs/yaml/test/gates/``.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

import yaml
from pydantic import BaseModel, Field

from docmirror.configs.paths import YAML_DIR
from docmirror.core.analyze.spe_consumer import mirror_expected_primary_rows
from docmirror.models.entities.parse_result import ParseResult

logger = logging.getLogger(__name__)


class OracleMode(str, Enum):
    """How EXTRACT_GATE derives expected row counts."""

    NONE = "none"
    ABSOLUTE = "absolute"
    PDFPLUMBER_FULL_PAGE_SAMPLE = "pdfplumber_full_page_sample"


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
    oracle_mode: OracleMode = OracleMode.NONE
    oracle_sample_pages: int = 3  # pages sampled when oracle_mode=pdfplumber_full_page_sample


def _builtin_gate_profiles() -> dict[str, QualityGateProfile]:
    return {
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
            oracle_mode=OracleMode.PDFPLUMBER_FULL_PAGE_SAMPLE,
            oracle_sample_pages=3,
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


def _profile_from_yaml_entry(entry: dict[str, Any]) -> QualityGateProfile:
    oracle_raw = str(entry.get("oracle_mode", "none")).lower()
    oracle_mode = OracleMode.NONE
    if oracle_raw == "pdfplumber_full_page_sample":
        oracle_mode = OracleMode.PDFPLUMBER_FULL_PAGE_SAMPLE
    elif oracle_raw == "absolute":
        oracle_mode = OracleMode.ABSOLUTE
    return QualityGateProfile(
        profile_id=str(entry.get("profile_id", "generic")),
        min_char_preservation=float(entry.get("min_char_preservation", 0.90)),
        min_reading_order=float(entry.get("min_reading_order", 0.70)),
        min_transaction_rows=int(entry.get("min_transaction_rows", 0)),
        min_table_count=int(entry.get("min_table_count", 0)),
        max_empty_row_ratio=float(entry.get("max_empty_row_ratio", 0.50)),
        expected_merged_table=bool(entry.get("expected_merged_table", False)),
        min_merge_confidence=float(entry.get("min_merge_confidence", 0.65)),
        min_row_preservation_ratio=float(entry.get("min_row_preservation_ratio", 0.0)),
        min_logical_rows=int(entry.get("min_logical_rows", 0)),
        max_logical_rows=int(entry.get("max_logical_rows", 0)),
        oracle_mode=oracle_mode,
        oracle_sample_pages=int(entry.get("oracle_sample_pages", 3)),
    )


def load_gate_profiles_from_yaml() -> dict[str, QualityGateProfile]:
    """Load GATE_PROFILES from configs/yaml/test/gates/extract.yaml profiles section."""
    path = YAML_DIR / "test" / "gates" / "extract.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("Failed to load gate profiles YAML: %s", exc)
        return {}
    profiles_raw = data.get("profiles") or {}
    out: dict[str, QualityGateProfile] = {}
    for key, entry in profiles_raw.items():
        if isinstance(entry, dict):
            out[str(key)] = _profile_from_yaml_entry(entry)
    return out


def _merge_gate_profiles() -> dict[str, QualityGateProfile]:
    merged = _builtin_gate_profiles()
    yaml_profiles = load_gate_profiles_from_yaml()
    merged.update(yaml_profiles)
    return merged


GATE_PROFILES: dict[str, QualityGateProfile] = _merge_gate_profiles()


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
                f"CROSS_PAGE_CHECK: {lt.logical_id or lt.table_id} merge_confidence {mc:.3f} < {confidence_threshold}"
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
                failures.append(f"CROSS_PAGE_CHECK: {lt.logical_id or lt.table_id} source_pages have gaps")

    return QualityGateResult(
        passed=len(failures) == 0,
        failure_class=FailureClass.TABLE_EXTRACTION if failures else None,
        failures=failures,
        metrics=metrics,
        checks=checks,
    )


def _primary_logical_row_count(result: ParseResult) -> int:
    """Row count for cross-page merged ledgers — Mirror LTQG SSOT when enabled."""
    return mirror_expected_primary_rows(result)


def _physical_row_count(result: ParseResult) -> int:
    return sum(len(tb.rows) for pg in result.pages for tb in pg.tables)


def dual_view_consistency_metrics(
    result: ParseResult,
    *,
    quarantined_tables: list[dict[str, Any]] | None = None,
) -> dict[str, float | int]:
    """Physical vs logical row accounting for dual-view regression checks."""
    quarantined = quarantined_tables or []
    primary = _primary_logical_row_count(result)
    total_logical = sum(lt.row_count for lt in result.logical_tables) if result.logical_tables else 0
    physical = _physical_row_count(result)
    quarantine_rows = sum(int(q.get("row_count") or q.get("rows") or 0) for q in quarantined)
    return {
        "primary_logical_rows": primary,
        "total_logical_rows": total_logical,
        "physical_row_count": physical,
        "quarantine_row_count": quarantine_rows,
        "quarantine_page_count": len(quarantined),
        "logical_minus_primary": total_logical - primary,
    }


def dual_view_consistency_check(
    result: ParseResult,
    *,
    quarantined_tables: list[dict[str, Any]] | None = None,
    max_secondary_logical_rows: int = 10,
) -> QualityGateResult:
    """E9 guard — primary logical rows stable; secondary logical tables bounded."""
    metrics_raw = dual_view_consistency_metrics(result, quarantined_tables=quarantined_tables)
    metrics = {k: float(v) for k, v in metrics_raw.items()}
    failures: list[str] = []
    checks: dict[str, bool] = {}

    primary = int(metrics_raw["primary_logical_rows"])
    total_logical = int(metrics_raw["total_logical_rows"])
    gap = int(metrics_raw["logical_minus_primary"])

    checks["primary_le_total_logical"] = primary <= total_logical
    if not checks["primary_le_total_logical"]:
        failures.append(f"DUAL_VIEW: primary_logical {primary} > total_logical {total_logical}")

    checks["primary_present"] = primary > 0
    if primary <= 0:
        failures.append("DUAL_VIEW: primary logical row count is zero")

    # Secondary logical tables (footnote / quarantine pages) should be small vs primary.
    checks["secondary_logical_bounded"] = gap <= max_secondary_logical_rows
    if gap > max_secondary_logical_rows:
        failures.append(
            f"DUAL_VIEW: secondary logical rows {gap} > {max_secondary_logical_rows} "
            f"(primary={primary}, total={total_logical})"
        )

    return QualityGateResult(
        passed=len(failures) == 0,
        failure_class=FailureClass.TABLE_EXTRACTION if failures else None,
        failures=failures,
        metrics=metrics,
        checks=checks,
    )


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

    physical_rows = sum(len(tb.rows) for pg in result.pages for tb in pg.tables)
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
        failures.append(f"EXTRACT_GATE: logical_rows {logical_rows} < {profile.min_logical_rows}")
        checks["min_logical_rows"] = False
    else:
        checks["min_logical_rows"] = True

    if profile and profile.max_logical_rows and logical_rows > profile.max_logical_rows:
        failures.append(f"EXTRACT_GATE: logical_rows {logical_rows} > {profile.max_logical_rows}")
        checks["max_logical_rows"] = False
    else:
        checks["max_logical_rows"] = True

    use_oracle_ratio = (
        profile
        and profile.min_row_preservation_ratio > 0
        and oracle_row_count > 0
        and profile.oracle_mode == OracleMode.PDFPLUMBER_FULL_PAGE_SAMPLE
    )
    if use_oracle_ratio:
        ratio = logical_rows / oracle_row_count
        metrics["row_preservation_ratio"] = ratio
        metrics["oracle_row_count"] = float(oracle_row_count)
        checks["row_preservation"] = ratio >= profile.min_row_preservation_ratio
        if ratio < profile.min_row_preservation_ratio:
            failures.append(
                f"EXTRACT_GATE: row_preservation {ratio:.4f} < {profile.min_row_preservation_ratio} "
                f"(logical={logical_rows}, oracle={oracle_row_count})"
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
    from docmirror.eval.metrics import compute_metrics

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
            failures.append(f"logical_rows {logical_rows} < {profile.min_transaction_rows}")
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
