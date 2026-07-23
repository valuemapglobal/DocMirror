# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Classification rules loader — file-sorting categories (design 09 OQ-8).

Loads the ``classification_rules`` resource declared by the generic plugin.
The resource defines file-sort categories used upstream of business-scene
classification. Each category may optionally map to one or more
``business_scene`` values via ``maps_to_scenes``.

Functions::

    load_classification_rules()     LRU-cached ``categories`` dict from YAML
    get_maps_to_scenes()          Scenes mapped from a single category ID
    resolve_scenes_for_category() Same as above; empty list if unmapped (valid)
    categories_with_scene_maps()  All categories that define scene mappings

The category → scene bridge is optional and does not require a 1:1 mapping;
unmapped categories are valid and return empty scene lists.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any

import yaml

try:
    from importlib.resources.abc import Traversable
except ImportError:  # Python 3.10
    from importlib.abc import Traversable


@lru_cache(maxsize=1)
def get_classification_rules_resource() -> Traversable | None:
    """Resolve the generic plugin's declared classification-rules resource."""
    plugin_dir = files("docmirror.plugins.generic")
    manifest = yaml.safe_load(plugin_dir.joinpath("plugin.yaml").read_text(encoding="utf-8")) or {}
    relative_text = str(((manifest.get("resources") or {}).get("classification_rules")) or "").strip()
    relative = PurePosixPath(relative_text)
    if not relative_text or relative.is_absolute() or ".." in relative.parts:
        return None
    resource = plugin_dir.joinpath(*relative.parts)
    return resource if resource.is_file() else None


@lru_cache(maxsize=1)
def load_classification_rules() -> dict[str, Any]:
    resource = get_classification_rules_resource()
    if resource is None:
        return {}
    data = yaml.safe_load(resource.read_text(encoding="utf-8")) or {}
    return data.get("categories") or {}


def get_maps_to_scenes(category_id: str) -> list[str]:
    """Optional bridge from file-sort category → business_scene list."""
    cat = load_classification_rules().get(category_id) or {}
    raw = cat.get("maps_to_scenes") or []
    return [str(s) for s in raw if s]


def resolve_scenes_for_category(category_id: str) -> list[str]:
    """Return mapped business_scenes; empty if unmapped (valid — no 1:1 required)."""
    return get_maps_to_scenes(category_id)


def categories_with_scene_maps() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for cid, cat in load_classification_rules().items():
        scenes = cat.get("maps_to_scenes") if isinstance(cat, dict) else None
        if scenes:
            out[cid] = [str(s) for s in scenes]
    return out
