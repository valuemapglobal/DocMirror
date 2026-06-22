# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Four-layer Fidelity Metric Computation — QTC §6.2.

Provides computation helpers for the four fidelity layers:
- Text: CER, char preservation, garbled ratio, OCR confidence, language detection
- Layout: reading order, bbox coverage, table TEDS, cross-page continuity, noise leakage
- Business: field accuracy, record count fidelity, amount/date/account normalization, schema validation
- Audit: source refs coverage, bbox evidence, evidence completeness, needs_review recall, no-evidence rate

These helpers are designed to be called from:
- TQG benchmark runners (with golden data)
- Observation event population (with incremental metrics)
- BucketedMetricsAggregator (for per-bucket computation)

When golden data is unavailable, metrics return float('nan') to indicate "not measurable".
"""

from __future__ import annotations

import math
from typing import Any, Sequence


# ── Text Fidelity (W2-01) ───────────────────────────────────────────────────

def compute_cer(observed_text: str, golden_text: str) -> float:
    """Character Error Rate between observed and golden text.

    Uses Levenshtein distance normalized by golden length.
    Returns NaN if golden_text is empty.
    """
    if not golden_text:
        return float('nan')
    if not observed_text:
        return 1.0

    # Wagner-Fischer Levenshtein
    m, n = len(golden_text), len(observed_text)
    if m == 0 and n == 0:
        return 0.0
    if m == 0:
        return 1.0

    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, m + 1):
            temp = dp[j]
            if observed_text[i - 1] == golden_text[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp

    return dp[m] / m


def compute_char_preservation_rate(observed_text: str, golden_text: str) -> float:
    """Fraction of golden characters present in observed text (case-insensitive)."""
    if not golden_text:
        return float('nan')
    golden_set = set(golden_text.lower())
    observed_set = set(observed_text.lower())
    if not golden_set:
        return 1.0
    return len(golden_set & observed_set) / len(golden_set)


def compute_garbled_ratio(text: str, min_len: int = 10) -> float:
    """Estimate garbled character ratio by counting non-printable / replacement chars."""
    if len(text) < min_len:
        return float('nan')
    garbled = sum(1 for c in text if c in '\ufffd\x00\x01\x02' or (ord(c) < 32 and c not in '\n\r\t'))
    return garbled / len(text)


def compute_ocr_confidence_avg(confidences: Sequence[float]) -> float:
    """Average OCR confidence across tokens/lines."""
    if not confidences:
        return float('nan')
    valid = [c for c in confidences if not math.isnan(c)]
    if not valid:
        return float('nan')
    return sum(valid) / len(valid)


def estimate_language(text: str) -> str:
    """Simple CJK vs Latin language heuristic."""
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff')
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    if cjk > latin:
        return "cjk"
    elif latin > cjk:
        return "latin"
    return "mixed"


def check_language_match(observed_lang: str, expected_lang: str) -> bool:
    """Check if observed language category matches expected."""
    if not expected_lang:
        return True
    return observed_lang.lower() == expected_lang.lower()


# ── Layout Fidelity (W2-02) ─────────────────────────────────────────────────

def compute_reading_order_accuracy(
    observed_order: Sequence[int], golden_order: Sequence[int]
) -> float:
    """Longest common subsequence ratio for reading order alignment."""
    if not golden_order:
        return float('nan')

    # LCS length
    m, n = len(observed_order), len(golden_order)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(n):
            if observed_order[i] == golden_order[j]:
                dp[i + 1][j + 1] = dp[i][j] + 1
            else:
                dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])

    return dp[m][n] / n


def compute_bbox_coverage(
    items_with_bbox: int, total_items: int
) -> float:
    """Fraction of items that have bbox annotations."""
    if total_items <= 0:
        return float('nan')
    return items_with_bbox / total_items


def compute_table_structure_score(
    observed_rows: int, golden_rows: int,
    observed_cols: int, golden_cols: int,
) -> float:
    """Approximate table structure fidelity (simplified TEDS-like).
    
    Returns 1.0 for perfect match, decreasing with dimensional mismatches.
    """
    if golden_rows <= 0 or golden_cols <= 0:
        return float('nan')
    row_score = 1.0 - abs(observed_rows - golden_rows) / max(golden_rows, 1)
    col_score = 1.0 - abs(observed_cols - golden_cols) / max(golden_cols, 1)
    return max(0.0, min(1.0, (row_score + col_score) / 2))


def compute_cross_page_continuity(
    cross_page_spans_retained: int, cross_page_spans_total: int,
) -> float:
    """Fraction of cross-page logical units that are retained."""
    if cross_page_spans_total <= 0:
        return float('nan')
    return cross_page_spans_retained / cross_page_spans_total


def compute_noise_leakage_rate(
    noise_char_count: int, total_char_count: int,
) -> float:
    """Fraction of text that is header/footer noise leaking into body."""
    if total_char_count <= 0:
        return float('nan')
    return noise_char_count / total_char_count


# ── Business Fidelity (W2-03) ───────────────────────────────────────────────

def compute_field_accuracy(
    matched_fields: int, total_fields: int,
) -> float:
    """P0 field exact or normalized match rate."""
    if total_fields <= 0:
        return float('nan')
    return matched_fields / total_fields


def compute_record_count_fidelity(
    observed_records: int, golden_records: int,
) -> float:
    """Transaction row count fidelity for finance domains."""
    if golden_records <= 0:
        return float('nan')
    return 1.0 - abs(observed_records - golden_records) / golden_records


def compute_amount_accuracy(
    matched_amounts: int, total_amounts: int,
) -> float:
    """Amount field accuracy (value/sign/currency alignment)."""
    if total_amounts <= 0:
        return float('nan')
    return matched_amounts / total_amounts


def compute_date_accuracy(
    matched_dates: int, total_dates: int,
) -> float:
    """Date field accuracy (raw/date/time/timezone alignment)."""
    if total_dates <= 0:
        return float('nan')
    return matched_dates / total_dates


def compute_account_serial_accuracy(
    matched_ids: int, total_ids: int,
) -> float:
    """Account/serial/invoice number key field accuracy."""
    if total_ids <= 0:
        return float('nan')
    return matched_ids / total_ids


# ── Audit Fidelity (W2-04) ──────────────────────────────────────────────────

def compute_source_refs_coverage(
    fields_with_refs: int, total_p0_fields: int,
) -> float:
    """Evidence source references coverage for P0 key fields."""
    if total_p0_fields <= 0:
        return float('nan')
    return fields_with_refs / total_p0_fields


def compute_bbox_evidence_coverage(
    key_fields_with_bbox: int, total_key_fields: int,
) -> float:
    """Bbox evidence coverage for key fields (target >= 95%)."""
    if total_key_fields <= 0:
        return float('nan')
    return key_fields_with_bbox / total_key_fields


def compute_evidence_completeness(
    fields_with_complete_evidence: int, total_fields: int,
) -> float:
    """Fraction of fields with complete evidence (field/record/section)."""
    if total_fields <= 0:
        return float('nan')
    return fields_with_complete_evidence / total_fields


def compute_needs_review_recall(
    recalled_low_confidence: int, total_low_confidence_golden: int,
) -> float:
    """Recall of needs_review for golden low-confidence fields (target >= 95%)."""
    if total_low_confidence_golden <= 0:
        return float('nan')
    return recalled_low_confidence / total_low_confidence_golden


def compute_no_evidence_auto_accept_rate(
    auto_accepted_no_evidence: int, total_fields: int,
) -> float:
    """Rate of auto-accepted fields without evidence (MUST be 0)."""
    if total_fields <= 0:
        return float('nan')
    return auto_accepted_no_evidence / total_fields


# ── Layer aggregator helpers ─────────────────────────────────────────────────

def build_text_fidelity_layer(
    *,
    cer: float = float('nan'),
    char_preservation: float = float('nan'),
    garbled_ratio: float = float('nan'),
    ocr_confidence: float = float('nan'),
    language_match: bool = True,
    item_count: int = 0,
) -> dict[str, Any]:
    """Build a text fidelity metric layer for observation events."""
    valid_metrics = {}
    for k, v in {
        "cer": cer, "char_preservation_rate": char_preservation,
        "garbled_ratio": garbled_ratio, "ocr_confidence_avg": ocr_confidence,
    }.items():
        if not math.isnan(v):
            valid_metrics[k] = v

    failures = []
    if not math.isnan(cer) and cer > 0.05:
        failures.append(f"CER {cer:.2%} exceeds 5%")
    if not math.isnan(garbled_ratio) and garbled_ratio > 0.01:
        failures.append(f"Garbled ratio {garbled_ratio:.2%} exceeds 1%")
    if not language_match:
        failures.append("Language mismatch")

    overall = 1.0
    if not math.isnan(cer):
        overall = min(overall, 1.0 - cer)
    if not math.isnan(char_preservation):
        overall = min(overall, char_preservation)

    return {
        "score": round(overall, 4),
        "status": "fail" if failures else ("not_measured" if not valid_metrics else "pass"),
        "metrics": valid_metrics,
        "denominator": item_count,
        "failed_items": failures,
        "evidence_refs": [],
    }


def build_layout_fidelity_layer(
    *,
    reading_order_accuracy: float = float('nan'),
    bbox_coverage: float = float('nan'),
    table_structure_score: float = float('nan'),
    cross_page_continuity: float = float('nan'),
    noise_leakage: float = float('nan'),
    item_count: int = 0,
) -> dict[str, Any]:
    """Build a layout fidelity metric layer for observation events."""
    valid_metrics = {}
    for k, v in {
        "reading_order_accuracy": reading_order_accuracy,
        "bbox_coverage": bbox_coverage,
        "table_structure_score": table_structure_score,
        "cross_page_continuity": cross_page_continuity,
        "noise_leakage_rate": noise_leakage,
    }.items():
        if not math.isnan(v):
            valid_metrics[k] = v

    failures = []
    if not math.isnan(reading_order_accuracy) and reading_order_accuracy < 0.90:
        failures.append(f"Reading order accuracy {reading_order_accuracy:.2%} below 90%")
    if not math.isnan(bbox_coverage) and bbox_coverage < 0.80:
        failures.append(f"Bbox coverage {bbox_coverage:.2%} below 80%")
    if not math.isnan(cross_page_continuity) and cross_page_continuity < 0.95:
        failures.append(f"Cross-page continuity {cross_page_continuity:.2%} below 95%")

    overall = 1.0
    for v in [reading_order_accuracy, bbox_coverage, table_structure_score, cross_page_continuity]:
        if not math.isnan(v):
            overall = min(overall, v)

    return {
        "score": round(overall, 4),
        "status": "fail" if failures else ("not_measured" if not valid_metrics else "pass"),
        "metrics": valid_metrics,
        "denominator": item_count,
        "failed_items": failures,
        "evidence_refs": [],
    }


def build_business_fidelity_layer(
    *,
    field_accuracy: float = float('nan'),
    record_count_fidelity: float = float('nan'),
    amount_accuracy: float = float('nan'),
    date_accuracy: float = float('nan'),
    account_serial_accuracy: float = float('nan'),
    schema_validation_pass: bool = True,
    item_count: int = 0,
    domain: str = "generic",
) -> dict[str, Any]:
    """Build a business fidelity metric layer for observation events."""
    valid_metrics = {}
    for k, v in {
        "field_accuracy": field_accuracy,
        "record_count_fidelity": record_count_fidelity,
        "amount_accuracy": amount_accuracy,
        "date_accuracy": date_accuracy,
        "account_serial_accuracy": account_serial_accuracy,
    }.items():
        if not math.isnan(v):
            valid_metrics[k] = v

    failures = []
    if not math.isnan(field_accuracy) and field_accuracy < 0.99:
        failures.append(f"Field accuracy {field_accuracy:.2%} below 99%")
    if not schema_validation_pass:
        failures.append("Schema validation failed")

    # Finance domains have stricter requirements
    if domain in ("bank_statement", "payment_flow", "vat_invoice", "credit_report"):
        if not math.isnan(amount_accuracy) and amount_accuracy < 0.99:
            failures.append(f"Amount accuracy {amount_accuracy:.2%} below 99% (finance)")
        if not math.isnan(record_count_fidelity) and record_count_fidelity < 0.98:
            failures.append(f"Record count fidelity {record_count_fidelity:.2%} below 98% (finance)")

    overall = 1.0
    for v in [field_accuracy, record_count_fidelity, amount_accuracy, date_accuracy, account_serial_accuracy]:
        if not math.isnan(v):
            overall = min(overall, v)

    return {
        "score": round(overall, 4),
        "status": "fail" if failures else ("not_measured" if not valid_metrics else "pass"),
        "metrics": valid_metrics,
        "denominator": item_count,
        "failed_items": failures,
        "evidence_refs": [],
    }


def build_audit_fidelity_layer(
    *,
    source_refs_coverage: float = float('nan'),
    bbox_evidence_coverage: float = float('nan'),
    evidence_completeness: float = float('nan'),
    needs_review_recall: float = float('nan'),
    no_evidence_auto_accept_rate: float = float('nan'),
    item_count: int = 0,
) -> dict[str, Any]:
    """Build an audit fidelity metric layer for observation events."""
    valid_metrics = {}
    for k, v in {
        "source_refs_coverage": source_refs_coverage,
        "bbox_evidence_coverage": bbox_evidence_coverage,
        "evidence_completeness": evidence_completeness,
        "needs_review_recall": needs_review_recall,
        "no_evidence_auto_accept_rate": no_evidence_auto_accept_rate,
    }.items():
        if not math.isnan(v):
            valid_metrics[k] = v

    failures = []
    if not math.isnan(source_refs_coverage) and source_refs_coverage < 0.95:
        failures.append(f"Source refs coverage {source_refs_coverage:.2%} below 95%")
    if not math.isnan(bbox_evidence_coverage) and bbox_evidence_coverage < 0.95:
        failures.append(f"Bbox evidence coverage {bbox_evidence_coverage:.2%} below 95%")
    if not math.isnan(no_evidence_auto_accept_rate) and no_evidence_auto_accept_rate > 0:
        failures.append(f"No-evidence auto-accept rate {no_evidence_auto_accept_rate} must be 0")
    if not math.isnan(needs_review_recall) and needs_review_recall < 0.95:
        failures.append(f"Needs-review recall {needs_review_recall:.2%} below 95%")

    overall = 1.0
    for v in [source_refs_coverage, bbox_evidence_coverage, evidence_completeness]:
        if not math.isnan(v):
            overall = min(overall, v)

    return {
        "score": round(overall, 4),
        "status": "fail" if failures else ("not_measured" if not valid_metrics else "pass"),
        "metrics": valid_metrics,
        "denominator": item_count,
        "failed_items": failures,
        "evidence_refs": [],
    }
