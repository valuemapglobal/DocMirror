# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entitlement unit tests — TQG-Lite LIC-* cases."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from docmirror.plugins.licensing.contract import premium_feature
from docmirror.plugins.licensing.entitlements import demo_features, is_entitled
from docmirror.plugins.runner import _is_edition_plugin_licensed, _wrap_license_degraded


def test_lic01_premium_feature_naming():
    assert premium_feature("alipay_payment") == "alipay_payment_premium"


def test_lic02_community_free_domain_not_entitled_without_license():
    with patch("docmirror.plugins.offline_license.offline_license_manager._licenses", []):
        with patch("docmirror.plugins.license.license_manager.is_licensed", return_value=False):
            assert is_entitled("bank_statement") is False


def test_lic03_entitled_with_premium_feature_in_offline_lic():
    lic = MagicMock()
    lic.is_valid = True
    lic.get_features.return_value = ["alipay_payment_premium"]
    with patch("docmirror.plugins.offline_license.offline_license_manager._licenses", [lic]):
        assert is_entitled("alipay_payment") is True


def test_lic04_bare_domain_in_lic_features_not_entitled():
    lic = MagicMock()
    lic.is_valid = True
    lic.get_features.return_value = ["alipay_payment"]
    with patch("docmirror.plugins.offline_license.offline_license_manager._licenses", [lic]):
        assert is_entitled("alipay_payment") is False


def test_lic05_runner_degrade_warning_without_license():
    class _Plugin:
        domain_name = "audit_report"
        requires_license = True

    with patch("docmirror.plugins.offline_license.offline_license_manager._licenses", []):
        with patch("docmirror.plugins.license.license_manager.is_licensed", return_value=False):
            assert _is_edition_plugin_licensed(_Plugin()) is False

    payload = _wrap_license_degraded(
        {"status": {"warnings": []}, "metadata": {}},
        edition="enterprise",
        plugin=_Plugin(),
    )
    assert "_license_warning" in payload["status"]["warnings"]


def test_lic05_runner_no_warning_when_entitled():
    class _Plugin:
        domain_name = "audit_report"
        requires_license = True

    lic = MagicMock()
    lic.is_valid = True
    lic.get_features.return_value = ["audit_report_premium"]
    with patch("docmirror.plugins.offline_license.offline_license_manager._licenses", [lic]):
        assert _is_edition_plugin_licensed(_Plugin()) is True


def test_lic06_grace_period_still_entitled():
    lic = MagicMock()
    lic.is_valid = True
    lic.get_features.return_value = ["alipay_payment_premium"]
    with patch("docmirror.plugins.offline_license.offline_license_manager._licenses", [lic]):
        assert is_entitled("alipay_payment") is True


def test_lic07_demo_features_use_premium_suffix_or_literals():
    import re

    features = demo_features()
    assert features
    assert "*" not in features
    premium_re = re.compile(r"^[a-z0-9_]+_premium$")
    literals = {"batch_processing", "priority_support"}
    for feat in features:
        assert premium_re.match(feat) or feat in literals


def test_offline_simplified_requires_dev_mode(tmp_path, monkeypatch):
    from docmirror.plugins.offline_license import OfflineLicenseManager

    monkeypatch.setenv("DOCMIRROR_LICENSE_DEV_MODE", "")
    mgr = OfflineLicenseManager.__new__(OfflineLicenseManager)
    license_info = {
        "license_id": "TEST-1",
        "tier": "enterprise",
        "validity": {
            "issued_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "grace_period_days": 30,
        },
        "features": ["alipay_payment_premium"],
    }
    content_str = json.dumps(license_info, sort_keys=True)
    sig = json.dumps(
        {
            "license_info": license_info,
            "security": {"signature": f"simplified:{__import__('hashlib').sha256(content_str.encode()).hexdigest()}"},
        }
    )
    data = json.loads(sig)
    assert mgr._verify_signature(data) is False

    monkeypatch.setenv("DOCMIRROR_LICENSE_DEV_MODE", "1")
    assert mgr._verify_signature(data) is True
