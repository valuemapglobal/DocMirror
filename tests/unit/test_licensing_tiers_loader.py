# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for licensing/tiers.yaml loader."""

from __future__ import annotations

import pytest

from docmirror.configs.paths import LICENSE_FILE_SCHEMA, TIERS_YAML
from docmirror.plugins._runtime.licensing.contract import premium_feature
from docmirror.plugins._runtime.licensing.tiers_loader import (
    community_free_domains,
    feature_suffix,
    load_tiers,
    tier_features,
)


def test_tiers_yaml_exists():
    assert TIERS_YAML.is_file()


def test_license_schema_exists():
    assert LICENSE_FILE_SCHEMA.is_file()


def test_community_free_domains_six_plus_one():
    domains = community_free_domains()
    assert len(domains) == 6
    assert "bank_statement" in domains
    assert "alipay_payment" in domains


def test_premium_feature_suffix():
    assert feature_suffix() == "_premium"
    assert premium_feature("alipay_payment") == "alipay_payment_premium"


def test_enterprise_tier_includes_alipay_premium():
    features = tier_features("enterprise")
    assert "alipay_payment_premium" in features


def test_finance_tier_includes_public_entitlements():
    finance = set(tier_features("finance"))
    assert "alipay_payment_premium" in finance
    assert "batch_processing" in finance
    assert len(finance) >= 11


def test_finance_tier_covers_installed_finance_registry():
    pytest.importorskip("docmirror_finance", reason="finance package is not available in OSS CI")

    finance = set(tier_features("finance"))
    assert len(finance) >= 120


def test_load_tiers_cached():
    assert load_tiers()["schema_version"] == "1.0"
