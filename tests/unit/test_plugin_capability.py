# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Core canonical capability matrix tests."""

from __future__ import annotations

def test_canonical_premium_domains_are_six():
    from docmirror.configs.domain.registry import get_canonical_premium_domains

    domains = get_canonical_premium_domains()
    assert len(domains) == 6
    assert "bank_statement" in domains
    assert "id_card" not in domains
