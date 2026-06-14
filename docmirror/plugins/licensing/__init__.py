# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Licensing SSOT helpers."""

from docmirror.plugins.licensing.contract import FEATURE_SUFFIX, is_community_free, premium_feature
from docmirror.plugins.licensing.entitlements import demo_features, is_entitled
from docmirror.plugins.licensing.lifecycle import (
    EntitlementLifecycle,
    LicenseLifecycleState,
    entitlement_warnings,
    inject_edition_lifecycle_warnings,
    lifecycle_cli_message,
    resolve_entitlement_lifecycle,
    resolve_entitlement_state,
)
from docmirror.plugins.licensing.snapshot import resolve_license_snapshot
from docmirror.plugins.licensing.tiers_loader import (
    community_free_domains,
    feature_suffix,
    load_tiers,
    tier_features,
)

__all__ = [
    "FEATURE_SUFFIX",
    "EntitlementLifecycle",
    "LicenseLifecycleState",
    "community_free_domains",
    "demo_features",
    "entitlement_warnings",
    "feature_suffix",
    "inject_edition_lifecycle_warnings",
    "is_community_free",
    "is_entitled",
    "lifecycle_cli_message",
    "load_tiers",
    "premium_feature",
    "resolve_entitlement_lifecycle",
    "resolve_entitlement_state",
    "resolve_license_snapshot",
    "tier_features",
]
