# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for PEC plugin runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.plugins.runner import (
    _is_edition_plugin_licensed,
    _wrap_license_degraded,
    run_plugin_extract_sync,
)


def _mirror(document_type: str = "unknown") -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type=document_type)
    return pr


def test_runner_skips_unclassified():
    assert run_plugin_extract_sync(_mirror("unknown"), edition="community") is None


def test_runner_skips_generic_type():
    assert run_plugin_extract_sync(_mirror("generic"), edition="community") is None


def test_runner_id_card_uses_generic_fallback():
    mirror = _mirror("id_card")
    mirror.entities.domain_specific = {"name": "张三"}

    out = run_plugin_extract_sync(mirror, edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["classification"]["matched_document_type"] == "id_card"
    assert "community_generic_fallback" in out["status"]["warnings"]


def test_runner_audit_report_mirror_only():
    out = run_plugin_extract_sync(_mirror("audit_report"), edition="community")
    assert out is not None
    assert out["data"]["summary"]["total_rows"] == 0
    assert "mirror_only" in " ".join(out["status"]["warnings"])


def test_runner_skips_when_edition_package_missing():
    with patch("docmirror.plugins.runner._edition_package_available", return_value=False):
        assert (
            run_plugin_extract_sync(_mirror("bank_statement"), edition="enterprise") is None
        )


class _LicensedEnterprisePlugin:
    domain_name = "bank_statement"
    display_name = "Bank Statement Enterprise"
    edition = "enterprise"
    requires_license = True

    async def extract(self, document_context):
        return {
            "schema_version": "2.0",
            "edition": "enterprise",
            "data": {"records": [{"amount": 1}], "summary": {"total_rows": 1}},
            "status": {"success": True, "warnings": [], "errors": []},
        }


def test_is_edition_plugin_licensed_false_without_premium_feature():
    plugin = _LicensedEnterprisePlugin()
    with patch("docmirror.plugins.licensing.offline.offline_license_manager._licenses", []):
        with patch("docmirror.plugins.licensing.online.license_manager.is_licensed", return_value=False):
            assert _is_edition_plugin_licensed(plugin) is False


def test_is_edition_plugin_licensed_true_with_offline_feature():
    plugin = _LicensedEnterprisePlugin()
    license_file = MagicMock()
    license_file.is_valid = True
    license_file.get_features.return_value = ["bank_statement_premium"]
    with patch(
        "docmirror.plugins.licensing.offline.offline_license_manager._licenses",
        [license_file],
    ):
        assert _is_edition_plugin_licensed(plugin) is True


def test_wrap_license_degraded_adds_warning():
    payload = {"status": {"warnings": []}, "metadata": {}}
    wrapped = _wrap_license_degraded(
        payload,
        edition="enterprise",
        plugin=_LicensedEnterprisePlugin(),
    )
    assert wrapped["edition"] == "enterprise"
    assert wrapped["status"]["warnings"][0] == "_license_warning"
    assert wrapped["plugin"]["license_required"] is True


def test_enterprise_reuses_community_baseline_without_reextract():
    mirror = _mirror("business_license")
    community_payload = {
        "schema_version": "2.0",
        "edition": "community",
        "data": {"fields": {"company_name": "Acme"}, "records": []},
        "status": {"success": True, "warnings": [], "errors": []},
        "metadata": {"parser": "docmirror-community"},
    }

    with patch("docmirror.plugins.runner._edition_package_available", return_value=True):
        with patch("docmirror.plugins.registry.get", return_value=_LicensedEnterprisePlugin()):
            with patch("docmirror.plugins.runner._is_edition_plugin_licensed", return_value=False):
                with patch(
                    "docmirror.plugins.runner._run_community_extract",
                    return_value=community_payload,
                ):
                    out = run_plugin_extract_sync(mirror, edition="enterprise")

    assert out is not None
    assert out["edition"] == "enterprise"
    assert "_license_warning" in out["status"]["warnings"]
    assert out["plugin"]["license_required"] is True


def test_enterprise_runs_extract_when_licensed():
    mirror = _mirror("bank_statement")
    enterprise_payload = {
        "schema_version": "2.0",
        "data": {"records": [{"x": 1}], "summary": {"total_rows": 1}},
        "status": {"success": True, "warnings": [], "errors": []},
    }

    with patch("docmirror.plugins.runner._edition_package_available", return_value=True):
        with patch("docmirror.plugins.registry.get", return_value=_LicensedEnterprisePlugin()):
            with patch("docmirror.plugins.runner._is_edition_plugin_licensed", return_value=True):
                out = run_plugin_extract_sync(mirror, edition="enterprise")

    assert out is not None
    assert out["edition"] == "enterprise"
    assert out["data"]["summary"]["total_rows"] == 1
    assert "_license_warning" not in out.get("status", {}).get("warnings", [])


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("docmirror_finance"),
    reason="docmirror_finance not installed",
)
def test_finance_degrades_without_license():
    mirror = _mirror("alipay_payment")

    class _FinancePlugin:
        domain_name = "alipay_payment"
        display_name = "Alipay Finance"
        edition = "finance"
        requires_license = True

    community_payload = {
        "schema_version": "2.0",
        "edition": "community",
        "data": {"records": [{"amount": 1}], "summary": {"total_rows": 1}},
        "status": {"success": True, "warnings": [], "errors": []},
        "metadata": {},
    }

    with patch("docmirror.plugins.runner._edition_package_available", return_value=True):
        with patch("docmirror.plugins.registry.get", return_value=_FinancePlugin()):
            with patch("docmirror.plugins.runner._is_edition_plugin_licensed", return_value=False):
                with patch(
                    "docmirror.plugins.runner._run_community_extract",
                    return_value=community_payload,
                ):
                    out = run_plugin_extract_sync(mirror, edition="finance")

    assert out is not None
    assert "_license_warning" in out["status"]["warnings"]
