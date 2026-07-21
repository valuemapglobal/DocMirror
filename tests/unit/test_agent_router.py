# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Agent document routing tests (EFPA P7 / L11)."""

from __future__ import annotations

from docmirror.features.agent.router import route_document


def test_route_wechat_payment():
    route = route_document("wechat_payment", page_count=219, confidence=0.95)
    assert route.enhance_mode == "full"
    assert "wechat_payment" in route.recommended_plugins
    assert not hasattr(route, "export_formats")
    assert route.layout_profile_hint == "borderless_ledger_wechat"


def test_route_bank_statement():
    route = route_document("bank_statement", page_count=5, confidence=0.8)
    assert "bank_statement" in route.recommended_plugins
    assert not hasattr(route, "export_formats")


def test_route_generic_low_confidence_note():
    route = route_document("unknown_type", page_count=1, confidence=0.2)
    assert route.enhance_mode == "standard"
    assert any("Low classify confidence" in n for n in route.notes)


def test_route_large_document_note():
    route = route_document("credit_report", page_count=80, confidence=0.9)
    assert route.enhance_mode == "full"
    assert any("Large document" in n for n in route.notes)


def test_route_business_license():
    route = route_document("business_license", page_count=1, confidence=0.9)
    assert "business_license" in route.recommended_plugins
    assert not hasattr(route, "export_formats")


def test_route_audit_report():
    route = route_document("audit_report", page_count=2, confidence=0.85)
    assert "audit_report" in route.recommended_plugins
