# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Community plugin capability matrix and discovery helpers.

Compatibility helpers for selecting premium community plugins versus the generic
fallback. Capability, alias, ordering, and implementation ownership now come from
each bundled plugin's ``plugin.yaml`` manifest.

Pipeline role: ``runner`` and ``plugin_registry`` call ``find_premium_community_plugin``
and ``get_generic_community_plugin`` to select the community plugin before
extract. Enterprise-only routing removed in v2 — all types use generic fallback.

Key exports: ``load_plugin_capability``, ``get_community_premium_domains``,
``find_premium_community_plugin``, ``get_generic_community_plugin``,
``find_community_plugin``, ``community_plugin_module``, ``should_mirror_only``.

Dependencies: ``plugin_registry`` manifests and ``state.is_domain_enabled``.
"""

from __future__ import annotations

from functools import cache, lru_cache
from typing import Any

from docmirror.plugins._runtime.state import is_domain_enabled


@lru_cache(maxsize=1)
def load_plugin_capability() -> dict:
    """Build the legacy capability view from plugin-owned manifests."""
    from docmirror.plugins._runtime.plugin_registry import registry

    premium: list[tuple[int, str]] = []
    aliases: dict[str, str] = {}
    generic_enabled = False
    for manifest in registry.list_provider_manifests():
        provider = manifest.get("provider") or {}
        capabilities = manifest.get("capabilities") or {}
        classification = manifest.get("classification") or {}
        domain = str(provider.get("domain_name") or "")
        if str(provider.get("edition") or "") != "community" or not domain:
            continue
        if bool(capabilities.get("premium")):
            premium.append((int(capabilities.get("community_order") or 999), domain))
        if bool(capabilities.get("generic_fallback")):
            generic_enabled = True
        for alias in classification.get("aliases") or []:
            normalized = str(alias or "").strip()
            if normalized:
                aliases[normalized] = domain
    premium.sort(key=lambda item: (item[0], item[1]))
    return {
        "community_premium_domains": [domain for _order, domain in premium],
        "community_generic_enabled": generic_enabled,
        "enterprise_only": [],
        "aliases": aliases,
    }


def get_community_premium_domains() -> tuple[str, ...]:
    cfg = load_plugin_capability()
    domains = cfg.get("community_premium_domains") or ()
    return tuple(domains)


@cache
def get_quality_group_domains(group: str) -> tuple[str, ...]:
    """Return plugin domains that opt into a named quality metric group."""
    from docmirror.plugins._runtime.plugin_registry import registry

    domains: list[str] = []
    for manifest in registry.list_provider_manifests():
        provider = manifest.get("provider") or {}
        capabilities = manifest.get("capabilities") or {}
        domain = str(provider.get("domain_name") or "").strip()
        groups = {str(value).strip() for value in capabilities.get("quality_groups") or ()}
        if domain and group in groups:
            domains.append(domain)
    return tuple(sorted(set(domains)))


def is_community_premium(document_type: str) -> bool:
    return document_type in get_community_premium_domains()


def is_community_generic_enabled() -> bool:
    cfg = load_plugin_capability()
    return bool(cfg.get("community_generic_enabled", True))


def is_enterprise_only(document_type: str) -> bool:
    """Return whether a document type is restricted to enterprise routing."""
    return False


def should_mirror_only(document_type: str, edition: str = "community") -> bool:
    """Return whether a document type should skip community projection."""
    return False


def invalidate_plugin_capability_cache() -> None:
    load_plugin_capability.cache_clear()
    get_quality_group_domains.cache_clear()


def community_plugin_module(domain: str) -> str:
    """Module path relative to ``docmirror.plugins`` (e.g. ``bank_statement.community_plugin``)."""
    return f"{domain}.community_plugin"


def community_plugin_import_path(domain: str) -> str:
    """Fully qualified import path for a domain community plugin module."""
    return f"docmirror.plugins.{community_plugin_module(domain)}"


def normalize_premium_document_type(document_type: str) -> str:
    """Map raw mirror document types to premium plugin domain names (M9)."""
    aliases = load_plugin_capability().get("aliases") or {}
    return aliases.get(document_type, document_type)


def find_premium_community_plugin(detected_type: str) -> tuple[Any, str]:
    """Match one of the six premium community plugins by domain_name."""
    detected_type = normalize_premium_document_type(detected_type)
    if not is_community_premium(detected_type):
        return None, ""
    if not is_domain_enabled(detected_type):
        return None, ""
    from docmirror.plugins._runtime.plugin_registry import registry

    modname = community_plugin_module(detected_type)
    plugin = registry.get(detected_type, "community")
    if plugin is not None and getattr(plugin, "domain_name", None) == detected_type:
        return plugin, modname
    return None, ""


def get_generic_community_plugin() -> tuple[Any, str]:
    """Return the singleton generic community fallback plugin."""
    if not is_domain_enabled("generic"):
        return None, ""
    from docmirror.plugins._runtime.plugin_registry import registry

    plugin = registry.get("generic", "community")
    if plugin is None:
        return None, ""
    return plugin, community_plugin_module("generic")


def find_community_plugin(detected_type: str) -> tuple[Any, str]:
    """Return the premium community plugin for a detected document type."""
    return find_premium_community_plugin(detected_type)


def list_premium_community_modules() -> tuple[str, ...]:
    return tuple(community_plugin_module(d) for d in get_community_premium_domains())


def list_community_plugin_domains() -> tuple[str, ...]:
    """Premium domains plus generic fallback package name."""
    return (*get_community_premium_domains(), "generic")
