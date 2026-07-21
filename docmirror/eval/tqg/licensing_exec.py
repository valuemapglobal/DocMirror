# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
TQG licensing track — mock license files and entitlement probes.

Builds temporary ``.lic`` fixtures and patches entitlement resolution so TQG
cases can assert premium-feature gating, lifecycle warnings, and projection
rejection without requiring real license servers. Used exclusively in tests
and CI gate runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from docmirror.eval.tqg.manifest import TQGCase
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.plugins._runtime.licensing.contract import premium_feature
from docmirror.plugins._runtime.licensing.entitlements import is_entitled
from docmirror.plugins._runtime.licensing.lifecycle import (
    LicenseLifecycleState,
    entitlement_warnings,
    inject_edition_lifecycle_warnings,
    resolve_entitlement_lifecycle,
)
from docmirror.plugins._runtime.runner import run_plugin_extract_sync


def _mock_license(*, features: list[str], days_until_expiry: int = 365, in_grace: bool = False, expired: bool = False):
    lic = MagicMock()
    now = datetime.now()
    if expired:
        lic.expires_at = now - timedelta(days=60)
        lic.effective_expiry = now - timedelta(days=30)
        lic.is_valid = False
        lic.days_until_expiry = -60
        lic.days_until_effective_expiry = -30
    elif in_grace:
        lic.expires_at = now - timedelta(days=1)
        lic.effective_expiry = now + timedelta(days=29)
        lic.is_valid = True
        lic.days_until_expiry = -1
        lic.days_until_effective_expiry = 29
    else:
        lic.expires_at = now + timedelta(days=days_until_expiry)
        lic.effective_expiry = lic.expires_at + timedelta(days=30)
        lic.is_valid = True
        lic.days_until_expiry = days_until_expiry
        lic.days_until_effective_expiry = days_until_expiry + 30
    lic.get_features.return_value = features
    lic.get_tier.return_value = "enterprise"
    lic.license_info = {"license_id": "TQG-MOCK"}
    return lic


def _licenses_for_setup(setup: str, domain: str) -> list[Any]:
    premium = premium_feature(domain)
    if setup == "valid_premium":
        return [_mock_license(features=[premium])]
    if setup == "bare_domain_bug":
        return [_mock_license(features=[domain])]
    if setup == "grace_period":
        return [_mock_license(features=[premium], in_grace=True)]
    if setup == "expiring_soon":
        return [_mock_license(features=[premium], days_until_expiry=30)]
    if setup == "expired":
        return [_mock_license(features=[premium], expired=True)]
    return []


async def execute_licensing(case: TQGCase) -> tuple[dict[str, Any], dict[str, Any]]:
    opts = case.options
    check = str(opts.get("check") or "entitlement")
    domain = str(opts.get("domain") or "alipay_payment")
    setup = str(opts.get("setup") or "no_license")
    licenses = _licenses_for_setup(setup, domain)

    with patch("docmirror.plugins._runtime.licensing.offline.offline_license_manager._licenses", licenses):
        with patch("docmirror.plugins._runtime.licensing.online.license_manager.is_licensed", return_value=False):
            meta: dict[str, Any] = {"domain": domain, "setup": setup}

            if check == "premium_feature":
                meta["premium_feature"] = premium_feature(domain)
                return meta, meta

            lc = resolve_entitlement_lifecycle()
            meta["lifecycle_state"] = lc.state.value
            meta["is_entitled"] = is_entitled(domain)
            meta["lifecycle_days"] = lc.days_remaining
            meta["edition_warnings"] = list(entitlement_warnings(lc))

            if opts.get("run_enterprise_extract"):
                doc_type = str(opts.get("document_type") or domain)
                mirror = ParseResult(status=ResultStatus.SUCCESS)
                mirror.entities = DocumentEntities(document_type=doc_type)
                with patch("docmirror.plugins._runtime.runner._edition_package_available", return_value=True):
                    out = run_plugin_extract_sync(mirror, edition="enterprise")
                meta["projection_generated"] = out is not None
                if out:
                    if meta["is_entitled"] and lc.state in (
                        LicenseLifecycleState.EXPIRING_SOON,
                        LicenseLifecycleState.GRACE_PERIOD,
                    ):
                        out = inject_edition_lifecycle_warnings(out)
                    status_warnings = list((out.get("status") or {}).get("warnings") or [])
                    meta["edition_warnings"] = status_warnings
                meta["has_license_warning"] = "_license_warning" in meta["edition_warnings"]
            else:
                meta["projection_generated"] = False
                meta["has_license_warning"] = False

            return meta, meta
