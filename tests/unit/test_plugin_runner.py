# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for PEC plugin runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.plugins._runtime.runner import (
    _is_edition_plugin_licensed,
    run_plugin_extract_sync,
)


def _mirror(document_type: str = "unknown") -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type=document_type)
    return pr


def test_runner_unclassified_uses_universal_fallback():
    out = run_plugin_extract_sync(_mirror("unknown"), edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["classification"]["matched"] is False
    assert out["business"]["version"] == "community.business.v1"


def test_runner_generic_type_uses_universal_fallback():
    out = run_plugin_extract_sync(_mirror("generic"), edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert "community_generic_fallback" in out["status"]["warnings"]


def test_runner_id_card_uses_generic_fallback():
    mirror = _mirror("id_card")
    mirror.entities.domain_specific = {"name": "张三"}

    out = run_plugin_extract_sync(mirror, edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["classification"]["matched_document_type"] == "id_card"
    assert "community_generic_fallback" in out["status"]["warnings"]


def test_runner_audit_report_uses_generic_fallback():
    out = run_plugin_extract_sync(_mirror("audit_report"), edition="community")
    assert out is not None
    assert out["data"]["summary"]["total_rows"] == 0
    assert "community_generic_fallback" in out["status"]["warnings"]


def test_runner_skips_when_edition_package_missing():
    with patch("docmirror.plugins._runtime.runner._edition_package_available", return_value=False):
        assert run_plugin_extract_sync(_mirror("bank_statement"), edition="enterprise") is None


class _LicensedEnterprisePlugin:
    domain_name = "bank_statement"
    display_name = "Bank Statement Enterprise"
    edition = "enterprise"
    requires_license = True

    async def extract(self, result):  # noqa: ARG002
        return {
            "schema_version": "2.0",
            "edition": "enterprise",
            "data": {"records": [{"amount": 1}], "summary": {"total_rows": 1}},
            "status": {"success": True, "warnings": [], "errors": []},
        }


class _ContextCapturingEnterprisePlugin(_LicensedEnterprisePlugin):
    def __init__(self) -> None:
        self.result = None

    async def extract(self, result):
        self.result = result
        return await super().extract(result)


def test_is_edition_plugin_licensed_false_without_premium_feature():
    plugin = _LicensedEnterprisePlugin()
    with patch("docmirror.plugins._runtime.licensing.offline.offline_license_manager._licenses", []):
        with patch("docmirror.plugins._runtime.licensing.online.license_manager.is_licensed", return_value=False):
            assert _is_edition_plugin_licensed(plugin) is False


def test_is_edition_plugin_licensed_true_with_offline_feature():
    plugin = _LicensedEnterprisePlugin()
    license_file = MagicMock()
    license_file.is_valid = True
    license_file.get_features.return_value = ["bank_statement_premium"]
    with patch(
        "docmirror.plugins._runtime.licensing.offline.offline_license_manager._licenses",
        [license_file],
    ):
        assert _is_edition_plugin_licensed(plugin) is True


def test_unlicensed_enterprise_produces_no_projection():
    mirror = _mirror("business_license")
    community_payload = {
        "schema_version": "2.0",
        "edition": "community",
        "data": {"fields": {"company_name": "Acme"}, "records": []},
        "status": {"success": True, "warnings": [], "errors": []},
        "metadata": {"parser": "docmirror-community"},
    }

    with patch("docmirror.plugins._runtime.runner._edition_package_available", return_value=True):
        with patch("docmirror.plugins.registry.get", return_value=_LicensedEnterprisePlugin()):
            with patch("docmirror.plugins._runtime.runner._is_edition_plugin_licensed", return_value=False):
                with patch(
                    "docmirror.plugins._runtime.runner._run_community_recognition",
                    return_value=community_payload,
                ):
                    out = run_plugin_extract_sync(mirror, edition="enterprise")

    assert out is None


def test_enterprise_runs_extract_when_licensed():
    mirror = _mirror("bank_statement")

    with patch("docmirror.plugins._runtime.runner._edition_package_available", return_value=True):
        with patch("docmirror.plugins.registry.get", return_value=_LicensedEnterprisePlugin()):
            with patch("docmirror.plugins._runtime.runner._is_edition_plugin_licensed", return_value=True):
                out = run_plugin_extract_sync(mirror, edition="enterprise")

    assert out is not None
    assert out["edition"] == "enterprise"
    assert out["data"]["summary"]["total_rows"] == 1
    assert "_license_warning" not in out.get("status", {}).get("warnings", [])


def test_enterprise_receives_parse_result_directly():
    mirror = _mirror("bank_statement")
    plugin = _ContextCapturingEnterprisePlugin()
    mirror.entities.domain_specific["records"] = [{"amount": "-10.25"}]

    with patch("docmirror.plugins._runtime.runner._edition_package_available", return_value=True):
        with patch("docmirror.plugins.registry.get", return_value=plugin):
            with patch("docmirror.plugins._runtime.runner._is_edition_plugin_licensed", return_value=True):
                out = run_plugin_extract_sync(mirror, edition="enterprise")

    assert out is not None
    assert plugin.result is mirror
    assert plugin.result.entities.domain_specific["records"][0]["amount"] == "-10.25"


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("docmirror_finance"),
    reason="docmirror_finance not installed",
)
def test_finance_produces_no_projection_without_license():
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

    with patch("docmirror.plugins._runtime.runner._edition_package_available", return_value=True):
        with patch("docmirror.plugins.registry.get", return_value=_FinancePlugin()):
            with patch("docmirror.plugins._runtime.runner._is_edition_plugin_licensed", return_value=False):
                with patch(
                    "docmirror.plugins._runtime.runner._run_community_recognition",
                    return_value=community_payload,
                ):
                    out = run_plugin_extract_sync(mirror, edition="finance")

    assert out is None
