# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CQF canonical row audit tests."""

from __future__ import annotations

from docmirror.plugins.bank_statement.canonical_quality import (
    audit_cqf,
    is_canonical_row,
    resolve_extract_status,
)


def test_is_canonical_row_requires_directional_amount():
    assert is_canonical_row({"date": "2024-01-01", "direction": "income", "amount": 10.0})
    assert not is_canonical_row({"date": "2024-01-01", "direction": "other", "amount": 10.0})
    assert not is_canonical_row({"direction": "income", "amount": 10.0})


def test_audit_cqf_degraded_when_canonical_low():
    records = [
        {"normalized": {"date": "2024-01-01", "direction": "other", "amount": 1.0}},
        {"normalized": {"date": "2024-01-02", "direction": "other", "amount": 2.0}},
    ]
    result = audit_cqf(records, canonical_expected=100)
    assert result.extract_status == "degraded"
    assert result.canonical_extracted == 0


def test_audit_cqf_success():
    records = [
        {"normalized": {"date": "2024-01-01", "direction": "income", "amount": 1.0}}
        for _ in range(80)
    ]
    result = audit_cqf(records, canonical_expected=100)
    assert result.extract_status == "success"
    assert result.canonical_ratio >= 0.80


def test_resolve_extract_status_thresholds():
    assert resolve_extract_status(coverage_ratio=0.9, canonical_ratio=0.9) == "success"
    assert resolve_extract_status(coverage_ratio=0.6, canonical_ratio=0.6) == "low_coverage"
    assert resolve_extract_status(coverage_ratio=0.3, canonical_ratio=0.3) == "degraded"
