# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
License Expiry Plane (LEP) — lifecycle state and user-visible warnings.

Tracks entitlement lifecycle (active, expiring soon, grace period, expired,
missing) from offline and online license metadata, and injects structured
warnings into edition JSON for enterprise/finance output.

Pipeline role: ``runner._finalize_extract`` may call ``inject_edition_lifecycle_warnings``
after extended edition extract; CLI uses ``lifecycle_cli_message`` and
``resolve_entitlement_lifecycle`` for ``license show`` / renew prompts.

Key exports: ``LicenseLifecycleState``, ``EntitlementLifecycle``,
``resolve_entitlement_lifecycle``, ``resolve_entitlement_state``,
``entitlement_warnings``, ``inject_edition_lifecycle_warnings``,
``lifecycle_cli_message``.

Dependencies: ``licensing.tiers_loader`` (lifecycle thresholds), offline/online managers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from docmirror.plugins._runtime.licensing.tiers_loader import load_tiers


class LicenseLifecycleState(str, Enum):
    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    GRACE_PERIOD = "grace_period"
    EXPIRED = "expired"
    MISSING = "missing"


@dataclass(frozen=True)
class EntitlementLifecycle:
    state: LicenseLifecycleState
    days_remaining: int = 0
    channel: str = ""
    renewal_url: str = ""


def _lifecycle_config() -> dict[str, Any]:
    return load_tiers().get("lifecycle") or {}


def _offline_lifecycle() -> EntitlementLifecycle | None:
    try:
        from docmirror.plugins._runtime.licensing.offline import offline_license_manager
    except Exception:
        return None

    if not offline_license_manager._licenses:
        return None

    best = max(offline_license_manager._licenses, key=lambda lic: len(lic.get_features()))
    cfg = _lifecycle_config()
    expiring_days = int(cfg.get("expiring_soon_days") or 90)
    renewal_url = str(cfg.get("renewal_url") or "https://docmirror.com/pricing/renew")
    now = datetime.now()

    if now > best.effective_expiry:
        return EntitlementLifecycle(
            state=LicenseLifecycleState.EXPIRED,
            days_remaining=0,
            channel="offline",
            renewal_url=renewal_url,
        )

    if now > best.expires_at:
        return EntitlementLifecycle(
            state=LicenseLifecycleState.GRACE_PERIOD,
            days_remaining=max(0, best.days_until_effective_expiry),
            channel="offline",
            renewal_url=renewal_url,
        )

    days = best.days_until_expiry
    if 0 < days <= expiring_days:
        return EntitlementLifecycle(
            state=LicenseLifecycleState.EXPIRING_SOON,
            days_remaining=days,
            channel="offline",
            renewal_url=renewal_url,
        )

    if best.is_valid:
        return EntitlementLifecycle(
            state=LicenseLifecycleState.ACTIVE,
            days_remaining=max(0, days),
            channel="offline",
            renewal_url=renewal_url,
        )

    return EntitlementLifecycle(
        state=LicenseLifecycleState.EXPIRED,
        days_remaining=0,
        channel="offline",
        renewal_url=renewal_url,
    )


def _online_lifecycle() -> EntitlementLifecycle | None:
    try:
        from docmirror.plugins._runtime.licensing.online import license_manager
    except Exception:
        return None

    cached = license_manager._cached_license
    if cached is None:
        return None

    cfg = _lifecycle_config()
    expiring_days = int(cfg.get("expiring_soon_days") or 90)
    renewal_url = str(cfg.get("renewal_url") or "https://docmirror.com/pricing/renew")

    if cached.is_expired:
        return EntitlementLifecycle(
            state=LicenseLifecycleState.EXPIRED,
            days_remaining=0,
            channel="online",
            renewal_url=renewal_url,
        )

    days = cached.days_remaining
    if 0 < days <= expiring_days:
        return EntitlementLifecycle(
            state=LicenseLifecycleState.EXPIRING_SOON,
            days_remaining=days,
            channel="online",
            renewal_url=renewal_url,
        )

    return EntitlementLifecycle(
        state=LicenseLifecycleState.ACTIVE,
        days_remaining=days,
        channel="online",
        renewal_url=renewal_url,
    )


def resolve_entitlement_state() -> LicenseLifecycleState:
    """Return the dominant license lifecycle state (offline preferred)."""
    return resolve_entitlement_lifecycle().state


def resolve_entitlement_lifecycle() -> EntitlementLifecycle:
    """Resolve lifecycle from offline `.lic` (preferred) or online cache."""
    cfg = _lifecycle_config()
    renewal_url = str(cfg.get("renewal_url") or "https://docmirror.com/pricing/renew")

    offline = _offline_lifecycle()
    if offline is not None:
        return offline

    online = _online_lifecycle()
    if online is not None:
        return online

    return EntitlementLifecycle(
        state=LicenseLifecycleState.MISSING,
        days_remaining=0,
        channel="",
        renewal_url=renewal_url,
    )


def entitlement_warnings(lifecycle: EntitlementLifecycle | None = None) -> list[str]:
    """Map lifecycle state to edition JSON warning tags."""
    lc = lifecycle or resolve_entitlement_lifecycle()
    if lc.state == LicenseLifecycleState.EXPIRING_SOON:
        return [f"_license_expiring_soon:{lc.days_remaining}d"]
    if lc.state == LicenseLifecycleState.GRACE_PERIOD:
        return [f"_license_grace_period:{lc.days_remaining}d"]
    return []


def inject_edition_lifecycle_warnings(payload: dict[str, Any]) -> dict[str, Any]:
    """Append LEP warnings to enterprise/finance JSON when configured."""
    cfg = _lifecycle_config()
    if not cfg.get("warn_in_edition_json", True):
        return payload

    warnings = entitlement_warnings()
    if not warnings:
        return payload

    status = payload.setdefault("status", {})
    wlist = status.setdefault("warnings", [])
    for tag in warnings:
        if tag not in wlist:
            wlist.append(tag)
    return payload


def lifecycle_cli_message(lifecycle: EntitlementLifecycle | None = None) -> str | None:
    """One-line CLI banner for parse (when ``warn_on_parse`` is enabled)."""
    cfg = _lifecycle_config()
    if not cfg.get("warn_on_parse", True):
        return None

    lc = lifecycle or resolve_entitlement_lifecycle()
    if lc.state == LicenseLifecycleState.EXPIRING_SOON:
        return f"License expiring in {lc.days_remaining} days — renew at {lc.renewal_url}"
    if lc.state == LicenseLifecycleState.GRACE_PERIOD:
        return f"License in grace period ({lc.days_remaining} days left) — renew at {lc.renewal_url}"
    return None
