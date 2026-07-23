# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Private plugin runtime package with side-effect-free lazy exports.

Importing the package must not discover providers, import bundled plugins, load
licensing state, or register extension points. Runtime services are loaded only
when their explicit attribute is requested.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_MODULE_EXPORTS = {
    "discovery": "docmirror.plugins._runtime.discovery",
    "hooks": "docmirror.plugins._runtime.hooks",
}

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "PluginRegistry": ("docmirror.plugins._runtime.plugin_registry", "PluginRegistry"),
    "registry": ("docmirror.plugins._runtime.plugin_registry", "registry"),
    "resolve_dgc_status": ("docmirror.plugins._runtime.plugin_registry", "resolve_dgc_status"),
    "CompositionReason": ("docmirror.plugins._runtime.composition", "CompositionReason"),
    "annotate_composition": ("docmirror.plugins._runtime.composition", "annotate_composition"),
    "discover_plugins": ("docmirror.plugins._runtime.discovery", "discover_plugins"),
    "get_plugin_manager": ("docmirror.plugins._runtime.discovery", "get_plugin_manager"),
    "reset_discovery": ("docmirror.plugins._runtime.discovery", "reset_discovery"),
    "is_domain_enabled": ("docmirror.plugins._runtime.state", "is_domain_enabled"),
    "set_domain_enabled": ("docmirror.plugins._runtime.state", "set_domain_enabled"),
    "PluginManager": ("docmirror.plugins._runtime.manager", "PluginManager"),
    "plugin_manager": ("docmirror.plugins._runtime.manager", "plugin_manager"),
}

for _name in (
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
):
    _LAZY_EXPORTS[_name] = ("docmirror.plugins._runtime.licensing", _name)


def __getattr__(name: str) -> Any:
    module_name = _MODULE_EXPORTS.get(name)
    if module_name is not None:
        value = import_module(module_name)
    else:
        target = _LAZY_EXPORTS.get(name)
        if target is None:
            raise AttributeError(name)
        value = getattr(import_module(target[0]), target[1])
    globals()[name] = value
    return value


__all__ = sorted((*_MODULE_EXPORTS, *_LAZY_EXPORTS))
