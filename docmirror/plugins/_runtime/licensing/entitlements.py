# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Enterprise and finance entitlement checks — PEC single entry point.

Answers whether a domain's ``{domain}_premium`` feature is present in a valid
offline ``.lic`` file or online license cache. Community-free domains do not
bypass this check for edition plugins that set ``requires_license=True``.
``resolve_edition_tier`` derives the highest edition level from installed
packages after verifying the license.

Pipeline role: ``output_builder.build_extended_output`` delegates here before
running enterprise/finance ``extract``; unlicensed plugins degrade to community
baseline with ``_license_warning`` markers.

Key exports: ``is_entitled``, ``resolve_edition_tier``, ``demo_features``.

Dependencies: ``licensing.contract``, ``licensing.offline``, ``licensing.online``,
``licensing.tiers_loader``.
"""

from __future__ import annotations

import logging

from docmirror.plugins._runtime.licensing.contract import premium_feature

logger = logging.getLogger(__name__)


def _offline_has_feature(feature: str) -> bool:
    try:
        from docmirror.plugins._runtime.licensing.offline import offline_license_manager

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
        from docmirror.plugins._runtime.licensing.online import license_manager

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


def _has_any_license() -> bool:
    """Check whether ANY valid commercial license exists (offline or online)."""
    try:
        from docmirror.plugins._runtime.licensing.offline import offline_license_manager

        for lic in offline_license_manager._licenses:
            if not lic.is_valid:
                continue
            features = lic.get_features()
            if "*" in features:
                return True
            if any(f.endswith("_premium") for f in features):
                return True
    except Exception:
        pass
    try:
        from docmirror.plugins._runtime.licensing.online import license_manager

        cached = license_manager._cached_license
        if cached is not None and cached.is_valid:
            return True
    except Exception:
        pass
    return False


def resolve_edition_tier() -> str:
    """
    Determine the highest edition tier available.

    Logic:
    1. Check offline/online licenses for ANY commercial entitlement
       (wildcard ``*`` or any ``{domain}_premium`` feature).
    2. If no license → ``\"community\"``
    3. If licensed → max tier from installed packages:
       - ``docmirror_finance`` installed → ``\"finance\"``
       - ``docmirror_enterprise`` installed → ``\"enterprise\"``
       - Neither installed → ``\"community\"`` (with downstream install prompt)

    No sentinel features needed in license files.
    """
    if not _has_any_license():
        return "community"
    try:
        import docmirror_finance  # noqa: F401

        return "finance"
    except ImportError:
        pass
    try:
        import docmirror_enterprise  # noqa: F401

        return "enterprise"
    except ImportError:
        pass
    return "community"


def demo_features() -> list[str]:
    """Build demo ``.lic`` feature list from tiers SSOT + installed enterprise registry."""
    from docmirror.plugins._runtime.licensing.tiers_loader import load_tiers, tier_features

    tiers = load_tiers()
    demo_cfg = tiers.get("demo") or {}
    tier_name = str(demo_cfg.get("tier") or "enterprise")
    features: set[str] = set(tier_features(tier_name))

    if demo_cfg.get("include_all_enterprise_domains"):
        try:
            from docmirror.plugins._runtime import registry

            for plugin in registry.list_projectors("enterprise"):
                if not getattr(plugin, "requires_license", False):
                    continue
                domain = str(getattr(plugin, "domain_name", "") or "")
                if not domain:
                    continue
                features.add(premium_feature(domain))
        except Exception as exc:
            logger.debug("[Entitlements] Registry scan for demo features failed: %s", exc)

    features.discard("*")
    return sorted(features)
