# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
DTI field-schema helper — expected entity labels per business scene.

Replaces the legacy ``DocumentType`` enum with YAML-driven field schemas loaded
from ``document_field_schemas.yaml``. Each ``business_scene`` may define expected
field label mappings used by validators and plugin scaffolding.

Functions::

    get_field_schema(business_scene)   Return expected field labels (may be empty)
    list_scenes_with_schemas()         Sorted list of scenes with defined schemas

See design 09 §4.3 for Document Type Identity (DTI) integration.
"""

from __future__ import annotations

from functools import lru_cache

import yaml

from docmirror.configs.paths import YAML_DIR

_FIELD_SCHEMAS_YAML = YAML_DIR / "document_field_schemas.yaml"


@lru_cache(maxsize=1)
def _load_field_schemas() -> dict[str, dict[str, str]]:
    if not _FIELD_SCHEMAS_YAML.is_file():
        return {}
    data = yaml.safe_load(_FIELD_SCHEMAS_YAML.read_text(encoding="utf-8")) or {}
    schemas = data.get("field_schemas") or data
    if not isinstance(schemas, dict):
        return {}
    return {str(k): dict(v) for k, v in schemas.items() if isinstance(v, dict)}


def get_field_schema(business_scene: str) -> dict[str, str]:
    """Return expected field labels for a business_scene (may be empty)."""
    return dict(_load_field_schemas().get(business_scene, {}))


def list_scenes_with_schemas() -> list[str]:
    return sorted(_load_field_schemas().keys())
