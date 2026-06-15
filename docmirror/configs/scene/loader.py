# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Scene keyword loader — single source for ``scene_keywords.yaml``.

Loads and caches the classification keyword corpus shared by the EvidenceEngine,
scene detector middleware, domain plugins, and DTI validators. The YAML structure
is ``scene_keywords: {scene_name: {include: [...], exclude: [...]}}``.

Caching::

    Module-level mtime cache avoids re-parsing on every lookup. Call
    ``invalidate_scene_cache()`` in tests or after YAML edits.

Derived views::

    ``get_scene_includes`` / ``get_scene_excludes`` filter by minimum keyword length.
    ``get_plugin_scene_keywords`` produces immutable tuples for plugin registration.
    ``compute_keyword_uniqueness`` returns inverse document-frequency weights used
    as softmax priors in evidence scoring.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

from docmirror.configs.paths import SCENE_KEYWORDS_YAML

logger = logging.getLogger(__name__)

_cache_raw: dict[str, Any] | None = None
_cache_mtime: float = 0.0
_cache_includes: dict[str, list[str]] | None = None
_cache_excludes: dict[str, list[str]] | None = None
_cache_plugin_includes: dict[str, tuple[str, ...]] | None = None


def invalidate_scene_cache() -> None:
    """Clear cached scene keywords (tests / hot-reload)."""
    global _cache_raw, _cache_mtime, _cache_includes, _cache_excludes, _cache_plugin_includes
    _cache_raw = None
    _cache_mtime = 0.0
    _cache_includes = None
    _cache_excludes = None
    _cache_plugin_includes = None


def _load_raw() -> dict[str, Any]:
    global _cache_raw, _cache_mtime
    if not SCENE_KEYWORDS_YAML.is_file():
        _cache_raw = {}
        _cache_mtime = 0.0
        return _cache_raw

    mtime = SCENE_KEYWORDS_YAML.stat().st_mtime
    if _cache_raw is not None and mtime == _cache_mtime:
        return _cache_raw

    try:
        with open(SCENE_KEYWORDS_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        raw = data.get("scene_keywords", {}) if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            raw = {}
        _cache_raw = raw
        _cache_mtime = mtime
        _cache_includes = None
        _cache_excludes = None
        _cache_plugin_includes = None
        logger.debug("[SceneLoader] Loaded %d scenes from %s", len(raw), SCENE_KEYWORDS_YAML)
    except Exception as exc:
        logger.error("[SceneLoader] Failed to load %s: %s", SCENE_KEYWORDS_YAML, exc)
        _cache_raw = {}
        _cache_mtime = mtime
    return _cache_raw


def get_scene_specs() -> dict[str, dict[str, list[str]]]:
    """Raw per-scene specs: ``{scene: {include: [...], exclude: [...]}}``."""
    raw = _load_raw()
    specs: dict[str, dict[str, list[str]]] = {}
    for scene, content in raw.items():
        if isinstance(content, dict):
            specs[scene] = {
                "include": [kw for kw in content.get("include", []) if isinstance(kw, str)],
                "exclude": [kw for kw in content.get("exclude", []) if isinstance(kw, str)],
            }
        elif isinstance(content, list):
            specs[scene] = {
                "include": [kw for kw in content if isinstance(kw, str)],
                "exclude": [],
            }
    return specs


def get_scene_includes(*, min_len: int = 2) -> dict[str, list[str]]:
    """Include keywords per scene (EvidenceEngine format)."""
    global _cache_includes
    if _cache_includes is not None:
        return _cache_includes
    includes: dict[str, list[str]] = {}
    for scene, spec in get_scene_specs().items():
        kws = [kw for kw in spec.get("include", []) if len(kw) >= min_len]
        if kws:
            includes[scene] = kws
    _cache_includes = includes
    return includes


def get_scene_excludes(*, min_len: int = 2) -> dict[str, list[str]]:
    """Exclude keywords per scene."""
    global _cache_excludes
    if _cache_excludes is not None:
        return _cache_excludes
    excludes: dict[str, list[str]] = {}
    for scene, spec in get_scene_specs().items():
        kws = [kw for kw in spec.get("exclude", []) if len(kw) >= min_len]
        if kws:
            excludes[scene] = kws
    _cache_excludes = excludes
    return excludes


def get_plugin_scene_keywords() -> dict[str, tuple[str, ...]]:
    """Include-only tuples for DomainPlugin.scene_keywords."""
    global _cache_plugin_includes
    if _cache_plugin_includes is not None:
        return _cache_plugin_includes
    out: dict[str, tuple[str, ...]] = {}
    for scene, spec in get_scene_specs().items():
        kws = tuple(kw for kw in spec.get("include", []) if isinstance(kw, str))
        if kws:
            out[scene] = kws
    _cache_plugin_includes = out
    return out


def compute_keyword_uniqueness() -> dict[str, float]:
    """Keyword rarity weights across scenes (EvidenceEngine softmax prior)."""
    includes = get_scene_includes(min_len=1)
    counts: dict[str, int] = {}
    for kws in includes.values():
        for kw in kws:
            counts[kw] = counts.get(kw, 0) + 1
    return {kw: 1.0 / max(cnt, 1) for kw, cnt in counts.items()}
