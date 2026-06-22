"""Outcome Ledger contract tests — W6-03 of the Failure & Degradation Contract.

Validates that the OutcomeEvent and OutcomeLedger schemas produce correct
serialization, that every required field is populated, and that status
derivation follows the FDC invariants.
"""

from docmirror.models.outcome import OutcomeEvent, OutcomeLedger, PageOutcome


class TestOutcomeEventContract:

    def test_event_has_required_fields(self):
        event = OutcomeEvent(
            status="partial",
            code="low_ocr_confidence",
            canonical_code="LOW_OCR_CONFIDENCE",
            category="ocr",
            severity="partial",
            scope={"type": "page", "pages": [2, 5]},
            message="OCR confidence below threshold.",
            suggestion="Retry with profile=forensic.",
        )
        d = event.to_dict()
        required = ["event_id", "status", "code", "canonical_code", "category",
                     "severity", "scope", "message", "suggestion", "recoverable",
                     "retryable", "timestamp"]
        for key in required:
            assert key in d, f"Missing required field: {key}"

    def test_event_id_is_unique(self):
        e1 = OutcomeEvent()
        e2 = OutcomeEvent()
        assert e1.event_id != e2.event_id

    def test_event_retained_output(self):
        event = OutcomeEvent(
            status="degraded",
            code="license_missing_degraded",
            canonical_code="LICENSE_MISSING_DEGRADED",
            retained_output={"mirror": True, "community": True, "enterprise": "degraded"},
        )
        assert event.to_dict()["retained_output"]["mirror"] is True


class TestOutcomeLedgerContract:

    def test_ledger_initial_state(self):
        ledger = OutcomeLedger(request_id="req_test", task_id="task_test")
        assert ledger.status == "success"
        assert len(ledger.events) == 0
        assert ledger.summary["has_errors"] is False

    def test_ledger_status_derives_from_events(self):
        ledger = OutcomeLedger(request_id="req_001")
        ledger.add_event(OutcomeEvent(status="failure", code="unsupported_format",
                                       canonical_code="UNSUPPORTED_FORMAT", severity="error"))
        assert ledger.status == "failed"
        assert ledger.summary["has_errors"] is True
        assert ledger.summary["errors_count"] == 1

    def test_ledger_partial_with_page_outcomes(self):
        ledger = OutcomeLedger(request_id="req_002")
        ledger.add_page_outcome(PageOutcome(page=1, status="success"))
        ledger.add_page_outcome(PageOutcome(page=2, status="failure", retained=False))
        assert ledger.status == "partial"
        assert ledger.summary["retained_success_pages"] is True

    def test_ledger_degraded_status(self):
        ledger = OutcomeLedger(request_id="req_003")
        ledger.add_event(OutcomeEvent(status="degraded", code="domain_not_ga_fallback",
                                       canonical_code="DOMAIN_NOT_GA_FALLBACK", severity="degraded"))
        assert ledger.status == "degraded"
        assert ledger.summary["has_degradations"] is True

    def test_ledger_roundtrip(self):
        ledger = OutcomeLedger(request_id="req_004", task_id="task_004")
        ledger.add_event(OutcomeEvent(status="warning", code="low_ocr_confidence",
                                       canonical_code="LOW_OCR_CONFIDENCE", severity="warning",
                                       scope={"type": "page", "pages": [3]}))
        ledger.add_page_outcome(PageOutcome(page=1, status="success"))
        d = ledger.to_dict()
        ledger2 = OutcomeLedger.from_dict(d)
        assert ledger2.request_id == "req_004"
        assert len(ledger2.events) == 1
        assert len(ledger2.page_outcomes) == 1

    def test_ledger_summary_counts(self):
        ledger = OutcomeLedger(request_id="req_005")
        ledger.add_event(OutcomeEvent(status="failure", code="timeout",
                                       canonical_code="TIMEOUT", severity="error"))
        ledger.add_event(OutcomeEvent(status="warning", code="low_ocr_confidence",
                                       canonical_code="LOW_OCR_CONFIDENCE", severity="warning"))
        ledger.add_event(OutcomeEvent(status="degraded", code="license_missing_degraded",
                                       canonical_code="LICENSE_MISSING_DEGRADED", severity="degraded"))
        s = ledger.summary
        assert s["errors_count"] == 1
        assert s["warnings_count"] == 1
        assert s["degradations_count"] == 1
        assert s["has_errors"] is True
        assert s["has_warnings"] is True
        assert s["has_degradations"] is True
