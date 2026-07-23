# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
DTI field-schema helper — expected entity labels per business scene.

Replaces the raw ``DocumentType`` enum with field schemas loaded from resources
declared by plugin manifests. Each ``business_scene`` may define expected field
label mappings used by validators and plugin scaffolding.

Functions::

    get_field_schema(business_scene)   Return expected field labels (may be empty)
    list_scenes_with_schemas()         Sorted list of scenes with defined schemas

See design 09 §4.3 for Document Type Identity (DTI) integration.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from pathlib import PurePosixPath

import yaml


@lru_cache(maxsize=1)
def _load_field_schemas() -> dict[str, dict[str, str]]:
    schemas: dict[str, dict[str, str]] = {}
    plugin_root = files("docmirror").joinpath("plugins")
    for plugin_dir in sorted(plugin_root.iterdir(), key=lambda item: item.name):
        manifest_path = plugin_dir.joinpath("plugin.yaml")
        if not plugin_dir.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            relative_text = str(((manifest.get("resources") or {}).get("field_schema")) or "").strip()
            relative_path = PurePosixPath(relative_text)
            if not relative_text or relative_path.is_absolute() or ".." in relative_path.parts:
                continue
            resource_path = plugin_dir.joinpath(*relative_path.parts)
            data = yaml.safe_load(resource_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        plugin_schemas = data.get("field_schemas") if isinstance(data, dict) else None
        if not isinstance(plugin_schemas, dict):
            continue
        schemas.update({str(key): dict(value) for key, value in plugin_schemas.items() if isinstance(value, dict)})
    return schemas


def get_field_schema(business_scene: str) -> dict[str, str]:
    """Return expected field labels for a business_scene (may be empty)."""
    return dict(_load_field_schemas().get(business_scene, {}))


def list_scenes_with_schemas() -> list[str]:
    return sorted(_load_field_schemas().keys())
