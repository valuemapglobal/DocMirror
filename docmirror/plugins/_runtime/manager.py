# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Plugin manager — registry-driven enable/disable lifecycle for domain plugins.

Exposes CLI-friendly list/status/enable/disable operations over domains registered
in ``registry``. Enable flags persist in ``.plugin_state.json`` beside this package
(via ``state``); disabled domains are skipped by ``community`` discovery and
``runner`` extract.

Pipeline role: administrative layer only — does not run extract. ``list_community``
covers the six premium plus generic fallback; ``list_all`` includes enterprise/finance
plugins when those packages are installed.

Key exports: ``PluginManager``, ``plugin_manager``.

Dependencies: ``community.list_community_plugin_domains``, ``state`` (persistence),
``registry`` (domain metadata and edition list).
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.plugins._runtime.community import list_community_plugin_domains
from docmirror.plugins._runtime.state import is_domain_enabled, set_domain_enabled

logger = logging.getLogger(__name__)


class PluginManager:
    """Manage enable/disable flags for plugins registered in ``registry``."""

    def list_community(self) -> list[dict[str, Any]]:
        """List community 6 premium + 1 generic plugins."""
        return self._build_rows(domain_names=list_community_plugin_domains())

    def list_all(self) -> list[dict[str, Any]]:
        """List every domain registered in ``registry`` (includes enterprise/finance)."""
        from docmirror.plugins._runtime import registry

        registry._ensure_discovered()
        return self._build_rows(domain_names=tuple(sorted(registry.list_domains())))

    def enable(self, plugin_name: str) -> bool:
        return self._set_enabled(plugin_name, True)

    def disable(self, plugin_name: str) -> bool:
        return self._set_enabled(plugin_name, False)

    def status(self, plugin_name: str) -> dict[str, Any]:
        row = self._row_for(plugin_name)
        if row is None:
            raise ValueError(f"Plugin '{plugin_name}' not found")
        return row

    def is_enabled(self, plugin_name: str) -> bool:
        if self._row_for(plugin_name) is None:
            return False
        return is_domain_enabled(plugin_name)

    def _row_for(self, domain_name: str) -> dict[str, Any] | None:
        from docmirror.plugins._runtime import registry

        registry._ensure_discovered()
        editions = registry.list_domains().get(domain_name)
        if not editions:
            return None

        plugin = registry.get(domain_name, "community") or registry.get_first(domain_name)
        if plugin is None:
            return None

        return {
            "name": domain_name,
            "display_name": plugin.display_name,
            "enabled": is_domain_enabled(domain_name),
            "type": "builtin",
            "editions": sorted(editions),
            "version": "unknown",
        }

    def _build_rows(self, domain_names: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
        from docmirror.plugins._runtime import registry

        registry._ensure_discovered()
        rows: list[dict[str, Any]] = []
        for domain_name in domain_names:
            row = self._row_for(domain_name)
            if row is not None:
                rows.append(row)
        return rows

    def _set_enabled(self, plugin_name: str, enabled: bool) -> bool:
        if self._row_for(plugin_name) is None:
            raise ValueError(f"Plugin '{plugin_name}' not found")

        if is_domain_enabled(plugin_name) == enabled:
            state = "enabled" if enabled else "disabled"
            logger.info("[PluginManager] Plugin '%s' is already %s", plugin_name, state)
            return True

        set_domain_enabled(plugin_name, enabled)
        state = "enabled" if enabled else "disabled"
        logger.info("[PluginManager] Plugin '%s' %s", plugin_name, state)
        return True


plugin_manager = PluginManager()

__all__ = ["PluginManager", "plugin_manager"]
