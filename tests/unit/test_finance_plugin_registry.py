# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Finance plugin registry — domains aligned with enterprise."""

from __future__ import annotations

import pytest

pytest.importorskip("docmirror_finance")

from docmirror_finance.plugins._baseline import FinanceBaselinePlugin

from docmirror.plugins._runtime import registry


def test_finance_registers_finance_subset_plugins():
    import docmirror_enterprise.enable as enterprise_enable
    import docmirror_finance.enable as finance_enable

    enterprise_enable.register_enterprise_plugins(registry)
    count = finance_enable.register_finance_plugins(registry)

    assert count >= 119

    finance_plugins = []
    for name in registry.list_plugins():
        plugin = registry.get(name, "finance")
        if plugin is not None and getattr(plugin, "edition", "") == "finance":
            finance_plugins.append(plugin)

    assert len(finance_plugins) == count
    assert all(getattr(p, "requires_license", False) for p in finance_plugins)
    assert all(p.edition == "finance" for p in finance_plugins)


def test_finance_domains_are_enterprise_subset():
    import docmirror_enterprise.enable as enterprise_enable
    import docmirror_finance.enable as finance_enable

    enterprise_enable.register_enterprise_plugins(registry)
    finance_enable.register_finance_plugins(registry)

    enterprise_domains = {
        registry.get(n, "enterprise").domain_name
        for n in registry.list_plugins()
        if registry.get(n, "enterprise") is not None
    }
    finance_domains = {
        registry.get(n, "finance").domain_name
        for n in registry.list_plugins()
        if registry.get(n, "finance") is not None
    }
    assert finance_domains <= enterprise_domains
    assert len(finance_domains) >= 119


def test_alipay_is_full_plugin_not_baseline():
    import docmirror_finance.enable as finance_enable

    finance_enable.register_finance_plugins(registry)
    alipay = registry.get("alipay_payment", "finance")
    assert alipay is not None
    assert not isinstance(alipay, FinanceBaselinePlugin)
    assert hasattr(alipay, "extract")
