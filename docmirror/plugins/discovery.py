# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Community plugin discovery — 6 premium + 1 generic."""

from __future__ import annotations

import importlib
from typing import Any

from docmirror.plugins.capability import get_community_premium_domains, is_community_premium

_GENERIC_MODULE = "generic_community"
_GENERIC_PLUGIN: Any | None = None


def _load_plugin(module_name: str) -> Any | None:
    try:
        mod = importlib.import_module(f"docmirror.plugins.{module_name}")
    except Exception:
        return None
    return getattr(mod, "plugin", None)


def find_premium_community_plugin(detected_type: str) -> tuple[Any, str]:
    """Match one of the six premium community plugins by domain_name."""
    if not is_community_premium(detected_type):
        return None, ""
    modname = f"{detected_type}_community"
    plugin = _load_plugin(modname)
    if plugin is not None and getattr(plugin, "domain_name", None) == detected_type:
        return plugin, modname
    return None, ""


def get_generic_community_plugin() -> tuple[Any, str]:
    """Return the singleton generic community fallback plugin."""
    global _GENERIC_PLUGIN
    if _GENERIC_PLUGIN is None:
        _GENERIC_PLUGIN = _load_plugin(_GENERIC_MODULE)
    if _GENERIC_PLUGIN is None:
        return None, ""
    return _GENERIC_PLUGIN, _GENERIC_MODULE


def find_community_plugin(detected_type: str) -> tuple[Any, str]:
    """Backward-compatible: premium match only (use runner for generic fallback)."""
    return find_premium_community_plugin(detected_type)


def list_premium_community_modules() -> tuple[str, ...]:
    return tuple(f"{d}_community" for d in get_community_premium_domains())
