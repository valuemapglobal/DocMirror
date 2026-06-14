# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Parse quality metrics for evaluation loop."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from docmirror.models.entities.parse_result import ParseResult


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", "", s.strip())


def char_preservation_rate(original_text: str, result: ParseResult) -> float:
    """Fraction of original visible chars preserved in mirror output."""
    if not original_text.strip():
        return 1.0
    mirror_text = result.full_text
    orig_chars = set(_normalize_text(original_text))
    if not orig_chars:
        return 1.0
    mirror_norm = _normalize_text(mirror_text)
    preserved = sum(1 for c in orig_chars if c in mirror_norm)
    return preserved / len(orig_chars)


def reading_order_score(result: ParseResult) -> float:
    """Heuristic reading order score based on monotonic reading_order fields."""
    orders = []
    for page in result.pages:
        for t in page.texts:
            orders.append(t.reading_order)
        for t in page.tables:
            orders.append(t.reading_order)
    if len(orders) < 2:
        return 1.0
    inversions = sum(1 for i in range(1, len(orders)) if orders[i] < orders[i - 1])
    return max(0.0, 1.0 - inversions / (len(orders) - 1))


def provenance_coverage(result: ParseResult) -> float:
    """Fraction of output blocks with evidence_ids."""
    total = 0
    linked = 0
    for page in result.pages:
        for t in page.texts:
            total += 1
            if t.evidence_ids:
                linked += 1
        for t in page.tables:
            total += 1
            if t.evidence_ids:
                linked += 1
    return linked / total if total else 1.0


def kv_field_f1(expected: dict[str, str], actual: dict[str, str]) -> float:
    """Field-level F1 for KV pairs."""
    if not expected and not actual:
        return 1.0
    if not expected:
        return 0.0
    tp = sum(1 for k, v in expected.items() if actual.get(k) == v)
    precision = tp / len(actual) if actual else 0.0
    recall = tp / len(expected)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _scalar_domain_value(value: Any) -> bool:
    return isinstance(value, (int, float, str, bool))


_DOMAIN_FIELD_SKIP = frozenset(
    {
        "layout_profile",
        "report_subtype",
        "document_subtype",
        "language",
        "region",
        "structured_data",
        "derived_variables",
        "extracted_entities",
        "quality_gate",
        "institution",
        "entities",
        "metadata",
    }
)


def extract_domain_fields(result: ParseResult) -> dict[str, Any]:
    """Collect scalar domain fields from domain_specific / structured_data."""
    domain = result.entities.domain_specific or {}
    out: dict[str, Any] = {}
    for source in (
        domain.get("derived_variables"),
        (domain.get("structured_data") or {}).get("derived_variables")
        if isinstance(domain.get("structured_data"), dict)
        else None,
    ):
        if isinstance(source, dict):
            for key, value in source.items():
                if _scalar_domain_value(value):
                    out[str(key)] = value
    for key, value in domain.items():
        if key in _DOMAIN_FIELD_SKIP:
            continue
        if _scalar_domain_value(value):
            out[str(key)] = value
    return out


def domain_field_f1(expected: dict[str, Any], actual: dict[str, Any]) -> float:
    """Recall on expected domain fields (§5.2 domain plugin gate).

    Extra fields in *actual* do not reduce the score — golden cases declare
    only the fields they care about.
    """
    if not expected and not actual:
        return 1.0
    if not expected:
        return 1.0
    exp = {str(k): v for k, v in expected.items() if _scalar_domain_value(v)}
    act = {str(k): v for k, v in actual.items() if _scalar_domain_value(v)}
    if not exp:
        return 1.0
    tp = sum(1 for k, v in exp.items() if act.get(k) == v)
    return tp / len(exp)


def table_structure_score(expected_cols: int, actual_cols: int) -> float:
    """Column count match score."""
    if expected_cols <= 0:
        return 1.0
    return max(0.0, 1.0 - abs(expected_cols - actual_cols) / expected_cols)


def transaction_row_count(result: ParseResult) -> float:
    """Domain transaction rows from structured_data, else table data rows."""
    domain = result.entities.domain_specific or {}
    structured = domain.get("structured_data") or {}
    if isinstance(structured, dict):
        txns = structured.get("transactions") or []
        if txns:
            return float(len(txns))
        count = structured.get("transaction_count")
        if isinstance(count, (int, float)) and count > 0:
            return float(count)
    return float(result.total_rows)


def compute_metrics(
    result: ParseResult,
    *,
    original_text: str = "",
    expected_kv: dict[str, str] | None = None,
    expected_table_cols: int = 0,
    expected_domain_fields: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Compute unified quality metrics for a parse result."""
    metrics: dict[str, float] = {
        "reading_order_score": reading_order_score(result),
        "provenance_coverage": provenance_coverage(result),
        "table_count": float(result.total_tables),
        "page_count": float(result.page_count),
        "transaction_row_count": transaction_row_count(result),
    }
    if original_text:
        metrics["char_preservation_rate"] = char_preservation_rate(original_text, result)
    if expected_kv is not None:
        metrics["kv_field_f1"] = kv_field_f1(expected_kv, result.all_key_values())
    if expected_domain_fields is not None:
        metrics["domain_field_f1"] = domain_field_f1(
            expected_domain_fields, extract_domain_fields(result)
        )
    if expected_table_cols > 0 and result.total_tables > 0:
        avg_cols = sum(len(t.headers) for t in result.all_tables()) / result.total_tables
        metrics["table_structure_score"] = table_structure_score(expected_table_cols, int(avg_cols))
    return metrics


def evidence_fingerprint(text: str) -> str:
    """Stable fingerprint for deduplication in full_text assembly."""
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]
