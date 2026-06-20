# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Core extension points for non-Core integrations.

Core owns the Mirror. Edition builders, plugin matchers, and plugin profile
hints are optional consumers/providers around that Mirror, so Core talks to
small callable contracts instead of importing plugin or server packages.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from docmirror.models.entities.hypothesis import ParseHypothesis

PluginCandidateProvider = Callable[[str, Any | None], list[ParseHypothesis]]
ProfileHintProvider = Callable[[str], str | None]
EditionProjectionBuilder = Callable[..., dict[str, dict[str, Any] | None]]
SectionResolver = Callable[[Any, dict[str, dict[str, Any]] | None], list[dict[str, Any]]]

_plugin_candidate_provider: PluginCandidateProvider | None = None
_profile_hint_provider: ProfileHintProvider | None = None
_edition_projection_builder: EditionProjectionBuilder | None = None
_section_resolver: SectionResolver | None = None


def register_plugin_candidate_provider(provider: PluginCandidateProvider | None) -> None:
    global _plugin_candidate_provider
    _plugin_candidate_provider = provider


def get_plugin_candidate_provider() -> PluginCandidateProvider | None:
    return _plugin_candidate_provider


def register_profile_hint_provider(provider: ProfileHintProvider | None) -> None:
    global _profile_hint_provider
    _profile_hint_provider = provider


def get_profile_hint_provider() -> ProfileHintProvider | None:
    return _profile_hint_provider


def register_edition_projection_builder(provider: EditionProjectionBuilder | None) -> None:
    global _edition_projection_builder
    _edition_projection_builder = provider


def get_edition_projection_builder() -> EditionProjectionBuilder | None:
    return _edition_projection_builder


def register_section_resolver(provider: SectionResolver | None) -> None:
    global _section_resolver
    _section_resolver = provider


def resolve_sections(parse_result: Any, editions: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if _section_resolver is not None:
        return _section_resolver(parse_result, editions)
    for name in ("enterprise", "finance", "community"):
        payload = (editions or {}).get(name)
        if not isinstance(payload, dict):
            continue
        sections = (payload.get("data") or {}).get("sections")
        if sections:
            return [_as_section_dict(sec) for sec in sections]
    core_sections = getattr(parse_result, "sections", None) or []
    return [_as_section_dict(sec) for sec in core_sections]


def _as_section_dict(sec: Any) -> dict[str, Any]:
    if isinstance(sec, dict):
        return dict(sec)
    return {
        "id": getattr(sec, "id", None),
        "title": getattr(sec, "title", None) or getattr(sec, "name", None),
        "name": getattr(sec, "name", None) or getattr(sec, "title", None),
        "page_start": getattr(sec, "page_start", 1),
    }


__all__ = [
    "EditionProjectionBuilder",
    "PluginCandidateProvider",
    "ProfileHintProvider",
    "SectionResolver",
    "get_edition_projection_builder",
    "get_plugin_candidate_provider",
    "get_profile_hint_provider",
    "register_edition_projection_builder",
    "register_plugin_candidate_provider",
    "register_profile_hint_provider",
    "register_section_resolver",
    "resolve_sections",
]
