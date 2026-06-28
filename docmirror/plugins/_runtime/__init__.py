# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Runtime support package — infrastructure internals for the plugin system.

Moved here from ``docmirror/plugins/`` top-level to keep the domain-plugin
namespace clean.  All public symbols are re-exported so that external code can
import from ``docmirror.plugins._runtime`` instead of the old top-level paths.

Pipeline role: infrastructure modules only — registry, runner, licensing,
post-extract hooks, community-config, discovery, plugin state, and manager.
Domain plugins (bank_statement, credit_report, …) stay at the top-level
``docmirror.plugins.*`` and are **not** re-exported here.

Key re-exports (see each sub-module for docstrings):

* plugin_registry  — ``DomainPlugin``, ``PluginRegistry``, ``registry``
* runner           — ``run_plugin_extract``, ``run_plugin_extract_sync``
* state            — ``is_domain_enabled``, ``set_domain_enabled``
* manager          — ``PluginManager``, ``plugin_manager``
* composition      — ``CompositionReason``, ``annotate_composition``, …
* licensing        — ``is_entitled``, ``license_manager``, ``offline_license_manager``, …
* post_extract     — ``PostExtractHook``, ``run_post_extract_hooks``
* community        — ``get_community_premium_domains``, ``find_premium_community_plugin``, …
* discovery        — entry-point plugin discovery
* hooks            — pluggy hook specifications
* core_extensions  — extension-point registration
"""

from __future__ import annotations

# ── Registry ────────────────────────────────────────────────────────────
from docmirror.plugins._runtime.plugin_registry import (
    DomainPlugin,
    PluginRegistry,
    registry,
    resolve_dgc_status,
)

# ── Composition ─────────────────────────────────────────────────────────
from docmirror.plugins._runtime.composition import (
    CompositionReason,
    annotate_composition,
    apply_extract_fallback,
    apply_license_degrade,
)

# ── Runner ──────────────────────────────────────────────────────────────
from docmirror.plugins._runtime.runner import run_plugin_extract, run_plugin_extract_sync

# ── State / Manager ─────────────────────────────────────────────────────
from docmirror.plugins._runtime.state import is_domain_enabled, set_domain_enabled
from docmirror.plugins._runtime.manager import PluginManager, plugin_manager

# ── Licensing (re-export package-level symbols) ─────────────────────────
from docmirror.plugins._runtime.licensing import (  # noqa: F401
    EntitlementLifecycle,
    FEATURE_SUFFIX,
    LicenseLifecycleState,
    LicenseManager,
    OfflineLicenseManager,
    community_free_domains,
    demo_features,
    entitlement_warnings,
    feature_suffix,
    inject_edition_lifecycle_warnings,
    is_community_free,
    is_entitled,
    license_manager,
    lifecycle_cli_message,
    load_tiers,
    offline_license_manager,
    premium_feature,
    resolve_entitlement_lifecycle,
    resolve_entitlement_state,
    resolve_license_snapshot,
    tier_features,
)

# ── Post-extract ────────────────────────────────────────────────────────
from docmirror.plugins._runtime.post_extract import (  # noqa: F401
    PostExtractHook,
    run_post_extract_hooks,
)

# ── Community-config helpers ────────────────────────────────────────────
from docmirror.plugins._runtime.community_config import (  # noqa: F401
    community_plugin_module,
    community_plugin_import_path,
    find_community_plugin,
    find_premium_community_plugin,
    get_community_premium_domains,
    get_generic_community_plugin,
    invalidate_plugin_capability_cache,
    is_community_generic_enabled,
    is_community_premium,
    is_enterprise_only,
    list_community_plugin_domains,
    list_premium_community_modules,
    load_plugin_capability,
    normalize_premium_document_type,
    should_mirror_only,
)

# ── Community plugin instances (static imports) ─────────────────────────
from docmirror.plugins._runtime.community import (  # noqa: F401
    alipay_payment_plugin,
    bank_statement_plugin,
    business_license_plugin,
    credit_report_plugin,
    generic_plugin,
    vat_invoice_plugin,
    wechat_payment_plugin,
)

# ── Discovery / Hooks / Core-extensions ─────────────────────────────────
from docmirror.plugins._runtime.discovery import (  # noqa: F401
    discover_plugins,
    get_plugin_manager,
    reset_discovery,
)
from docmirror.plugins._runtime.core_extensions import register_core_extensions  # noqa: F401

# ── Hook specs (the module, re-exported so callers can reach hookimpl) ──
from docmirror.plugins._runtime import hooks as _hooks  # noqa: F401


__all__ = [
    # plugin_registry
    "DomainPlugin",
    "PluginRegistry",
    "registry",
    "resolve_dgc_status",
    # composition
    "CompositionReason",
    "annotate_composition",
    "apply_extract_fallback",
    "apply_license_degrade",
    # runner
    "run_plugin_extract",
    "run_plugin_extract_sync",
    # state / manager
    "is_domain_enabled",
    "set_domain_enabled",
    "PluginManager",
    "plugin_manager",
    # licensing (all from licensing package __init__)
    "EntitlementLifecycle",
    "FEATURE_SUFFIX",
    "LicenseLifecycleState",
    "LicenseManager",
    "OfflineLicenseManager",
    "community_free_domains",
    "demo_features",
    "entitlement_warnings",
    "feature_suffix",
    "inject_edition_lifecycle_warnings",
    "is_community_free",
    "is_entitled",
    "license_manager",
    "lifecycle_cli_message",
    "load_tiers",
    "offline_license_manager",
    "premium_feature",
    "resolve_entitlement_lifecycle",
    "resolve_entitlement_state",
    "resolve_license_snapshot",
    "tier_features",
    # post_extract
    "PostExtractHook",
    "run_post_extract_hooks",
    # community_config
    "community_plugin_module",
    "community_plugin_import_path",
    "find_community_plugin",
    "find_premium_community_plugin",
    "get_community_premium_domains",
    "get_generic_community_plugin",
    "invalidate_plugin_capability_cache",
    "is_community_generic_enabled",
    "is_community_premium",
    "is_enterprise_only",
    "list_community_plugin_domains",
    "list_premium_community_modules",
    "load_plugin_capability",
    "normalize_premium_document_type",
    "should_mirror_only",
    # community plugin instances
    "alipay_payment_plugin",
    "bank_statement_plugin",
    "business_license_plugin",
    "credit_report_plugin",
    "generic_plugin",
    "vat_invoice_plugin",
    "wechat_payment_plugin",
    # discovery / hooks / core_extensions
    "discover_plugins",
    "get_plugin_manager",
    "hooks",
    "register_core_extensions",
    "reset_discovery",
]
