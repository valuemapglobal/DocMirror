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

_plugin_candidate_provider: PluginCandidateProvider | None = None
_profile_hint_provider: ProfileHintProvider | None = None


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


__all__ = [
    "PluginCandidateProvider",
    "ProfileHintProvider",
    "get_plugin_candidate_provider",
    "get_profile_hint_provider",
    "register_plugin_candidate_provider",
    "register_profile_hint_provider",
]
