# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Stable default delivery editions shared by every public surface."""

from __future__ import annotations

from typing import Literal

Edition = Literal["mirror", "community", "enterprise", "finance"]


def default_editions() -> tuple[Edition, ...]:
    """Return the explicit-configuration-free delivery default.

    Community JSON is the only implicit artifact regardless of installed
    entitlements. Mirror and extended editions require an explicit edition or
    output profile, keeping CLI/API/SDK behavior deterministic.
    """
    return ("community",)


def default_cli_editions() -> tuple[Edition, ...]:
    """Return artifacts persisted by a bare document CLI invocation.

    The CLI keeps the canonical Mirror artifact beside the consumer-facing
    Community projection. Programmatic surfaces continue to use
    :func:`default_editions` and therefore remain Community-only by default.
    """
    return ("mirror", "community")


def licensed_cli_editions(tier: str | None = None) -> tuple[Edition, ...]:
    """Return every installed edition allowed by the active license.

    ``resolve_edition_tier`` already combines entitlement state with installed
    commercial packages. Accepting an explicit tier keeps the edition matrix
    independently testable without loading a local license.
    """
    if tier is None:
        from docmirror.plugins._runtime.licensing.entitlements import resolve_edition_tier

        tier = resolve_edition_tier()
    normalized = str(tier or "community").strip().lower()
    if normalized == "finance":
        return ("mirror", "community", "enterprise", "finance")
    if normalized == "enterprise":
        return ("mirror", "community", "enterprise")
    return default_cli_editions()


__all__ = ["default_cli_editions", "default_editions", "licensed_cli_editions"]
