# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Edition defaults resolved outside the core compatibility entry layer."""

from __future__ import annotations

from typing import Literal

Edition = Literal["mirror", "community", "enterprise", "finance"]


def default_editions() -> tuple[Edition, ...]:
    """Return license-aware default editions, falling back to community."""
    tier = _resolve_edition_tier()
    if tier == "finance":
        return ("mirror", "community", "enterprise", "finance")
    if tier == "enterprise":
        return ("mirror", "community", "enterprise")
    return ("mirror", "community")


def _resolve_edition_tier() -> str:
    try:
        from docmirror.plugins._runtime.licensing.entitlements import resolve_edition_tier

        return str(resolve_edition_tier())
    except Exception:
        pass
    try:
        from docmirror.plugins._runtime.licensing.offline import offline_license_manager

        lic_info = offline_license_manager.get_license_info()
        if lic_info:
            return str(lic_info.get("tier") or "")
    except Exception:
        pass
    return "community"


__all__ = ["default_editions"]
