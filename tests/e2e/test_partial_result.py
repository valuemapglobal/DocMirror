# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""G13: Partial Result e2e acceptance tests.

GA 1.0 SS4.12 C4: For a mixed-quality document (3 pages normal + 1 page broken),
output contains partial_result with success pages retained and failed pages marked;
quality_decision is needs_review.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docmirror.evidence.bundle import _build_page_status_ledger
from docmirror.models.mirror.page_access import PageStatus
from docmirror.output.projection.resolver import build_partial_result_envelope


class TestPageStatusEnum:
    """Test PageStatus enumeration and helpers."""

    def test_all_values_present(self):
        assert PageStatus.success.value == "success"
        assert PageStatus.partial.value == "partial"
        assert PageStatus.failure.value == "failure"
        assert PageStatus.skipped.value == "skipped"

    def test_str_matches_value(self):
        assert str(PageStatus.success) == "success"
        assert str(PageStatus.failure) == "failure"

    def test_from_exception_none_returns_success(self):
        assert PageStatus.from_exception(None) == PageStatus.success

    def test_from_exception_with_error_returns_partial(self):
        assert PageStatus.from_exception(ValueError("bad parse")) == PageStatus.partial

    def test_from_exception_skipped_flag(self):
        assert PageStatus.from_exception(None, skipped=True) == PageStatus.skipped
        # skipped flag overrides exception
        assert PageStatus.from_exception(ValueError("err"), skipped=True) == PageStatus.skipped

    def test_is_ok(self):
        assert PageStatus.success.is_ok is True
        assert PageStatus.partial.is_ok is True
        assert PageStatus.failure.is_ok is False
        assert PageStatus.skipped.is_ok is False

    def test_needs_review(self):
        assert PageStatus.success.needs_review is False
        assert PageStatus.partial.needs_review is True
        assert PageStatus.failure.needs_review is True
        assert PageStatus.skipped.needs_review is False


class TestBuildPartialResultEnvelope:
    """Test build_partial_result_envelope() function."""

    def test_complete_success(self):
        partial_output = {
            "document_id": "doc-001",
            "total_pages": 5,
            "success_pages": [1, 2, 3, 4, 5],
            "failed_pages": [],
            "partial_pages": [],
            "skipped_pages": [],
            "retention_rate": 1.0,
        }
        envelope = build_partial_result_envelope(partial_output)
        assert envelope["partial_result"] is False
        assert envelope["total_pages"] == 5
        assert envelope["success_count"] == 5
        assert envelope["failure_count"] == 0
        assert envelope["skipped_count"] == 0
        assert envelope["page_level_retention"] == 1.0
        assert envelope["needs_review"] is False
        assert envelope["output_status"] == "complete"

    def test_mixed_quality_partial(self):
        partial_output = {
            "document_id": "doc-002",
            "total_pages": 4,
            "success_pages": [1, 3],
            "failed_pages": [
                {"page": 2, "status": "failure", "error_code": "ocr_failure"},
                {"page": 4, "status": "failure", "error_code": "table_corrupt"},
            ],
            "partial_pages": [],
            "skipped_pages": [],
            "retention_rate": 0.5,
        }
        envelope = build_partial_result_envelope(partial_output)
        assert envelope["partial_result"] is True
        assert envelope["total_pages"] == 4
        assert envelope["success_count"] == 2
        assert envelope["failure_count"] == 2
        assert envelope["page_level_retention"] == 0.5
        assert envelope["needs_review"] is True
        assert envelope["output_status"] == "partial"
        assert len(envelope["failed_page_details"]) == 2
        assert envelope["failed_page_details"][0]["error_code"] == "ocr_failure"

    def test_with_skipped_pages(self):
        partial_output = {
            "document_id": "doc-003",
            "total_pages": 3,
            "success_pages": [1],
            "failed_pages": [],
            "partial_pages": [],
            "skipped_pages": [2, 3],
            "retention_rate": 0.3333,
        }
        envelope = build_partial_result_envelope(partial_output)
        assert envelope["partial_result"] is True
        assert envelope["success_count"] == 1
        assert envelope["skipped_count"] == 2
        assert envelope["output_status"] == "partial"
        assert envelope["status_reason"] == "Some pages were skipped"
        assert envelope["needs_review"] is True

    def test_with_partial_pages(self):
        partial_output = {
            "document_id": "doc-004",
            "total_pages": 3,
            "success_pages": [1, 2, 3],
            "failed_pages": [],
            "partial_pages": [
                {"page": 2, "status": "partial", "error_code": "partial_table_parse"},
            ],
            "skipped_pages": [],
            "retention_rate": 1.0,
        }
        envelope = build_partial_result_envelope(partial_output)
        assert envelope["partial_result"] is True
        assert envelope["failure_count"] == 1  # partial_pages count as failures
        assert envelope["needs_review"] is True

    def test_domain_and_support_level(self):
        partial_output = {
            "document_id": "doc-005",
            "total_pages": 1,
            "success_pages": [1],
            "failed_pages": [],
            "partial_pages": [],
            "skipped_pages": [],
            "retention_rate": 1.0,
        }
        envelope = build_partial_result_envelope(
            partial_output, domain="bank_statement", support_level="L2"
        )
        assert envelope["domain"] == "bank_statement"
        assert envelope["support_level"] == "L2"


class TestPageStatusLedger:
    """Test page_status_ledger in evidence bundle."""

    def test_build_page_status_ledger_from_result(self):
        """_build_page_status_ledger must correctly count per-page status."""
        result = type("FakeResult", (), {})()
        result.pages = []
        ledger = _build_page_status_ledger(result)
        assert ledger["total_pages"] == 0
        assert ledger["page_level_partial_retention"] == 0.0

    def test_fallback_empty_pages(self):
        """When result has no pages, ledger reports 0 pages."""
        result = type("FakeResult", (), {})()
        result.pages = []
        ledger = _build_page_status_ledger(result)
        assert ledger["total_pages"] == 0
        assert ledger["page_level_partial_retention"] == 0.0
        assert ledger["outcomes"] == []


class TestQualityDecisionWithPartialResult:
    """Test that quality_decision reflects partial result status."""

    def test_build_quality_decision_block_returns_valid_dict(self):
        from docmirror.evidence.quality_decision import QualityDecisionReport

        qd_block = QualityDecisionReport(
            document_id="d1", task_id="t1",
            decision="needs_review",
            decision_reason="2 of 4 pages failed",
            confidence_policy="ga_default_v1",
        ).to_dict()

        assert qd_block["decision"] == "needs_review"
        assert qd_block["version"] == 2
        assert "needs_review" in qd_block
        assert "decision_reason" in qd_block
        assert "blocking_issues" in qd_block

    def test_quality_decision_auto_ingest_when_clean(self):
        from docmirror.evidence.quality_decision import QualityDecisionReport

        qd_block = QualityDecisionReport(
            document_id="d2", task_id="t2",
            decision="auto_ingest",
            decision_reason="all checks passed",
            confidence_policy="ga_default_v1",
        ).to_dict()

        assert qd_block["decision"] == "auto_ingest"

    def test_quality_decision_reject(self):
        from docmirror.evidence.quality_decision import QualityDecisionReport

        qd_block = QualityDecisionReport(
            document_id="d3", task_id="t3",
            decision="reject",
            decision_reason="schema validation failed on all pages",
            confidence_policy="ga_default_v1",
        ).to_dict()

        assert qd_block["decision"] == "reject"


class TestPartialResultEndToEnd:
    """G13 acceptance: mixed-quality document produces partial output with needs_review."""

    def test_partial_result_with_mixed_pages(self, tmp_path: Path):
        """
        Simulate a 4-page document where 2 pages succeed and 2 fail.
        The partial output must reflect this correctly.
        """
        partial_output = {
            "document_id": "mixed-quality-doc",
            "total_pages": 4,
            "success_pages": [1, 3],
            "failed_pages": [
                {"page": 2, "status": "failure", "error_code": "ocr_failure"},
                {"page": 4, "status": "failure", "error_code": "page_corrupt"},
            ],
            "partial_pages": [],
            "skipped_pages": [],
            "retention_rate": 0.5,
        }

        # Build partial result envelope
        envelope = build_partial_result_envelope(partial_output)

        # Verification: G13 checks
        assert envelope["partial_result"] is True, (
            "G13: partial_result must be True when pages fail"
        )
        assert envelope["success_count"] == 2, (
            "G13: success_count should be 2 (pages 1 and 3)"
        )
        assert envelope["failure_count"] == 2, (
            "G13: failure_count should be 2 (pages 2 and 4)"
        )
        assert envelope["page_level_retention"] == 0.5, (
            "G13: page_level_retention should be 0.5 (2/4)"
        )
        assert envelope["needs_review"] is True, (
            "G13: needs_review must be True when pages fail"
        )
        assert envelope["output_status"] == "partial", (
            "G13: output_status must be 'partial'"
        )
        assert len(envelope["failed_page_details"]) == 2, (
            "G13: failed_page_details must list 2 pages"
        )

    def test_partial_result_with_skipped_pages(self):
        """G13: Skipped pages also trigger partial result."""
        partial_output = {
            "document_id": "skipped-doc",
            "total_pages": 3,
            "success_pages": [1],
            "failed_pages": [],
            "partial_pages": [
                {"page": 2, "status": "partial", "error_code": "partial_ocr"},
            ],
            "skipped_pages": [3],
            "retention_rate": 0.6667,
        }

        envelope = build_partial_result_envelope(partial_output)

        assert envelope["partial_result"] is True
        assert envelope["failure_count"] == 1  # partial page counts as failure
        assert envelope["skipped_count"] == 1
        assert envelope["needs_review"] is True
        # Skipped pages are tracked
        assert 3 in envelope["skipped_page_numbers"]

    def test_no_partial_result_when_all_pages_succeed(self):
        """G13: When all pages succeed, no partial result is flagged."""
        partial_output = {
            "document_id": "clean-doc",
            "total_pages": 3,
            "success_pages": [1, 2, 3],
            "failed_pages": [],
            "partial_pages": [],
            "skipped_pages": [],
            "retention_rate": 1.0,
        }

        envelope = build_partial_result_envelope(partial_output)

        assert envelope["partial_result"] is False
        assert envelope["output_status"] == "complete"
        assert envelope["needs_review"] is False
