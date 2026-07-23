# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Post-seal plugin runtime facade without import-time discovery.

External providers import stable contracts from :mod:`docmirror.plugin_api`.
The bundled canonical domain implementations remain physically colocated in
this package, but they are fixed Core capabilities and never enter this runtime
registry.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from docmirror.plugins._runtime.plugin_registry import PluginRegistry, registry


def __getattr__(name: str) -> Any:
    if name == "license_manager":
        return getattr(import_module("docmirror.plugins._runtime.licensing.online"), "license_manager")
    if name == "plugin_manager":
        return getattr(import_module("docmirror.plugins._runtime.manager"), "plugin_manager")
    if name in {"hooks", "discovery"}:
        return import_module(f"docmirror.plugins._runtime.{name}")
    raise AttributeError(name)


__all__ = [
    "PluginRegistry",
    "registry",
    "license_manager",
    "plugin_manager",
    "hooks",
    "discovery",
]
