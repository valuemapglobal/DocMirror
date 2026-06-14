# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enterprise/Finance entitlement checks — PEC single entry point."""

from __future__ import annotations

import logging
from typing import Any

from docmirror.plugins.licensing.contract import premium_feature

logger = logging.getLogger(__name__)


def _offline_has_feature(feature: str) -> bool:
    try:
        from docmirror.plugins.offline_license import offline_license_manager

        for license_file in offline_license_manager._licenses:
            if not license_file.is_valid:
                continue
            features = license_file.get_features()
            if "*" in features:
                return True
            if feature in features:
                return True
    except Exception as exc:
        logger.debug("[Entitlements] Offline check failed: %s", exc)
    return False


def _online_has_feature(feature: str) -> bool:
    try:
        from docmirror.plugins.license import license_manager

        return license_manager.is_licensed(feature)
    except Exception as exc:
        logger.debug("[Entitlements] Online check failed: %s", exc)
    return False


def is_entitled(domain: str) -> bool:
    """
    Check enterprise/finance entitlement for a domain.

    Requires ``{domain}_premium`` in a valid offline or online license.
    Community-free domains do **not** bypass this check for edition plugins.
    """
    feature = premium_feature(domain)
    if _offline_has_feature(feature):
        return True
    return _online_has_feature(feature)


def demo_features() -> list[str]:
    """Build demo ``.lic`` feature list from tiers SSOT + installed enterprise registry."""
    from docmirror.plugins.licensing.tiers_loader import load_tiers, tier_features

    tiers = load_tiers()
    demo_cfg = tiers.get("demo") or {}
    tier_name = str(demo_cfg.get("tier") or "enterprise")
    features: set[str] = set(tier_features(tier_name))

    if demo_cfg.get("include_all_enterprise_domains"):
        try:
            from docmirror.plugins import registry

            for name in registry.list_plugins():
                plugin = registry.get(name)
                if plugin is None:
                    continue
                if getattr(plugin, "edition", "") != "enterprise":
                    continue
                if not getattr(plugin, "requires_license", False):
                    continue
                domain = getattr(plugin, "domain_name", name) or name
                features.add(premium_feature(domain))
        except Exception as exc:
            logger.debug("[Entitlements] Registry scan for demo features failed: %s", exc)

    features.discard("*")
    return sorted(features)
