# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent router 6+1 alignment tests."""

from __future__ import annotations

from docmirror.features.agent.router import route_document


def test_core_domains_route_to_core_domain_tier():
    route = route_document("alipay_payment")
    assert route.community_tier == "core_domain"
    assert route.recommended_plugins == ["alipay_payment"]


def test_id_card_routes_to_generic_plugin():
    route = route_document("id_card")
    assert route.community_tier == "generic_fallback"
    assert route.recommended_plugins == ["generic"]


def test_audit_report_enterprise_only():
    route = route_document("audit_report")
    assert route.community_tier == "enterprise_only"
