"""Error envelope coverage tests — W6-02 of the Failure & Degradation Contract.

Ensures every registered failure code can produce a complete error envelope
and that envelope fields match the FailureCodeRegistry metadata.
"""

from docmirror.configs.failure_codes import registry, build_error_envelope_from_code


class TestErrorEnvelopeCoverage:

    @classmethod
    def setup_class(cls):
        registry.load()

    def test_all_public_codes_have_envelope(self):
        """Every public code must produce a valid error envelope."""
        public_codes = registry.list_public()
        assert len(public_codes) > 0, "No public codes registered"

        for entry in public_codes:
            envelope = build_error_envelope_from_code(entry.user_code)
            assert envelope["code"] == entry.user_code
            assert envelope["canonical_code"] == entry.canonical_code
            assert "message" in envelope
            assert "scope" in envelope
            assert "recoverable" in envelope
            assert isinstance(envelope["recoverable"], bool)
            assert "retryable" in envelope
            assert isinstance(envelope["retryable"], bool)
            assert "suggestion" in envelope
            assert len(envelope["suggestion"]) > 0, f"No suggestion for {entry.user_code}"
            assert "docs_anchor" in envelope

    def test_input_category_codes(self):
        input_codes = registry.list_by_category("input")
        assert len(input_codes) >= 10  # minimum expected input codes
        for entry in input_codes:
            assert entry.default_scope == "document"

    def test_ocr_category_has_low_confidence(self):
        ocr_codes = registry.list_by_category("ocr")
        code_names = [e.user_code for e in ocr_codes]
        assert "low_ocr_confidence" in code_names, "OCR quality code missing"
        assert "low_quality_image" in code_names

    def test_table_category_has_quarantine(self):
        table_codes = registry.list_by_category("table")
        code_names = [e.user_code for e in table_codes]
        assert "table_merge_quarantined" in code_names

    def test_license_category_codes(self):
        license_codes = registry.list_by_category("license")
        code_names = [e.user_code for e in license_codes]
        assert "license_missing_degraded" in code_names
        assert "license_invalid" in code_names

    def test_domain_category_has_fallbacks(self):
        domain_codes = registry.list_by_category("domain")
        code_names = [e.user_code for e in domain_codes]
        assert "domain_not_ga_fallback" in code_names
        assert "domain_low_confidence_fallback" in code_names
        assert "domain_extraction_failed_fallback" in code_names

    def test_runtime_category_codes(self):
        runtime_codes = registry.list_by_category("runtime")
        code_names = [e.user_code for e in runtime_codes]
        for expected in ["timeout", "stage_timeout", "resource_limit_exceeded", "resource_budget_exhausted"]:
            assert expected in code_names, f"Missing runtime code: {expected}"

    def test_silent_failure_codes_present(self):
        artifact_codes = registry.list_by_category("artifact")
        code_names = [e.user_code for e in artifact_codes]
        for expected in ["artifact_missing", "silent_failure_detected", "silent_fallback_detected"]:
            assert expected in code_names, f"Missing silent failure code: {expected}"

    def test_user_code_to_canonical_roundtrip(self):
        for entry in registry.list_public():
            canonical = registry.user_to_canonical(entry.user_code)
            assert canonical == entry.canonical_code
            user = registry.canonical_to_user(entry.canonical_code)
            assert user == entry.user_code

    def test_unknown_code_has_fallback(self):
        envelope = build_error_envelope_from_code("nonexistent_code")
        assert envelope["code"] == "nonexistent_code"
        assert envelope["canonical_code"] == "NONEXISTENT_CODE"
        assert envelope["recoverable"] is False

    def test_severity_values_are_valid(self):
        valid_severities = {"info", "warning", "degraded", "partial", "error", "fatal"}
        for entry in registry.list_all():
            assert entry.severity in valid_severities, f"Invalid severity for {entry.user_code}: {entry.severity}"

    def test_recoverable_implies_suggestion(self):
        for entry in registry.list_all():
            if entry.recoverable:
                assert len(entry.default_suggestion) > 0, f"Recoverable code {entry.user_code} has no suggestion"
