# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entry-point based plugin discovery — pluggy integration.

This module provides pluggy-based discovery of third-party DocMirror plugins
distributed as PyPI packages. Plugins register themselves via the
``docmirror.plugins`` entry point in their ``pyproject.toml``::

    [project.entry-points."docmirror.plugins"]
    bank_statement = "docmirror_plugin_bank_statement.plugin"

Usage::

    from docmirror.plugins._runtime.discovery import discover_plugins, get_plugin_manager

    pm = get_plugin_manager()
    manifests = pm.hook.docmirror_plugin_manifest()
    for manifest in manifests:
        if manifest:
            print(manifest["name"])

Design (GA1.0-EC-01 §Component 5):
    - Uses pluggy for hook dispatch (standard Python plugin framework)
    - Discovers via ``importlib.metadata.entry_points`` (Python 3.11+)
    - Falls back silently if no plugins are installed (zero deps for base install)
    - The ``docmirror.plugins`` entry point should point to a module that
      defines at least one ``@hookimpl``-decorated function or method.
"""

from __future__ import annotations

import logging
from typing import Any

import pluggy

from docmirror.plugin_api import PluginProvider
from docmirror.plugins._runtime import hooks

logger = logging.getLogger(__name__)

# ── Global plugin manager (lazy singleton) ──

_plugin_manager: Any = None
_discovery_done: bool = False


def get_plugin_manager() -> pluggy.PluginManager:
    """Get or create the global DocMirror plugin manager.

    The manager auto-discovers plugins on first access via entry points.
    Returns a working ``PluginManager`` even if no plugins are installed.
    """
    global _plugin_manager, _discovery_done
    if _plugin_manager is None:
        _plugin_manager = pluggy.PluginManager(hooks.PROJECT_NAME)
        _plugin_manager.add_hookspecs(hooks)

    if not _discovery_done:
        _discover_entry_point_plugins(_plugin_manager)
        _discovery_done = True

    return _plugin_manager


def discover_plugins() -> pluggy.PluginManager:
    """Convenience alias for ``get_plugin_manager()``."""
    return get_plugin_manager()


def load_plugin_providers() -> list[PluginProvider]:
    """Return validated runtime providers discovered via entry points."""
    providers: list[PluginProvider] = []
    raw_items = get_plugin_manager().hook.docmirror_plugin_provider()
    for raw in raw_items:
        if raw is None:
            continue
        candidates = raw if isinstance(raw, (list, tuple)) else (raw,)
        for candidate in candidates:
            providers.append(PluginProvider.model_validate(candidate))
    return providers


def _discover_entry_point_plugins(pm: pluggy.PluginManager) -> None:
    """Discover and register plugins via the ``docmirror.plugins`` entry point.

    Each entry point should resolve to a module that contains at least one
    ``@hookimpl``-decorated function or class.
    """
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="docmirror.plugins")
        registered = 0

        for ep in eps:
            try:
                plugin_module = ep.load()
                pm.register(plugin_module, name=ep.name)
                registered += 1
                logger.info(
                    "[PluginDiscovery] Registered plugin %r (name=%r, module=%s)",
                    ep.value,
                    ep.name,
                    getattr(plugin_module, "__name__", str(type(plugin_module))),
                )
            except Exception as e:
                logger.warning(
                    "[PluginDiscovery] Failed to load plugin %r: %s",
                    ep.value,
                    e,
                )

        if registered == 0:
            logger.debug("[PluginDiscovery] No third-party DocMirror plugins found via entry points")

    except Exception as e:
        logger.debug("[PluginDiscovery] Entry-point discovery failed: %s", e)


def reset_discovery() -> None:
    """Reset the discovery cache. Useful in tests."""
    global _plugin_manager, _discovery_done
    _plugin_manager = None
    _discovery_done = False


__all__ = [
    "get_plugin_manager",
    "discover_plugins",
    "load_plugin_providers",
    "reset_discovery",
]
