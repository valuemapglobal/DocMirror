# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Community plugin capability matrix and discovery helpers.

Single source of truth for which document types ship as premium community
plugins (six domains) versus the generic fallback, driven by
``configs/yaml/plugin_capability.yaml``. Resolves import paths, loads
``community_plugin`` modules on demand, and gates discovery on per-domain
enable state from ``state``.

Pipeline role: ``runner`` and ``plugin_registry`` call ``find_premium_community_plugin``
and ``get_generic_community_plugin`` to select the community plugin before
extract. Enterprise-only routing removed in v2 — all types use generic fallback.

Key exports: ``load_plugin_capability``, ``get_community_premium_domains``,
``find_premium_community_plugin``, ``get_generic_community_plugin``,
``find_community_plugin``, ``community_plugin_module``, ``should_mirror_only``.

Dependencies: ``configs.paths.PLUGIN_CAPABILITY_YAML``, ``state.is_domain_enabled``,
``importlib`` for lazy plugin module loading.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

import yaml

from docmirror.configs.paths import PLUGIN_CAPABILITY_YAML
from docmirror.plugins._runtime.state import is_domain_enabled

_DEFAULT_PREMIUM = (
    "bank_statement",
    "wechat_payment",
    "alipay_payment",
    "vat_invoice",
    "business_license",
    "credit_report",
)

_GENERIC_MODULE = "generic.community_plugin"
_GENERIC_PLUGIN: Any | None = None


@lru_cache(maxsize=1)
def load_plugin_capability() -> dict:
    if not PLUGIN_CAPABILITY_YAML.is_file():
        return {
            "community_premium_domains": list(_DEFAULT_PREMIUM),
            "community_generic_enabled": True,
            "enterprise_only": [],
        }
    with open(PLUGIN_CAPABILITY_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_community_premium_domains() -> tuple[str, ...]:
    cfg = load_plugin_capability()
    domains = cfg.get("community_premium_domains") or _DEFAULT_PREMIUM
    return tuple(domains)


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


def community_plugin_module(domain: str) -> str:
    """Module path relative to ``docmirror.plugins`` (e.g. ``bank_statement.community_plugin``)."""
    return f"{domain}.community_plugin"


def community_plugin_import_path(domain: str) -> str:
    """Fully qualified import path for a domain community plugin module."""
    return f"docmirror.plugins.{community_plugin_module(domain)}"


def _load_plugin(module_path: str) -> Any | None:
    try:
        mod = importlib.import_module(f"docmirror.plugins.{module_path}")
    except Exception:
        return None
    return getattr(mod, "plugin", None)


_PLUGIN_TYPE_ALIASES: dict[str, str] = {
    "bank_reconciliation": "bank_statement",
    "credit_report_enterprise": "credit_report",
}


def normalize_premium_document_type(document_type: str) -> str:
    """Map raw mirror document types to premium plugin domain names (M9)."""
    return _PLUGIN_TYPE_ALIASES.get(document_type, document_type)


def find_premium_community_plugin(detected_type: str) -> tuple[Any, str]:
    """Match one of the six premium community plugins by domain_name."""
    detected_type = normalize_premium_document_type(detected_type)
    if not is_community_premium(detected_type):
        return None, ""
    if not is_domain_enabled(detected_type):
        return None, ""
    modname = community_plugin_module(detected_type)
    plugin = _load_plugin(modname)
    if plugin is not None and getattr(plugin, "domain_name", None) == detected_type:
        return plugin, modname
    return None, ""


def get_generic_community_plugin() -> tuple[Any, str]:
    """Return the singleton generic community fallback plugin."""
    global _GENERIC_PLUGIN
    if not is_domain_enabled("generic"):
        return None, ""
    if _GENERIC_PLUGIN is None:
        _GENERIC_PLUGIN = _load_plugin(_GENERIC_MODULE)
    if _GENERIC_PLUGIN is None:
        return None, ""
    return _GENERIC_PLUGIN, _GENERIC_MODULE


def find_community_plugin(detected_type: str) -> tuple[Any, str]:
    """Return the premium community plugin for a detected document type."""
    return find_premium_community_plugin(detected_type)


def list_premium_community_modules() -> tuple[str, ...]:
    return tuple(community_plugin_module(d) for d in get_community_premium_domains())


def list_community_plugin_domains() -> tuple[str, ...]:
    """Premium domains plus generic fallback package name."""
    return (*get_community_premium_domains(), "generic")
