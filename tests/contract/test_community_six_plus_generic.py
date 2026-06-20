# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Community 6 premium + 1 generic contract tests."""

from __future__ import annotations

import importlib

import pytest

from docmirror.plugins.community import (
    community_plugin_module,
    find_premium_community_plugin,
    get_community_premium_domains,
    get_generic_community_plugin,
    is_community_premium,
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
    assert is_community_premium(domain)
    plugin, modname = find_premium_community_plugin(domain)
    assert plugin is not None, f"missing premium plugin for {domain}"
    assert modname == community_plugin_module(domain)
    assert plugin.domain_name == domain
    assert plugin.edition == "community"


def test_premium_domain_count_matches_ssot():
    assert get_community_premium_domains() == PREMIUM_DOMAINS


def test_demoted_domain_has_no_premium_plugin():
    plugin, _ = find_premium_community_plugin("id_card")
    assert plugin is None


def test_generic_plugin_singleton():
    plugin, modname = get_generic_community_plugin()
    assert plugin is generic_plugin
    assert modname == community_plugin_module("generic")
    assert plugin.domain_name == "generic"


def test_archived_plugins_not_importable_from_package_root():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("docmirror.plugins.id_card_community")
