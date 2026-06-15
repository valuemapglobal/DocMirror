# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin capability matrix tests."""

from __future__ import annotations

from docmirror.plugins.community import is_enterprise_only, should_mirror_only


def test_audit_report_is_enterprise_only():
    assert is_enterprise_only("audit_report") is True


def test_bank_statement_has_community_plugin():
    assert should_mirror_only("bank_statement", "community") is False


def test_audit_report_mirror_only_on_community():
    assert should_mirror_only("audit_report", "community") is True


def test_id_card_uses_generic_not_mirror_only():
    assert should_mirror_only("id_card", "community") is False


def test_community_premium_domains_are_six():
    from docmirror.plugins.community import get_community_premium_domains

    domains = get_community_premium_domains()
    assert len(domains) == 6
    assert "bank_statement" in domains
    assert "id_card" not in domains
