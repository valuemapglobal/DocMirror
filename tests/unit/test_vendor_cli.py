# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for docmirror-vendor (VOT) package."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_VENDOR_DIR = Path(__file__).resolve().parents[2] / "vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from docmirror_vendor.cli import main  # noqa: E402
from docmirror_vendor.fingerprint import compute_machine_fingerprint  # noqa: E402
from docmirror_vendor.renew_notice import scan_license_directory  # noqa: E402
from docmirror_vendor.signing import LicenseGenerator, features_for_tier  # noqa: E402


def test_fingerprint_has_machine_id():
    fp = compute_machine_fingerprint()
    assert len(fp["machine_id"]) == 64
    assert fp["hostname"]


def test_finance_tier_features():
    features = features_for_tier("finance")
    assert "alipay_payment_premium" in features
    assert "*" not in features


def test_sign_generates_lic_file(tmp_path):
    gen = LicenseGenerator()
    data = gen.generate_license(
        customer={"company": "Test Co", "contact": "T", "email": "t@test.com", "phone": ""},
        tier="finance",
        duration_years=1,
    )
    out = gen.save_license(data, str(tmp_path))
    assert Path(out).is_file()
    loaded = json.loads(Path(out).read_text(encoding="utf-8"))
    assert loaded["license_info"]["tier"] == "finance"
    assert "alipay_payment_premium" in loaded["license_info"]["features"]


def test_renew_notice_finds_expiring(tmp_path):
    gen = LicenseGenerator()
    data = gen.generate_license(
        customer={"company": "Soon Co", "contact": "S", "email": "s@test.com", "phone": ""},
        tier="enterprise",
        duration_years=0,
    )
    expires = datetime.now() + timedelta(days=10)
    data["license_info"]["validity"]["expires_at"] = expires.isoformat()
    lic_path = tmp_path / "test.lic"
    lic_path.write_text(json.dumps(data), encoding="utf-8")

    notices = scan_license_directory(tmp_path, within_days=30)
    assert len(notices) == 1
    assert notices[0]["customer_company"] == "Soon Co"


def test_cli_fingerprint_json(capsys):
    code = main(["fingerprint", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "machine_id" in payload


def test_cli_sign_json(tmp_path, capsys):
    code = main(
        [
            "sign",
            "--customer",
            "CLI Co",
            "--tier",
            "professional",
            "--years",
            "1",
            "--output",
            str(tmp_path),
            "--json",
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["tier"] == "professional"
    assert Path(summary["file"]).is_file()
