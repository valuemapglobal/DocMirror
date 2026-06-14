# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load plugin_capability.yaml — community premium / generic / mirror_only."""

from __future__ import annotations

from functools import lru_cache

import yaml

from docmirror.configs.paths import PLUGIN_CAPABILITY_YAML

_DEFAULT_PREMIUM = (
    "bank_statement",
    "wechat_payment",
    "alipay_payment",
    "vat_invoice",
    "business_license",
    "credit_report",
)


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
    cfg = load_plugin_capability()
    return document_type in set(cfg.get("enterprise_only") or [])


def should_mirror_only(document_type: str, edition: str = "community") -> bool:
    """True when community edition should emit mirror_only (no generic fallback)."""
    if edition != "community":
        return False
    if not document_type or document_type in ("unknown", "generic", ""):
        return False
    return is_enterprise_only(document_type)


def invalidate_plugin_capability_cache() -> None:
    load_plugin_capability.cache_clear()
