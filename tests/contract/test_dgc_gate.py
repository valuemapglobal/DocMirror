# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""DGC remains descriptive readiness metadata, not an execution gate."""

from __future__ import annotations

import pytest

from docmirror.plugins._runtime.plugin_registry import resolve_dgc_status


@pytest.mark.parametrize(
    "domain,expected",
    [
        ("bank_statement", "ga"),
        ("vat_invoice", "candidate"),
        ("unknown_domain_xyz", "unknown"),
        ("", "unknown"),
    ],
)
def test_resolve_dgc_status_is_total_and_descriptive(domain: str, expected: str) -> None:
    assert resolve_dgc_status(domain) == expected
