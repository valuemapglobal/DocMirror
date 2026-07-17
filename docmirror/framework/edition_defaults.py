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


__all__ = ["default_editions"]
