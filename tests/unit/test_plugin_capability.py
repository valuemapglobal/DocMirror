# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin capability matrix tests.

enterprise_only routing removed in v2 — all types use generic community
fallback with upgrade hints instead of mirror_only empty envelopes.
"""

from __future__ import annotations

from docmirror.plugins._runtime.community import is_enterprise_only, should_mirror_only


def test_enterprise_only_always_false():
    """enterprise_only routing removed in v2 — always returns False."""
    assert is_enterprise_only("audit_report") is False
    assert is_enterprise_only("balance_sheet") is False


def test_should_mirror_only_always_false():
    """mirror_only routing removed in v2 — always returns False."""
    assert should_mirror_only("audit_report", "community") is False
    assert should_mirror_only("bank_statement", "community") is False
    assert should_mirror_only("id_card", "community") is False


def test_community_premium_domains_are_six():
    from docmirror.plugins._runtime.community import get_community_premium_domains

    domains = get_community_premium_domains()
    assert len(domains) == 6
    assert "bank_statement" in domains
    assert "id_card" not in domains
