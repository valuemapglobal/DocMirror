# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load plugin_capability.yaml — community vs mirror_only document types."""

from __future__ import annotations

from functools import lru_cache

import yaml

from docmirror.configs.paths import PLUGIN_CAPABILITY_YAML
from docmirror.plugins.discovery import find_community_plugin


@lru_cache(maxsize=1)
def load_plugin_capability() -> dict:
    if not PLUGIN_CAPABILITY_YAML.is_file():
        return {"enterprise_only": []}
    with open(PLUGIN_CAPABILITY_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def is_enterprise_only(document_type: str) -> bool:
    cfg = load_plugin_capability()
    return document_type in set(cfg.get("enterprise_only") or [])


def should_mirror_only(document_type: str, edition: str = "community") -> bool:
    """True when classified but no community plugin should run (honest empty state)."""
    if edition != "community":
        return False
    if not document_type or document_type in ("unknown", "generic", ""):
        return False
    if is_enterprise_only(document_type):
        return True
    plugin, _ = find_community_plugin(document_type)
    return plugin is None
