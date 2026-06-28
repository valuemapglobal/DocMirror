# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for TQG Mirror conservation oracle fields."""

from __future__ import annotations

from docmirror.eval.tqg.conservation_oracles import run_mirror_conservation_oracle


def _api_payload() -> dict:
    return {
        "data": {
            "document": {
                "text": "A sufficiently long forensic text snapshot.",
                "raw_text": "A sufficiently long raw forensic text snapshot.",
                "pages": [
                    {
                        "page_number": 1,
                        "width": 612,
                        "height": 792,
                        "flow": {"texts": [{"content": "hello", "evidence_ids": ["txt_1"]}]},
                        "texts": [{"content": "hello", "evidence_ids": ["txt_1"]}],
                        "tables": [
                            {
                                "table_id": "pt_1_0",
                                "extraction_layer": "pdfplumber_default",
                                "evidence_ids": ["tbl_1"],
                                "rows": [{"cells": [{"text": "42"}]}],
                            }
                        ],
                    }
                ],
                "logical_tables": [
                    {
                        "logical_id": "lt_1",
                        "row_count": 1,
                        "rows": [{"cells": [{"text": "42"}]}],
                    }
                ],
            }
        },
        "meta": {
            "conservation": {
                "passed": True,
                "error_count": 0,
                "warning_count": 0,
                "issues": [],
                "metrics": {
                    "physical_table_count": 1,
                    "logical_table_count": 1,
                    "logical_row_count": 1,
                    "evidence_span_count": 2,
                    "hypothesis_count": 1,
                },
            },
            "ehl": {
                "evidence_summary": {"total_spans": 2},
                "hypotheses": [{"kind": "table", "method": "bcs", "selected": True}],
                "quarantine": {"physical_tables": [{"reason": "low_confidence"}]},
            },
        },
    }


def test_mirror_conservation_oracle_accepts_full_surface_requirements():
    report = run_mirror_conservation_oracle(
        _api_payload(),
        {
            "passed": True,
            "max_errors": 0,
            "max_warnings": 0,
            "min_pages": 1,
            "min_text_blocks": 1,
            "min_text_chars": 20,
            "min_physical_tables": 1,
            "min_logical_tables": 1,
            "min_logical_rows": 1,
            "min_evidence_spans": 2,
            "min_hypotheses": 1,
            "require_ehl": True,
            "require_raw_text": True,
            "require_page_dimensions": True,
            "require_text_evidence": True,
            "require_table_evidence": True,
            "require_table_layer": True,
            "require_candidate_audit": True,
            "require_quarantine_annex": True,
            "forbidden_issue_codes": ["logical_row_provenance_missing"],
        },
        case_id="unit",
    )

    assert report.passed, report.failures
    assert report.metrics["page_count"] == 1
    assert report.metrics["logical_row_count"] == 1


def test_mirror_conservation_oracle_reports_missing_required_surfaces():
    payload = _api_payload()
    page = payload["pages"][0]
    (page.get("flow") or {}).setdefault("texts", page.get("texts") or [])
    page["flow"]["texts"][0]["evidence_ids"] = []
    if page.get("texts"):
        page["texts"][0]["evidence_ids"] = []
    payload["meta"]["ehl"]["hypotheses"] = []

    report = run_mirror_conservation_oracle(
        payload,
        {
            "require_text_evidence": True,
            "require_candidate_audit": True,
        },
        case_id="unit",
    )

    assert not report.passed
    assert "expected at least one text block evidence_ids" in report.failures
    assert "expected BCS candidate hypotheses in meta.ehl" in report.failures
