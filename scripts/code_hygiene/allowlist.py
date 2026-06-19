# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Load hygiene allowlist for false-positive suppression."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.code_hygiene.config import ALLOWLIST_PATH


def load_allowlist(path: Path | None = None) -> dict[str, Any]:
    path = path or ALLOWLIST_PATH
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def is_allowed(category: str, key: str, allowlist: dict[str, Any]) -> bool:
    entries = allowlist.get(category) or []
    if not isinstance(entries, list):
        return False
    return key in entries or any(key.endswith(e) for e in entries if isinstance(e, str))
