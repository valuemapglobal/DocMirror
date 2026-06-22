# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GA readiness and Community route taxonomy helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from docmirror.configs.paths import GA_READINESS_YAML

CORE_DOMAIN_ROUTE = "core_domain"
GENERIC_FALLBACK_ROUTE = "generic_fallback"
ENTERPRISE_ONLY_ROUTE = "enterprise_only"
MIRROR_ONLY_ROUTE = "mirror_only"


@lru_cache(maxsize=1)
def load_ga_readiness() -> dict[str, Any]:
    if not GA_READINESS_YAML.is_file():
        return {"version": 1, "domains": {}, "community_core_domains": []}
    return yaml.safe_load(GA_READINESS_YAML.read_text(encoding="utf-8")) or {}


def community_core_domains() -> tuple[str, ...]:
    data = load_ga_readiness()
    return tuple(data.get("community_core_domains") or ())


def domain_readiness(domain: str) -> dict[str, Any]:
    domains = load_ga_readiness().get("domains") or {}
    return dict(domains.get(domain) or {})


def community_route_for_domain(domain: str) -> str:
    if not domain or domain in {"unknown", "generic"}:
        return GENERIC_FALLBACK_ROUTE
    info = domain_readiness(domain)
    if info.get("community_route"):
        return str(info["community_route"])
    if domain in community_core_domains():
        return CORE_DOMAIN_ROUTE
    return GENERIC_FALLBACK_ROUTE


def dgc_status_for_domain(domain: str) -> str:
    return str(domain_readiness(domain).get("dgc_status") or "unknown")


def support_level_for_domain(domain: str) -> str:
    return str(domain_readiness(domain).get("support_level") or "unknown")


def edition_sku_status(domain: str, edition: str) -> str:
    sku = domain_readiness(domain).get("sku") or {}
    return str(sku.get(edition) or "unknown")


def compact_domain_readiness(domain: str) -> dict[str, Any]:
    info = domain_readiness(domain)
    route = community_route_for_domain(domain)
    return {
        "domain": domain or "generic",
        "dgc_status": info.get("dgc_status") or "unknown",
        "support_level": info.get("support_level") or "unknown",
        "community_route": route,
        "edition_schema_gate": bool(info.get("edition_schema_gate")),
        "evidence_gate": bool(info.get("evidence_gate")),
        "sku": dict(info.get("sku") or {}),
    }


def invalidate_ga_readiness_cache() -> None:
    load_ga_readiness.cache_clear()
