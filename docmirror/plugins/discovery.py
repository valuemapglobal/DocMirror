# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Community plugin discovery by document_type."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any


def find_community_plugin(detected_type: str) -> tuple[Any, str]:
    import docmirror.plugins as _plugins_pkg

    for _, modname, ispkg in pkgutil.iter_modules(_plugins_pkg.__path__):
        if ispkg or not modname.endswith("_community") or modname.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"docmirror.plugins.{modname}")
        except Exception:
            continue
        if not hasattr(mod, "plugin"):
            continue
        plugin = mod.plugin
        if detected_type == plugin.domain_name:
            return plugin, modname
    return None, ""
