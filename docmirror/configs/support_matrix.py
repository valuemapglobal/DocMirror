# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Support Matrix loader.

The Format Capability Registry says whether DocMirror can route a format. The
Support Matrix says what product support level that routed format can honestly
claim at GA time.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from docmirror.configs.paths import SUPPORT_MATRIX_YAML


@lru_cache(maxsize=1)
def load_support_matrix() -> dict[str, Any]:
    if not SUPPORT_MATRIX_YAML.is_file():
        return {"version": 1, "formats": {}}
    with open(SUPPORT_MATRIX_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("version", 1)
    data.setdefault("formats", {})
    return data


def support_for_capability(capability_id: str) -> dict[str, Any]:
    formats = load_support_matrix().get("formats") or {}
    item = formats.get(capability_id) or {}
    return dict(item) if isinstance(item, dict) else {}


def compact_support_info(capability_id: str) -> dict[str, Any]:
    item = support_for_capability(capability_id)
    return {
        "capability_id": capability_id,
        "ga_status": item.get("ga_status", "unknown"),
        "user_label": item.get("user_label", capability_id),
        "requires_converter": item.get("requires_converter"),
        "outputs": item.get("outputs") or {},
        "limitations": item.get("limitations") or [],
    }
