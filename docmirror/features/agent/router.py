# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Document routing hints for Agent workflows (L11 / P7)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentRoute(BaseModel):
    """Recommended parse path — does not execute parsing."""

    document_type: str = "generic"
    enhance_mode: str = "standard"
    layout_profile_hint: str | None = None
    recommended_plugins: list[str] = Field(default_factory=list)
    export_formats: list[str] = Field(default_factory=lambda: ["json", "udif"])
    notes: list[str] = Field(default_factory=list)


_DOMAIN_ROUTES: dict[str, dict] = {
    "wechat_payment": {
        "enhance_mode": "full",
        "layout_profile_hint": "borderless_ledger_wechat",
        "plugins": ["wechat_payment"],
        "exports": ["json", "udif", "csv", "chunks"],
        "notes": ["Requires cross-page merge; use full enhance mode"],
    },
    "bank_statement": {
        "enhance_mode": "standard",
        "layout_profile_hint": "borderless_ledger_bank",
        "plugins": ["bank_statement"],
        "exports": ["json", "udif", "csv", "parquet", "chunks"],
    },
    "credit_report": {
        "enhance_mode": "full",
        "layout_profile_hint": "credit_report_section_dominant",
        "plugins": ["credit_report"],
        "exports": ["json", "udif", "chunks"],
        "notes": ["Section-driven layout; L6 graph available"],
    },
    "business_license": {
        "enhance_mode": "standard",
        "plugins": ["business_license"],
        "exports": ["json", "udif", "chunks"],
    },
    "audit_report": {
        "enhance_mode": "standard",
        "plugins": ["audit_report"],
        "exports": ["json", "udif", "chunks"],
    },
}


def route_document(
    document_type: str,
    *,
    page_count: int = 1,
    confidence: float = 0.0,
) -> DocumentRoute:
    """Map document type to enhance mode and plugin hints."""
    doc_type = document_type or "generic"
    cfg = _DOMAIN_ROUTES.get(doc_type, {})
    plugins = list(cfg.get("plugins") or [])
    if doc_type not in _DOMAIN_ROUTES and doc_type not in ("generic", "unknown", ""):
        plugins = [doc_type]

    notes = list(cfg.get("notes") or [])
    if page_count >= 50:
        notes.append("Large document: set DOCMIRROR_MAX_PAGE_CONCURRENCY conservatively")
    if confidence < 0.5:
        notes.append("Low classify confidence: consider /v1/validate after parse")

    return DocumentRoute(
        document_type=doc_type,
        enhance_mode=cfg.get("enhance_mode", "standard"),
        layout_profile_hint=cfg.get("layout_profile_hint"),
        recommended_plugins=plugins,
        export_formats=list(cfg.get("exports") or ["json", "udif", "chunks"]),
        notes=notes,
    )
