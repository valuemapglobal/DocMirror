# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Licensing naming contract — premium feature string conventions.

Derives runtime entitlement feature names as ``{domain}_premium`` (suffix from
``tiers.yaml``) and identifies domains that are free in community edition without
a license check.

Pipeline role: ``entitlements.is_entitled`` and ``runner._premium_feature_name``
use ``premium_feature``; tier loaders re-export ``is_community_free`` for docs/CLI.

Key exports: ``FEATURE_SUFFIX``, ``premium_feature``, ``is_community_free``.

Dependencies: ``licensing.tiers_loader`` (suffix and community-free domain list).
"""

from __future__ import annotations

FEATURE_SUFFIX = "_premium"


def premium_feature(domain: str, *, suffix: str | None = None) -> str:
    """Derive the runtime entitlement feature name for a domain."""
    from docmirror.plugins.licensing.tiers_loader import feature_suffix

    effective_suffix = suffix if suffix is not None else feature_suffix()
    if domain.endswith(effective_suffix):
        return domain
    return f"{domain}{effective_suffix}"


def is_community_free(domain: str) -> bool:
    """Return True when domain is a community premium-free plugin (6+1)."""
    from docmirror.plugins.licensing.tiers_loader import community_free_domains

    return domain in community_free_domains()
