# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapters that expose plugin facts through Core extension-point contracts."""

from __future__ import annotations

import uuid
from typing import Any

from docmirror.models.entities.hypothesis import ParseHypothesis


def _hyp(scene: str, confidence: float, method: str) -> ParseHypothesis:
    return ParseHypothesis(
        id=f"doctype_{scene}_{uuid.uuid4().hex[:6]}",
        kind="document_type",
        payload={"document_type": scene},
        confidence=confidence,
        method=method,
        evidence_ids=[],
    )


def collect_plugin_candidates(text: str, parse_result: Any | None = None) -> list[ParseHypothesis]:
    from docmirror.plugins._runtime import registry

    candidates: list[ParseHypothesis] = []
    ctx = {"text": text, "parse_result": parse_result}
    for domain_name in registry.list_plugins():
        plugin = registry.get(domain_name)
        if plugin is None:
            continue
        try:
            if hasattr(plugin, "match") and plugin.match(ctx):
                candidates.append(_hyp(plugin.domain_name, 0.82, "plugin_match"))
        except Exception:
            continue
    return candidates


def resolve_profile_hint(scene_hint: str) -> str | None:
    from docmirror.plugins._runtime import registry

    plugin = registry.get(scene_hint)
    if not plugin:
        return None
    hints = plugin.get_extraction_hints() or {} if hasattr(plugin, "get_extraction_hints") else {}
    lp_id = hints.get("layout_profile")
    return str(lp_id) if lp_id else None


def register_core_extensions() -> None:
    from docmirror.framework.extension_points import (
        register_plugin_candidate_provider,
        register_profile_hint_provider,
    )

    register_plugin_candidate_provider(collect_plugin_candidates)
    register_profile_hint_provider(resolve_profile_hint)
    _register_parse_time_structure_extensions()


def _register_parse_time_structure_extensions() -> None:
    # Discovery imports provider implementations, which register optional
    # evidence-only structure extensions through the existing Core contracts.
    # This runtime adapter must never name a concrete business plugin.
    from docmirror.plugins._runtime.plugin_registry import registry

    registry.list_providers()


__all__ = ["collect_plugin_candidates", "register_core_extensions", "resolve_profile_hint"]
