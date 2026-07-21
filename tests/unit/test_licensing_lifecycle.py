# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LEP lifecycle tests (doc 13 §9 / doc 11 LEP-5)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from docmirror.plugins._runtime.licensing.lifecycle import (
    LicenseLifecycleState,
    entitlement_warnings,
    inject_edition_lifecycle_warnings,
    resolve_entitlement_lifecycle,
    resolve_entitlement_state,
)


def _mock_license_file(*, days_until_expiry: int, in_grace: bool = False):
    lic = MagicMock()
    now = datetime.now()
    lic.expires_at = now + timedelta(days=days_until_expiry)
    lic.grace_period_days = 30
    lic.effective_expiry = lic.expires_at + timedelta(days=30)
    if in_grace:
        lic.expires_at = now - timedelta(days=1)
        lic.effective_expiry = now + timedelta(days=29)
    lic.days_until_expiry = days_until_expiry if not in_grace else -1
    lic.days_until_effective_expiry = 29 if in_grace else days_until_expiry + 30
    lic.is_valid = True
    lic.get_features.return_value = ["alipay_payment_premium"]
    lic.get_tier.return_value = "enterprise"
    return lic


def test_expiring_soon_state_and_warning():
    lic = _mock_license_file(days_until_expiry=30)
    with patch("docmirror.plugins._runtime.licensing.offline.offline_license_manager._licenses", [lic]):
        lc = resolve_entitlement_lifecycle()
        assert lc.state == LicenseLifecycleState.EXPIRING_SOON
        assert entitlement_warnings(lc) == ["_license_expiring_soon:30d"]


def test_grace_period_still_active_state():
    lic = _mock_license_file(days_until_expiry=0, in_grace=True)
    with patch("docmirror.plugins._runtime.licensing.offline.offline_license_manager._licenses", [lic]):
        lc = resolve_entitlement_lifecycle()
        assert lc.state == LicenseLifecycleState.GRACE_PERIOD
        assert "_license_grace_period:" in entitlement_warnings(lc)[0]


def test_missing_state_without_licenses():
    with patch("docmirror.plugins._runtime.licensing.offline.offline_license_manager._licenses", []):
        with patch("docmirror.plugins._runtime.licensing.online.license_manager._cached_license", None):
            assert resolve_entitlement_state() == LicenseLifecycleState.MISSING


def test_inject_edition_lifecycle_warnings():
    lic = _mock_license_file(days_until_expiry=15)
    payload = {"status": {"warnings": []}}
    with patch("docmirror.plugins._runtime.licensing.offline.offline_license_manager._licenses", [lic]):
        out = inject_edition_lifecycle_warnings(payload)
    assert any(w.startswith("_license_expiring_soon:") for w in out["status"]["warnings"])


def test_build_api_response_does_not_recheck_or_publish_license_state():
    from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
    from docmirror.server.output_builder import build_api_response

    lic = _mock_license_file(days_until_expiry=15)
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="alipay_payment")

    with patch("docmirror.plugins._runtime.licensing.offline.offline_license_manager._licenses", [lic]):
        api = build_api_response(result)

    assert "meta" not in api
    assert "license" not in api["source"]["provenance"]
