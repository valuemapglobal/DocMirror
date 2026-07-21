# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI license show snapshot tests."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from docmirror.cli.plugins import license


def test_license_show_offline_snapshot():
    runner = CliRunner()
    snapshot = {
        "active_channel": "offline",
        "offline": {
            "tier": "enterprise",
            "is_valid": True,
            "expires_at": "2027-01-01T00:00:00",
            "grace_period_days": 30,
            "effective_expiry": "2027-01-31T00:00:00",
        },
        "online": None,
        "offline_licenses": [{"license_id": "DEMO-1"}],
        "entitled_features_sample": ["alipay_payment_premium", "batch_processing"],
        "lifecycle": {},
    }
    with patch("docmirror.plugins._runtime.licensing.snapshot.resolve_license_snapshot", return_value=snapshot):
        result = runner.invoke(license, ["show"])
    assert result.exit_code == 0
    assert "offline" in result.output.lower() or "Offline" in result.output
    assert "alipay_payment_premium" in result.output


def test_license_show_no_license():
    runner = CliRunner()
    with patch(
        "docmirror.plugins._runtime.licensing.snapshot.resolve_license_snapshot",
        return_value={"offline": None, "online": None, "offline_licenses": []},
    ):
        result = runner.invoke(license, ["show"])
    assert result.exit_code == 0
    assert "No active license" in result.output
