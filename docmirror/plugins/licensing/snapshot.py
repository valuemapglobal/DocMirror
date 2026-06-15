# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unified license snapshot for CLI ``license show``."""

from __future__ import annotations

from typing import Any

from docmirror.plugins.licensing.tiers_loader import load_tiers


def resolve_license_snapshot() -> dict[str, Any]:
    """Merge offline `.lic` state with online license cache."""
    from docmirror.plugins.licensing.online import license_manager
    from docmirror.plugins.licensing.offline import offline_license_manager
    from docmirror.plugins.licensing.lifecycle import resolve_entitlement_lifecycle

    tiers = load_tiers()
    lifecycle_cfg = tiers.get("lifecycle") or {}
    lifecycle = resolve_entitlement_lifecycle()

    offline = offline_license_manager.get_license_info()
    online = license_manager.get_license_info()
    offline_list = offline_license_manager.list_licenses()

    active_channel: str | None = None
    if offline and offline.get("is_valid"):
        active_channel = "offline"
    elif online and not online.get("is_expired"):
        active_channel = "online"

    entitled_sample: list[str] = []
    if offline and offline.get("features"):
        entitled_sample = list(offline["features"][:12])
    elif online and online.get("plugins"):
        entitled_sample = list(online["plugins"][:12])

    return {
        "active_channel": active_channel,
        "lifecycle_state": lifecycle.state.value,
        "lifecycle_days_remaining": lifecycle.days_remaining,
        "lifecycle_channel": lifecycle.channel,
        "renewal_url": lifecycle.renewal_url,
        "offline": offline,
        "offline_licenses": offline_list,
        "online": online,
        "entitled_features_sample": entitled_sample,
        "lifecycle": {
            "expiring_soon_days": lifecycle_cfg.get("expiring_soon_days", 90),
            "offline_grace_period_days": lifecycle_cfg.get("offline_grace_period_days", 30),
            "online_verify_grace_days": lifecycle_cfg.get("online_verify_grace_days", 7),
            "renewal_url": lifecycle_cfg.get("renewal_url", "https://docmirror.com/pricing/renew"),
        },
    }
