# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Tier and feature catalog loader — ``configs/yaml/licensing/tiers.yaml`` SSOT.

Caches YAML defining ``feature_suffix``, ``community_free_domains``, per-tier
feature lists, and optional finance/enterprise registry expansion for demo licenses.

Pipeline role: feeds ``contract.premium_feature``, ``entitlements.demo_features``,
``lifecycle`` thresholds, and ``snapshot`` display metadata.

Key exports: ``load_tiers``, ``community_free_domains``, ``feature_suffix``,
``tier_features``, ``premium_feature``.

Dependencies: ``configs.paths.TIERS_YAML``, optional ``docmirror_finance`` /
``docmirror_enterprise`` registries for feature expansion.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from docmirror.configs.paths import TIERS_YAML

_DEFAULT_COMMUNITY_FREE = (
    "bank_statement",
    "wechat_payment",
    "alipay_payment",
    "vat_invoice",
    "business_license",
    "credit_report",
)


@lru_cache(maxsize=1)
def load_tiers() -> dict[str, Any]:
    if not TIERS_YAML.is_file():
        return {
            "feature_suffix": "_premium",
            "community_free_domains": list(_DEFAULT_COMMUNITY_FREE),
            "tiers": {},
        }
    with open(TIERS_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not data.get("community_free_domains"):
        data["community_free_domains"] = list(_DEFAULT_COMMUNITY_FREE)
    return data


def community_free_domains() -> list[str]:
    return list(load_tiers().get("community_free_domains") or _DEFAULT_COMMUNITY_FREE)


def feature_suffix() -> str:
    return str(load_tiers().get("feature_suffix") or "_premium")


def premium_feature(domain: str) -> str:
    from docmirror.plugins.licensing.contract import premium_feature as _premium_feature

    return _premium_feature(domain)


def tier_features(tier: str) -> list[str]:
    tiers = load_tiers().get("tiers") or {}
    entry = tiers.get(tier) or {}
    features: set[str] = set(entry.get("features") or [])

    if entry.get("include_all_finance_domains"):
        features.update(_finance_registry_premium_features())

    return sorted(features)


def _finance_registry_premium_features() -> set[str]:
    """All ``{domain}_premium`` for registered finance plugins (when package installed)."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        import docmirror_finance.enable as finance_enable
        from docmirror.plugins import registry
    except ImportError:
        return set()

    try:
        finance_enable.register_finance_plugins(registry)
    except Exception as exc:
        logger.debug("[TiersLoader] Finance registry scan failed: %s", exc)
        return set()

    suffix = feature_suffix()
    out: set[str] = set()
    for name in registry.list_plugins():
        plugin = registry.get(name, "finance")
        if plugin is None or getattr(plugin, "edition", "") != "finance":
            continue
        if not getattr(plugin, "requires_license", False):
            continue
        domain = getattr(plugin, "domain_name", name) or name
        out.add(f"{domain}{suffix}")
    return out
