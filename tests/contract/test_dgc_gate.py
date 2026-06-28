# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""G14: DGC Gate contract tests.

GA 1.0 SS4.12 N2/N5: Verifies that DGC status gates Edition output correctly.
- ``vat_invoice`` (dgc_status: candidate) → L1 generic fallback fields only
- ``bank_statement`` (dgc_status: ga) → L2 fields normal output
- ``mirror_only`` domain → no Edition output, blocked
"""

from __future__ import annotations

import pytest


class TestResolveDgcStatus:
    """Test resolve_dgc_status() function from plugin_registry."""

    def test_ga_domain_returns_ga(self):
        from docmirror.plugins._runtime.plugin_registry import resolve_dgc_status
        result = resolve_dgc_status("bank_statement")
        assert result == "ga", f"bank_statement should be ga, got {result}"

    def test_candidate_domain_returns_candidate(self):
        from docmirror.plugins._runtime.plugin_registry import resolve_dgc_status
        result = resolve_dgc_status("vat_invoice")
        assert result == "candidate", f"vat_invoice should be candidate, got {result}"

    def test_mirror_only_domain_returns_mirror_only(self):
        from docmirror.plugins._runtime.plugin_registry import resolve_dgc_status
        result = resolve_dgc_status("unknown_domain_xyz")
        # unknown domains should return 'mirror_only' or 'unknown'
        assert result in ("mirror_only", "unknown"), (
            f"unknown domain should be mirror_only or unknown, got {result}"
        )

    def test_returns_string_for_all_cases(self):
        from docmirror.plugins._runtime.plugin_registry import resolve_dgc_status
        for domain in ("bank_statement", "vat_invoice", "business_license",
                       "personal_credit_report", "alipay_bill", "wechat_bill",
                       "nonexistent_domain", ""):
            result = resolve_dgc_status(domain)
            assert isinstance(result, str), f"result for {domain!r} should be str, got {type(result)}"
            assert result, f"result for {domain!r} should not be empty"


class TestEnforceDgcBoundary:
    """Test _enforce_dgc_boundary() function from kv_community_extract."""

    def test_ga_domain_no_restriction(self):
        from docmirror.plugins._base.kv_community_extract import _enforce_dgc_boundary
        gate = _enforce_dgc_boundary("bank_statement", "L2")
        assert gate["effective_support_level"] == "L2"
        assert gate["dgc_status"] == "ga"
        assert gate["block_edition"] is False
        assert "GA domain" in gate["dgc_annotation"]

    def test_ga_domain_keeps_L1_if_provided(self):
        from docmirror.plugins._base.kv_community_extract import _enforce_dgc_boundary
        gate = _enforce_dgc_boundary("bank_statement", "L1")
        assert gate["effective_support_level"] == "L1"
        assert gate["block_edition"] is False

    def test_candidate_domain_downgraded_to_L1(self):
        from docmirror.plugins._base.kv_community_extract import _enforce_dgc_boundary
        gate = _enforce_dgc_boundary("vat_invoice", "L2")
        assert gate["effective_support_level"] == "L1", (
            "G14: candidate domain must be downgraded to L1 (GA 1.0 N5)"
        )
        assert gate["dgc_status"] == "candidate"
        assert gate["block_edition"] is False
        assert "L1 generic fallback" in gate["dgc_annotation"]

    def test_mirror_only_domain_blocked(self):
        from docmirror.plugins._base.kv_community_extract import _enforce_dgc_boundary
        gate = _enforce_dgc_boundary("unknown_format", "L2")
        assert gate["block_edition"] is True, (
            "G14: mirror_only domain must block Edition output (GA 1.0 N2)"
        )
        assert gate["effective_support_level"] == "mirror_only"
        assert "edition output suppressed" in gate["dgc_annotation"].lower()

    def test_empty_domain_treated_as_mirror_only(self):
        from docmirror.plugins._base.kv_community_extract import _enforce_dgc_boundary
        gate = _enforce_dgc_boundary("", "L2")
        assert gate["block_edition"] is True


class TestDgcStatusInProjectionLineage:
    """Test that DGC status appears in projection lineage from edition payloads."""

    def test_lineage_includes_dgc_status_for_ga_domain(self):
        from docmirror.output.projection.resolver import build_projection_lineage

        payload = {
            "edition": "community",
            "plugin": {"name": "bank_statement"},
            "data": {"fields": {"total": "100.00"}},
            "metadata": {
                "source_page": 1,
                "domain": "bank_statement",
                "detected_type": "bank_statement",
                "support_level": "L2",
                "source_fact_ids": ["e1"],
                "evidence_ids": ["ev1"],
            },
            "quality": {"confidence": 0.94},
        }

        lineage = build_projection_lineage(payload)

        # Verify edition_lineage carries dgc_status
        assert lineage["edition_lineage"]["dgc_status"] == "ga", (
            "G14: edition_lineage.dgc_status must be 'ga' for bank_statement"
        )

        # Verify field_lineages also carry dgc_status
        for field in lineage["field_lineages"]:
            assert field["dgc_status"] == "ga"

    def test_lineage_includes_dgc_status_for_candidate_domain(self):
        from docmirror.output.projection.resolver import build_projection_lineage

        payload = {
            "edition": "community",
            "plugin": {"name": "vat_invoice"},
            "data": {"fields": {"invoice_no": "12345"}},
            "metadata": {
                "source_page": 1,
                "domain": "vat_invoice",
                "detected_type": "vat_invoice",
                "support_level": "L1",
                "source_fact_ids": ["e2"],
                "evidence_ids": ["ev2"],
            },
            "quality": {"confidence": 0.85},
        }

        lineage = build_projection_lineage(payload)

        assert lineage["edition_lineage"]["dgc_status"] == "candidate", (
            "G14: edition_lineage.dgc_status must be 'candidate' for vat_invoice"
        )
        assert lineage["edition_lineage"]["support_level"] == "L1"

    def test_lineage_dgc_status_from_metadata(self):
        """When dgc_status is explicitly set in metadata, it should be used."""
        from docmirror.output.projection.resolver import build_projection_lineage

        payload = {
            "edition": "enterprise",
            "plugin": {"name": "custom_plugin"},
            "data": {"fields": {"field1": "val1"}},
            "metadata": {
                "source_page": 1,
                "dgc_status": "ga",
                "support_level": "L2",
                "source_fact_ids": ["e3"],
                "evidence_ids": [],
            },
            "quality": {"confidence": 0.9},
        }

        lineage = build_projection_lineage(payload)

        assert lineage["edition_lineage"]["dgc_status"] == "ga"
        for field in lineage["field_lineages"]:
            assert field["dgc_status"] == "ga"

    def test_lineage_dgc_status_unresolved_fallback(self):
        """When domain is unrecognized, dgc_status falls back to 'unresolved'."""
        from docmirror.output.projection.resolver import build_projection_lineage

        payload = {
            "edition": "community",
            "plugin": {"name": "generic"},
            "data": {"fields": {"some_key": "some_value"}},
            "metadata": {
                "source_page": 1,
                "domain": "absolutely_unknown_document_type_xyz",
                "support_level": "L1",
                "source_fact_ids": [],
                "evidence_ids": [],
            },
            "quality": {"confidence": 0.5},
        }

        lineage = build_projection_lineage(payload)

        # Should resolve to a valid string (either 'mirror_only' from plugin_registry or 'unresolved')
        dgc = lineage["edition_lineage"]["dgc_status"]
        assert dgc in ("mirror_only", "unresolved", "unknown"), (
            f"Expected mirror_only/unresolved/unknown, got {dgc!r}"
        )


class TestDgcGateAcceptance:
    """G14 acceptance: DGC gate ensures correct field set per domain status."""

    def test_candidate_domain_blocks_L2_fields(self):
        """G14: vat_invoice (candidate) must NOT output L2 financial fields."""
        from docmirror.plugins._base.kv_community_extract import _enforce_dgc_boundary

        # vat_invoice is a candidate domain
        gate = _enforce_dgc_boundary("vat_invoice", "L2")
        assert gate["effective_support_level"] == "L1", (
            "G14 ACCEPTANCE: candidate domain must be downgraded to L1"
        )
        assert gate["dgc_status"] == "candidate"

    def test_ga_domain_allows_L2_fields(self):
        """G14: bank_statement (ga) must output L2 fields normally."""
        from docmirror.plugins._base.kv_community_extract import _enforce_dgc_boundary

        gate = _enforce_dgc_boundary("bank_statement", "L2")
        assert gate["effective_support_level"] == "L2", (
            "G14 ACCEPTANCE: ga domain must keep L2 support_level"
        )
        assert gate["dgc_status"] == "ga"
        assert gate["block_edition"] is False

    def test_mirror_only_domain_no_edition_output(self):
        """G14: mirror_only domain must block Edition output entirely."""
        from docmirror.plugins._base.kv_community_extract import _enforce_dgc_boundary

        gate = _enforce_dgc_boundary("unsupported_domain", "L2")
        assert gate["block_edition"] is True, (
            "G14 ACCEPTANCE: mirror_only domain must block all Edition output"
        )
