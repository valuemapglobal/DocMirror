# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-domain enable/disable state for registered plugins (``.plugin_state.json``)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).parent / ".plugin_state.json"


def _load_state() -> dict[str, Any]:
    if not _STATE_FILE.exists():
        return {}
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as exc:
        logger.warning("[PluginState] Failed to load %s: %s", _STATE_FILE, exc)
        return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as exc:
        logger.error("[PluginState] Failed to save %s: %s", _STATE_FILE, exc)


def is_domain_enabled(domain_name: str) -> bool:
    """Return True when domain is enabled (default enabled when absent from state)."""
    entry = _load_state().get(domain_name)
    if entry is None:
        return True
    return bool(entry.get("enabled", True))


def set_domain_enabled(domain_name: str, enabled: bool) -> None:
    state = _load_state()
    state[domain_name] = {"enabled": enabled}
    _save_state(state)
