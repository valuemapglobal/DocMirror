# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Plugin system tests — verify DomainPlugin contracts, edition-aware registry,
and built-in community/enterprise plugin discovery.
"""

import importlib.util

import pytest

pytestmark = [pytest.mark.tier_smoke]

from docmirror.plugins import PluginRegistry
from docmirror.plugins._runtime.community import get_community_premium_domains
from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror.plugins.generic.community_plugin import GenericCommunityPlugin

_HAS_ENTERPRISE = importlib.util.find_spec("docmirror_enterprise") is not None
if _HAS_ENTERPRISE:
    from docmirror_enterprise.plugins.bank_statement import BankStatementPlugin
    from docmirror_enterprise.plugins.bank_statement import plugin as bank_statement_plugin
    from docmirror_enterprise.plugins.bank_statement.plugin import plugin as bank_statement_module_plugin
else:
    BankStatementPlugin = None
    bank_statement_plugin = None
    bank_statement_module_plugin = None

requires_enterprise = pytest.mark.skipif(
    not _HAS_ENTERPRISE,
    reason="enterprise package is not available in OSS CI",
)


@requires_enterprise
class TestBankStatementEnterprisePlugin:
    """Enterprise bank_statement plugin (docmirror_enterprise)."""

    def test_instantiable(self):
        plugin = BankStatementPlugin()
        assert plugin.domain_name == "bank_statement"
        assert plugin.display_name == "Bank Statement (Enterprise)"

    def test_edition_metadata(self):
        plugin = BankStatementPlugin()
        assert plugin.edition == "enterprise"
        assert plugin.requires_license is True

    def test_scene_keywords_from_config(self):
        """Scene keywords are loaded from scene_keywords.yaml via DomainPlugin base."""
        plugin = BankStatementPlugin()
        assert len(plugin.scene_keywords) > 0
        assert "银行流水" in plugin.scene_keywords

    def test_identity_fields(self):
        plugin = BankStatementPlugin()
        field_names = {name for name, _ in plugin.identity_fields}
        assert "account_holder" in field_names

    def test_build_domain_data(self):
        plugin = BankStatementPlugin()
        result = plugin.build_domain_data(
            {"Account holder": "Alice"},
            {"account_holder": "Alice", "currency": "CNY"},
        )
        assert result is not None
        assert result["document_type"] == "bank_statement"

    def test_module_exports_plugin_singleton(self):
        assert isinstance(bank_statement_plugin, BankStatementPlugin)
        assert bank_statement_plugin is bank_statement_module_plugin


class TestBankStatementCommunityPlugin:
    """Community bank_statement plugin (docmirror.plugins)."""

    def test_instantiable(self):
        plugin = BankStatementCommunityPlugin()
        assert plugin.domain_name == "bank_statement"
        assert plugin.display_name == "Bank Statement (Community)"

    def test_edition_metadata(self):
        plugin = BankStatementCommunityPlugin()
        assert plugin.edition == "community"
        assert plugin.requires_license is False

    def test_identity_fields(self):
        plugin = BankStatementCommunityPlugin()
        field_names = {name for name, _ in plugin.identity_fields}
        assert "account_holder" in field_names
        assert "account_number" in field_names

    def test_build_domain_data(self):
        plugin = BankStatementCommunityPlugin()
        result = plugin.build_domain_data(
            {"Account holder": "Alice"},
            {"account_holder": "Alice", "account_number": "6222", "currency": "CNY"},
        )
        assert result is not None
        assert result["document_type"] == "bank_statement"
        assert result["entities"]["account_holder"] == "Alice"
        assert result["entities"]["account_number"] == "6222"


class TestCommunitySixPlusGeneric:
    """Community edition ships 6 premium plugins + 1 generic fallback."""

    def test_premium_domain_count(self):
        assert len(get_community_premium_domains()) == 6

    def test_generic_plugin_instantiable(self):
        plugin = GenericCommunityPlugin()
        assert plugin.domain_name == "generic"
        assert plugin.requires_license is False

    def test_registry_discovers_generic_not_archived(self):
        reg = PluginRegistry()
        reg._ensure_discovered()
        assert reg.get("generic", "community") is not None
        assert reg.get("id_card", "community") is None


class TestPluginRegistry:
    """Edition-aware PluginRegistry behavior."""

    @staticmethod
    def _isolated_registry() -> PluginRegistry:
        reg = PluginRegistry()
        reg._discovered = True
        return reg

    @requires_enterprise
    def test_register_and_get_by_edition(self):
        reg = self._isolated_registry()
        enterprise = BankStatementPlugin()
        reg.register(enterprise, override=True)
        assert reg.get("bank_statement", "enterprise") is enterprise
        assert reg.get("bank_statement", "community") is None

    @requires_enterprise
    def test_get_defaults_to_community_edition(self):
        reg = self._isolated_registry()
        community = BankStatementCommunityPlugin()
        enterprise = BankStatementPlugin()
        reg.register(community)
        reg.register(enterprise, override=True)
        assert reg.get("bank_statement") is community

    @requires_enterprise
    def test_get_first_prefers_highest_edition(self):
        reg = self._isolated_registry()
        community = BankStatementCommunityPlugin()
        enterprise = BankStatementPlugin()
        reg.register(community)
        reg.register(enterprise, override=True)
        assert reg.get_first("bank_statement") is enterprise

    def test_get_nonexistent_returns_none(self):
        reg = PluginRegistry()
        assert reg.get("nonexistent_domain") is None
        assert reg.get_first("nonexistent_domain") is None

    @requires_enterprise
    def test_list_plugins_keeps_first_sorted_edition(self):
        reg = self._isolated_registry()
        reg.register(BankStatementCommunityPlugin())
        reg.register(BankStatementPlugin(), override=True)
        plugins = reg.list_plugins()
        assert plugins["bank_statement"] == "Bank Statement (Community)"

    @requires_enterprise
    def test_list_domains_tracks_all_editions(self):
        reg = self._isolated_registry()
        reg.register(BankStatementCommunityPlugin())
        reg.register(BankStatementPlugin(), override=True)
        assert set(reg.list_domains()["bank_statement"]) == {"community", "enterprise"}

    def test_auto_discovery_registers_bank_statement_editions(self):
        reg = PluginRegistry()
        reg._ensure_discovered()
        assert reg.get("bank_statement", "community") is not None
        assert (reg.get("bank_statement", "enterprise") is not None) is _HAS_ENTERPRISE
        assert reg.get_first("bank_statement") is not None

    def test_auto_discovery_lists_bank_statement(self):
        reg = PluginRegistry()
        plugins = reg.list_plugins()
        assert "bank_statement" in plugins

    def test_plugin_scene_keywords_via_registry(self):
        reg = PluginRegistry()
        keywords = reg.get_all_scene_keywords()
        assert "bank_statement" in keywords
        assert "银行流水" in keywords["bank_statement"]

    def test_build_domain_data_unknown_returns_none(self):
        reg = PluginRegistry()
        assert reg.build_domain_data("unknown_domain", {}, {}) is None

    @requires_enterprise
    def test_build_domain_data_uses_get_first_plugin(self):
        reg = self._isolated_registry()
        community = BankStatementCommunityPlugin()
        enterprise = BankStatementPlugin()
        reg.register(community)
        reg.register(enterprise)
        # get_first resolves enterprise, which inherits raw KV from community base
        result = reg.build_domain_data("bank_statement", {}, {})
        assert result is not None
        assert result["document_type"] == "bank_statement"

    def test_build_domain_data_community_only_registry(self):
        reg = self._isolated_registry()
        reg.register(BankStatementCommunityPlugin())
        result = reg.build_domain_data(
            "bank_statement",
            {"Account holder": "Bob"},
            {"account_holder": "Bob", "account_number": "1234", "currency": "CNY"},
        )
        assert result is not None
        assert result["entities"]["account_holder"] == "Bob"

    @requires_enterprise
    def test_duplicate_register_same_edition_warns(self):
        reg = self._isolated_registry()
        p1 = BankStatementPlugin()
        p2 = BankStatementPlugin()
        reg.register(p1)
        reg.register(p2)
        assert reg.get("bank_statement", "enterprise") is p1

    @requires_enterprise
    def test_duplicate_register_with_override_replaces(self):
        reg = self._isolated_registry()
        p1 = BankStatementPlugin()
        p2 = BankStatementPlugin()
        reg.register(p1)
        reg.register(p2, override=True)
        assert reg.get("bank_statement", "enterprise") is p2

    @requires_enterprise
    def test_list_by_edition_enterprise(self):
        reg = PluginRegistry()
        enterprise_plugins = reg.list_by_edition("enterprise")
        domain_names = {p.domain_name for p in enterprise_plugins}
        assert "bank_statement" in domain_names
        assert len(enterprise_plugins) >= 100
