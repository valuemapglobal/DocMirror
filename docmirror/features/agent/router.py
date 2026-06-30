# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""
Document routing hints for agent and automation workflows (L11 / P7).

Derives recommended parse parameters — document type, enhancement mode, layout
profile hints — from an existing ``ParseResult`` or lightweight metadata.
Does not execute parsing; downstream agents use ``DocumentRoute`` to choose
plugins, middleware profiles, or re-parse options.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from docmirror.configs.ga_readiness import (
    CORE_DOMAIN_ROUTE,
    ENTERPRISE_ONLY_ROUTE,
    GENERIC_FALLBACK_ROUTE,
)


class DocumentRoute(BaseModel):
    """Recommended parse path — does not execute parsing."""

    document_type: str = "generic"
    enhance_mode: str = "standard"
    layout_profile_hint: str | None = None
    recommended_plugins: list[str] = Field(default_factory=list)
    community_tier: str = GENERIC_FALLBACK_ROUTE
    export_formats: list[str] = Field(default_factory=lambda: ["json", "udif"])
    notes: list[str] = Field(default_factory=list)


_DOMAIN_ROUTES: dict[str, dict] = {
    "bank_statement": {
        "enhance_mode": "standard",
        "layout_profile_hint": "borderless_ledger_bank",
        "plugins": ["bank_statement"],
        "community_tier": CORE_DOMAIN_ROUTE,
        "exports": ["json", "udif", "csv", "parquet", "chunks"],
    },
    "wechat_payment": {
        "enhance_mode": "full",
        "layout_profile_hint": "borderless_ledger_wechat",
        "plugins": ["wechat_payment"],
        "community_tier": CORE_DOMAIN_ROUTE,
        "exports": ["json", "udif", "csv", "chunks"],
        "notes": ["Requires cross-page merge; use full enhance mode"],
    },
    "alipay_payment": {
        "enhance_mode": "full",
        "layout_profile_hint": "borderless_ledger_alipay",
        "plugins": ["alipay_payment"],
        "community_tier": CORE_DOMAIN_ROUTE,
        "exports": ["json", "udif", "csv", "chunks"],
        "notes": ["Requires cross-page merge; use full enhance mode"],
    },
    "vat_invoice": {
        "enhance_mode": "standard",
        "plugins": ["vat_invoice"],
        "community_tier": CORE_DOMAIN_ROUTE,
        "exports": ["json", "udif", "chunks"],
    },
    "business_license": {
        "enhance_mode": "standard",
        "plugins": ["business_license"],
        "community_tier": CORE_DOMAIN_ROUTE,
        "exports": ["json", "udif", "chunks"],
    },
    "credit_report": {
        "enhance_mode": "full",
        "layout_profile_hint": "credit_report_section_dominant",
        "plugins": ["credit_report"],
        "community_tier": CORE_DOMAIN_ROUTE,
        "exports": ["json", "udif", "chunks"],
        "notes": ["Section-driven layout; L6 graph available"],
    },
    "audit_report": {
        "enhance_mode": "standard",
        "plugins": ["audit_report"],
        "community_tier": ENTERPRISE_ONLY_ROUTE,
        "exports": ["json", "udif", "chunks"],
        "notes": ["Community edition emits mirror_only envelope"],
    },
}


def route_document(
    document_type: str,
    *,
    page_count: int = 1,
    confidence: float = 0.0,
) -> DocumentRoute:
    """Map document type to enhance mode and plugin hints (6 premium + generic fallback)."""
    from docmirror.plugins._runtime.community import (
        get_community_premium_domains,
        is_community_premium,
    )

    doc_type = document_type or "generic"
    cfg = _DOMAIN_ROUTES.get(doc_type, {})
    plugins = list(cfg.get("plugins") or [])
    community_tier = cfg.get("community_tier", "")

    if not plugins:
        if is_community_premium(doc_type):
            plugins = [doc_type]
            community_tier = CORE_DOMAIN_ROUTE
        elif doc_type not in ("generic", "unknown", ""):
            plugins = ["generic"]
            community_tier = GENERIC_FALLBACK_ROUTE

    if not community_tier:
        if is_community_premium(doc_type):
            community_tier = CORE_DOMAIN_ROUTE
        elif doc_type in get_community_premium_domains():
            community_tier = CORE_DOMAIN_ROUTE
        elif doc_type not in ("generic", "unknown", ""):
            community_tier = GENERIC_FALLBACK_ROUTE
        else:
            community_tier = "unclassified"

    notes = list(cfg.get("notes") or [])
    if community_tier == GENERIC_FALLBACK_ROUTE:
        notes.append("Community structured output via generic.community_plugin fallback")
    if page_count >= 50:
        notes.append("Large document: set DOCMIRROR_MAX_PAGE_CONCURRENCY conservatively")
    if confidence < 0.5:
        notes.append("Low classify confidence: consider /v1/validate after parse")

    return DocumentRoute(
        document_type=doc_type,
        enhance_mode=cfg.get("enhance_mode", "standard"),
        layout_profile_hint=cfg.get("layout_profile_hint"),
        recommended_plugins=plugins,
        community_tier=community_tier,
        export_formats=list(cfg.get("exports") or ["json", "udif", "chunks"]),
        notes=notes,
    )
