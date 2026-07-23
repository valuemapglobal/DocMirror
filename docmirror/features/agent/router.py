# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""
Document routing hints for agent and automation workflows (L11 / P7).

Derives recommended parse parameters — document type, enhancement mode, layout
profile hints — from an existing ``ParseResult`` or lightweight metadata.
Does not execute parsing; downstream agents use ``DocumentRoute`` to choose
plugins, middleware profiles, or re-parse options.
"""

from __future__ import annotations

from importlib.resources import files

import yaml
from pydantic import BaseModel, Field

from docmirror.configs.ga_readiness import (
    CORE_DOMAIN_ROUTE,
    GENERIC_FALLBACK_ROUTE,
)


class DocumentRoute(BaseModel):
    """Recommended parse path — does not execute parsing."""

    document_type: str = "generic"
    enhance_mode: str = "standard"
    layout_profile_hint: str | None = None
    recommended_plugins: list[str] = Field(default_factory=list)
    community_tier: str = GENERIC_FALLBACK_ROUTE
    notes: list[str] = Field(default_factory=list)


def _manifest_route(document_type: str) -> dict:
    from docmirror.plugins._runtime.plugin_registry import registry

    manifests = registry.list_provider_manifests()
    for manifest in manifests:
        provider = manifest.get("provider") or {}
        if provider.get("domain_name") == document_type:
            return dict(manifest.get("routing") or {})

    generic_manifest = next(
        (manifest for manifest in manifests if (manifest.get("provider") or {}).get("domain_name") == "generic"),
        None,
    )
    if not generic_manifest:
        return {}
    relative_path = str(((generic_manifest.get("resources") or {}).get("route_overrides")) or "")
    if not relative_path:
        return {}
    try:
        resource = files("docmirror").joinpath("plugins").joinpath("generic")
        for part in relative_path.split("/"):
            resource = resource.joinpath(part)
        payload = yaml.safe_load(resource.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    routes = payload.get("routes") if isinstance(payload, dict) else None
    return dict(routes.get(document_type) or {}) if isinstance(routes, dict) else {}


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
    cfg = _manifest_route(doc_type)
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

    from docmirror.layout.scene.scene_resolver import scene_to_layout_profile_id

    return DocumentRoute(
        document_type=doc_type,
        enhance_mode=cfg.get("enhance_mode", "standard"),
        layout_profile_hint=scene_to_layout_profile_id(doc_type),
        recommended_plugins=plugins,
        community_tier=community_tier,
        notes=notes,
    )
