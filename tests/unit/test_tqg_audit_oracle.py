# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG extraction_audit oracle."""

from __future__ import annotations

from docmirror.core.evaluation.tqg.audit_oracle import run_extraction_audit_oracle


def test_audit_oracle_passes_minimal():
    class _Base:
        metadata = {
            "perf_breakdown": {
                "extraction_audit": {
                    "profile_id": "borderless_ledger_wechat",
                    "primary_logical_rows": 5111,
                    "pages": [
                        {"page": i, "candidates": [{"layer": "x"}], "picked": "pdfplumber_default", "score": 0.9}
                        for i in range(210)
                    ],
                    "quarantined_pages": [{"page": 219, "loss_reason": "col_count_mismatch"}],
                }
            }
        }

    report = run_extraction_audit_oracle(
        {"base": _Base()},
        {
            "profile_id": "borderless_ledger_wechat",
            "primary_logical_rows": 5111,
            "min_audit_pages": 200,
            "quarantine_page": 219,
            "quarantine_loss_reason": "col_count_mismatch",
            "require_bcs_candidates": True,
        },
    )
    assert report.passed, report.failures
