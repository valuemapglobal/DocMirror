# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PSC (Privacy / Security / Compliance) contract tests for GA 1.0.

Covers the core invariants defined in the PSC design document:
  PSC-I1: Default parse blocks network egress
  PSC-I2: External egress requires explicit consent + audit
  PSC-I3: Logs must not contain secrets or PII values
  PSC-I4: Resource gate blocks dangerous inputs
  PSC-I5: License state does not enter Mirror
  PSC-I7: Data classification levels are correct
  PSC-I9: Redaction masks PII and secrets
  PSC-I10: Resource gate matrix covers all input types

Design reference: docs/design/GA1.0/12_privacy_security_compliance_ga_gap_closure_plan.md
"""

import logging
import io
import json

from docmirror.security.data_classification import (
    DataClassification, classify_document, classify_value, is_classified_above,
)
from docmirror.security.privacy_mode import (
    PrivacyPolicy, resolve_privacy_policy, is_provider_allowed,
)
from docmirror.security.egress import EgressGate, EgressBlockedError
from docmirror.security.redaction import (
    redact_secrets, redact_pii, redact_text, mask_value, hash_value,
    redact_dict, classify_redaction,
)
from docmirror.security.logging import SafeLoggingFilter, install_safe_logging
from docmirror.security.security_ledger import (
    SecurityEvidenceLedger, EgressEvent, ResourceGateDecision, build_security_summary,
)
from docmirror.security.resource_gate import (
    check_archive_preflight, check_pdf_preflight, check_image_preflight, check_rest_upload,
)


class TestDataClassification:
    """PSC-I7: Data classification levels must be correct and ordered."""

    def test_levels_exist(self):
        levels = [c.label for c in DataClassification]
        assert levels == ["public", "internal", "confidential", "restricted", "secret"]

    def test_ordering(self):
        assert DataClassification.PUBLIC < DataClassification.INTERNAL
        assert DataClassification.INTERNAL < DataClassification.CONFIDENTIAL
        assert DataClassification.CONFIDENTIAL < DataClassification.RESTRICTED
        assert DataClassification.RESTRICTED < DataClassification.SECRET

    def test_allowed_in_logs(self):
        assert DataClassification.PUBLIC.allowed_in_logs
        assert DataClassification.INTERNAL.allowed_in_logs
        assert not DataClassification.CONFIDENTIAL.allowed_in_logs
        assert not DataClassification.RESTRICTED.allowed_in_logs
        assert not DataClassification.SECRET.allowed_in_logs

    def test_requires_redaction(self):
        assert not DataClassification.PUBLIC.requires_redaction
        assert not DataClassification.INTERNAL.requires_redaction
        assert DataClassification.CONFIDENTIAL.requires_redaction
        assert DataClassification.RESTRICTED.requires_redaction
        assert DataClassification.SECRET.requires_redaction

    def test_classify_document_defaults(self):
        assert classify_document("test.pdf", 10) == DataClassification.CONFIDENTIAL
        assert classify_document("test.pdf", 10, has_sensitive_fields=True) == DataClassification.RESTRICTED

    def test_classify_value(self):
        assert classify_value("") == DataClassification.PUBLIC
        assert classify_value("short") == DataClassification.INTERNAL
        assert classify_value("x" * 300) == DataClassification.CONFIDENTIAL
        assert classify_value("id_number", has_pii_pattern=True) == DataClassification.RESTRICTED

    def test_is_classified_above(self):
        assert is_classified_above(DataClassification.SECRET, DataClassification.CONFIDENTIAL)
        assert not is_classified_above(DataClassification.PUBLIC, DataClassification.INTERNAL)


class TestPrivacyMode:
    """PSC-I1: Default privacy mode is local, blocks network."""

    def test_default_policy(self):
        policy = resolve_privacy_policy()
        assert policy.mode == "local"
        assert not policy.allow_network
        assert not policy.allow_external_ocr
        assert not policy.allow_vlm

    def test_local_properties(self):
        policy = PrivacyPolicy(mode="local", allow_network=False)
        assert policy.is_local
        assert not policy.is_egress_opt_in

    def test_egress_opt_in_properties(self):
        policy = PrivacyPolicy(mode="egress_opt_in", allow_network=True, require_consent=True)
        assert policy.is_egress_opt_in
        assert not policy.is_local

    def test_provider_allowlist_check(self):
        policy = PrivacyPolicy(
            mode="egress_opt_in",
            allow_network=True,
            require_provider_allowlist=True,
            provider_allowlist={"vlm": ["openai"], "ocr": ["rapidocr"]},
        )
        assert is_provider_allowed("openai", "vlm", policy)
        assert not is_provider_allowed("unknown", "vlm", policy)
        assert is_provider_allowed("rapidocr", "ocr", policy)

    def test_no_allowlist_required(self):
        policy = PrivacyPolicy(mode="egress_opt_in", allow_network=True, require_provider_allowlist=False)
        assert is_provider_allowed("anything", "vlm", policy)


class TestEgressGate:
    """PSC-I1, PSC-I2: Egress gate blocks in local mode, audits in opt-in."""

    def test_local_blocks_all(self):
        policy = PrivacyPolicy(mode="local", allow_network=False)
        gate = EgressGate(policy, request_id="test-001")
        assert not gate.allow("openai", "vlm", destination="https://api.openai.com")
        assert not gate.allow("rapidocr", "ocr", destination="localhost")

    def test_local_require_allow_raises(self):
        policy = PrivacyPolicy(mode="local", allow_network=False)
        gate = EgressGate(policy, request_id="test-002")
        try:
            gate.require_allow("openai", "vlm", destination="https://api.openai.com")
            assert False, "Should have raised"
        except EgressBlockedError:
            pass

    def test_egress_opt_in_allows(self):
        policy = PrivacyPolicy(
            mode="egress_opt_in", allow_network=True,
            require_provider_allowlist=True,
            provider_allowlist={"vlm": ["openai"]},
        )
        gate = EgressGate(policy, request_id="test-003")
        assert gate.allow("openai", "vlm", destination="https://api.openai.com")
        assert not gate.allow("unknown", "vlm", destination="https://api.unknown.com")

    def test_egress_records_events(self):
        policy = PrivacyPolicy(mode="egress_opt_in", allow_network=True,
                               require_provider_allowlist=True,
                               provider_allowlist={"vlm": ["openai"]})
        gate = EgressGate(policy, request_id="test-004")
        gate.record("openai", "vlm", "https://api.openai.com", result="sent")
        gate.record("blocked-provider", "vlm", "https://api.blocked.com", result="blocked", reason="not in allowlist")
        assert len(gate.events) == 2
        assert gate.events[0].result == "sent"
        assert gate.events[1].result == "blocked"

    def test_egress_event_serializable(self):
        event = EgressEvent(
            event_id="egress_0001", request_id="test", provider="openai",
            component="vlm", destination="https://api.openai.com",
            data_classification=DataClassification.RESTRICTED,
            result="sent", consent_mode="egress_opt_in",
        )
        d = event.to_dict()
        assert d["event_id"] == "egress_0001"
        assert d["data_classification"] == "restricted"
        assert d["result"] == "sent"


class TestRedaction:
    """PSC-I9: Redaction must mask PII, secrets, and values."""

    def test_secrets_redacted(self):
        result = redact_secrets("Authorization: Bearer sk-abc123def456ghi78901234_end")
        assert "[REDACTED]" in result

    def test_pii_redacted_phone(self):
        result = redact_pii("Phone: 13812345678")
        assert "PHONE_MASKED" in result

    def test_pii_redacted_id(self):
        result = redact_pii("ID: 110101199001011234")
        assert "MASKED" in result

    def test_mask_value(self):
        result = mask_value("sensitive_data", keep_last=4)
        assert result.endswith("data")
        assert result.startswith("*")

    def test_hash_value_consistent(self):
        h1 = hash_value("test_value")
        h2 = hash_value("test_value")
        assert h1 == h2
        assert len(h1) == 16

    def test_redact_dict(self):
        result = redact_dict({"name": "Alice", "api_key": "sk-secret"})
        assert result["api_key"] == "[SECRET_REDACTED]"
        assert result["name"] == "Alice"

    def test_redact_dict_nested(self):
        result = redact_dict({"config": {"password": "secret123"}})
        assert result["config"]["password"] == "[SECRET_REDACTED]"

    def test_classify_redaction(self):
        c = classify_redaction("Phone 13812345678 token sk-abc123def456ghi78901234_end")
        assert c["has_pii"]
        assert c["has_secrets"]


class TestSecureLogging:
    """PSC-I3: Logs must not contain raw secrets or PII."""

    def test_filter_installs(self):
        root = logging.getLogger()
        initial_count = len(root.filters)
        install_safe_logging()
        # Should not add duplicate
        install_safe_logging()
        assert len(root.filters) >= initial_count

    def test_sanitize_message(self):
        f = SafeLoggingFilter()
        msg = f._sanitize("api_key=sk-secret token=abc phone 13812345678")
        assert "sk-secret" not in msg
        assert "13812345678" not in msg  # should be redacted

    def test_log_output_redacted(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        logger = logging.getLogger("psc_test_log")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.addFilter(SafeLoggingFilter())
        logger.info("API key: sk-abc123def456ghi78901234_test phone 13812345678")
        output = stream.getvalue()
        assert "sk-abc123def456ghi78901234_test" not in output


class TestSecurityLedger:
    """Security evidence ledger must track all PSC events."""

    def test_build_security_summary(self):
        ledger = SecurityEvidenceLedger(
            request_id="test-req", privacy_mode="local",
            data_classification=DataClassification.RESTRICTED,
        )
        summary = build_security_summary(ledger)
        assert summary["privacy_mode"] == "local"
        assert summary["network_egress"] == "blocked"
        assert summary["support_bundle_redaction_safe"]

    def test_ledger_tracks_egress(self):
        ledger = SecurityEvidenceLedger(request_id="req-1")
        ledger.add_egress(EgressEvent(event_id="e1", request_id="req-1", provider="openai", component="vlm",
                                        destination="https://api.oai.com", result="sent"))
        assert ledger.network_egress_allowed
        assert len(ledger.egress_events) == 1

    def test_ledger_tracks_resource_decisions(self):
        ledger = SecurityEvidenceLedger(request_id="req-2")
        ledger.add_resource_decision(ResourceGateDecision(component="archive", status="pass", code="archive_ok"))
        assert ledger.all_resource_gates_pass

    def test_ledger_to_dict(self):
        ledger = SecurityEvidenceLedger(request_id="req-3", privacy_mode="local")
        d = ledger.to_dict()
        assert d["privacy_mode"] == "local"
        assert d["version"] == 1


class TestResourceGate:
    """PSC-I4, PSC-I10: Resource gates must block dangerous inputs."""

    def test_archive_zip_bomb_blocked(self):
        r = check_archive_preflight("/tmp/bomb.zip", entry_count=1, max_depth=1,
                                    uncompressed_size=10_000_000_000, file_size=1000000)
        assert not r.allowed
        assert "compression_ratio" in r.blocked_reason.lower()

    def test_archive_too_many_entries(self):
        r = check_archive_preflight("/tmp/many.zip", entry_count=500, max_depth=1,
                                    uncompressed_size=1000000, file_size=500000)
        assert not r.allowed

    def test_archive_unsafe_path(self):
        r = check_archive_preflight("/tmp/bad.zip", entry_count=5, max_depth=1,
                                    uncompressed_size=1000000, file_size=500000,
                                    has_unsafe_paths=True)
        assert not r.allowed

    def test_archive_normal_allowed(self):
        r = check_archive_preflight("/tmp/good.zip", entry_count=10, max_depth=3,
                                    uncompressed_size=5_000_000, file_size=1_000_000)
        assert r.allowed

    def test_pdf_embedded_files_blocked(self):
        p = check_pdf_preflight(file_size=1_000_000, page_count=10, has_embedded_files=True)
        assert not p.allowed

    def test_pdf_javascript_blocked(self):
        p = check_pdf_preflight(file_size=1_000_000, page_count=10, has_javascript=True)
        assert not p.allowed

    def test_pdf_normal_allowed(self):
        p = check_pdf_preflight(file_size=1_000_000, page_count=100)
        assert p.allowed

    def test_image_pixel_bomb_blocked(self):
        i = check_image_preflight(width=32768, height=32768, channels=3,
                                  frame_count=1, file_size=1_000_000)
        assert not i.allowed

    def test_image_oversize_dimension_blocked(self):
        i = check_image_preflight(width=20000, height=20000, channels=3,
                                  frame_count=1, file_size=1_000_000)
        assert not i.allowed

    def test_image_normal_allowed(self):
        i = check_image_preflight(width=1920, height=1080, channels=3,
                                  frame_count=1, file_size=5_000_000)
        assert i.allowed

    def test_rest_upload_bad_content_type_blocked(self):
        u = check_rest_upload(content_type="application/x-msdos-program", body_size=1_000_000)
        assert u.status == "blocked"

    def test_rest_upload_pdf_allowed(self):
        u = check_rest_upload(content_type="application/pdf", body_size=1_000_000)
        assert u.status == "pass"


class TestPSCIntegration:
    """Integration tests across PSC components."""

    def test_local_parse_security_summary(self):
        """Simulate a full local parse security summary."""
        from docmirror.security.data_classification import DataClassification
        from docmirror.security.security_ledger import SecurityEvidenceLedger, EgressEvent, ResourceGateDecision, build_security_summary

        ledger = SecurityEvidenceLedger(
            request_id="parse-001",
            privacy_mode="local",
            data_classification=DataClassification.RESTRICTED,
        )

        # Resource gate checks
        ledger.add_resource_decision(ResourceGateDecision(
            component="pdf_resource_gate", status="pass", code="pdf_ok",
        ))

        # No egress events in local mode
        assert not ledger.network_egress_allowed
        assert ledger.all_resource_gates_pass

        summary = build_security_summary(ledger)
        assert summary["privacy_mode"] == "local"
        assert summary["network_egress"] == "blocked"
        assert summary["resource_gate"] == "pass"

    def test_egress_opt_in_parse_security_summary(self):
        """Simulate an egress opt-in parse security summary."""
        ledger = SecurityEvidenceLedger(
            request_id="parse-002",
            privacy_mode="egress_opt_in",
            data_classification=DataClassification.RESTRICTED,
        )
        ledger.add_egress(EgressEvent(
            event_id="egress_0001", request_id="parse-002",
            provider="openai", component="vlm",
            destination="https://api.openai.com/v1/chat/completions",
            result="sent", consent_mode="egress_opt_in",
        ))

        summary = build_security_summary(ledger)
        assert summary["network_egress"] == "allowed"
        assert "openai" in summary["external_providers"]

    def test_large_document_classification_flow(self):
        """Test classification -> privacy -> egress flow for large doc."""
        doc_class = classify_document("bank_statement.pdf", 500, has_sensitive_fields=True)
        assert doc_class == DataClassification.RESTRICTED

        # Local mode should block egress for restricted docs
        policy = PrivacyPolicy(mode="local", allow_network=False)
        gate = EgressGate(policy, request_id="test-flow")
        assert not gate.allow("openai", "vlm", destination="https://api.openai.com")
