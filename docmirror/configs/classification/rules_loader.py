# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Classification rules loader — file-sorting categories (design 09 OQ-8).

Loads ``classification_rules.yaml`` which defines file-sort categories used
upstream of business-scene classification. Each category may optionally map to
one or more ``business_scene`` values via ``maps_to_scenes``.

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
from typing import Any

import yaml

from docmirror.configs.paths import CLASSIFICATION_RULES_YAML


@lru_cache(maxsize=1)
def load_classification_rules() -> dict[str, Any]:
    if not CLASSIFICATION_RULES_YAML.is_file():
        return {}
    data = yaml.safe_load(CLASSIFICATION_RULES_YAML.read_text(encoding="utf-8")) or {}
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
