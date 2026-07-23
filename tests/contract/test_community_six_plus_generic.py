# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Community 6 premium + 1 generic contract tests."""

from __future__ import annotations

import importlib

import pytest

from docmirror.configs.domain.registry import (
    get_canonical_premium_domains,
    is_canonical_premium_domain,
)
from docmirror.plugins.generic.community_plugin import plugin as generic_plugin

PREMIUM_DOMAINS = (
    "bank_statement",
    "wechat_payment",
    "alipay_payment",
    "vat_invoice",
    "business_license",
    "credit_report",
)


@pytest.mark.parametrize("domain", PREMIUM_DOMAINS)
def test_premium_domain_has_community_plugin(domain: str):
    assert is_canonical_premium_domain(domain)
    capability = importlib.import_module(f"docmirror.plugins.{domain}.community_plugin").plugin
    assert capability.domain_name == domain
    assert callable(capability.recognize_facts)


def test_premium_domain_count_matches_ssot():
    assert get_canonical_premium_domains() == PREMIUM_DOMAINS


def test_demoted_domain_has_no_premium_capability():
    assert not is_canonical_premium_domain("id_card")


def test_generic_capability_singleton():
    assert generic_plugin.domain_name == "generic"


def test_archived_plugins_not_importable_from_package_root():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("docmirror.plugins.id_card_community")
