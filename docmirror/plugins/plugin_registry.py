# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Domain plugin registry — ``DomainPlugin`` ABC and ``PluginRegistry`` singleton.

Defines the abstract contract every domain plugin implements (``domain_name``,
``display_name``, optional ``extract`` / ``extract_from_mirror`` /
``build_domain_data``) and maintains a keyed registry of
``(domain_name, edition)`` instances. On first access, auto-discovers community
plugins via ``community.list_community_plugin_domains`` and optionally loads
``docmirror_enterprise`` / ``docmirror_finance`` extension packages.

Pipeline role: ``runner`` looks up edition-specific plugins through ``registry.get``;
``manager`` lists registered domains for CLI enable/disable; scene keywords and
``build_domain_data`` support classification and KV fallback paths.

Key exports: ``DomainPlugin``, ``PluginRegistry``, ``registry``.

Dependencies: ``community`` (builtin discovery), ``configs.scene.loader`` (scene
keywords), optional ``docmirror_enterprise`` / ``docmirror_finance`` packages.
"""

from __future__ import annotations

import importlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from docmirror.configs.scene.loader import get_plugin_scene_keywords

logger = logging.getLogger(__name__)


class DomainPlugin(ABC):
    """Abstract base class for domain plugins."""

    @property
    @abstractmethod
    def domain_name(self) -> str:
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        ...

    @property
    def edition(self) -> str:
        return "community"

    @property
    def requires_license(self) -> bool:
        return False

    @property
    def scene_keywords(self) -> Sequence[str]:
        return get_plugin_scene_keywords().get(self.domain_name, ())

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return ()

    def build_domain_data(
        self,
        _metadata: dict[str, Any],
        _entities: dict[str, Any],
    ) -> dict[str, Any] | None:
        return None

    def get_middleware_config(self) -> dict[str, Any]:
        return {}


class PluginRegistry:
    """Central registry for domain plugins."""

    def __init__(self):
        self._plugins: dict[tuple[str, str], DomainPlugin] = {}
        self._discovered = False

    def register(self, plugin: DomainPlugin, *, override: bool = False) -> None:
        name = plugin.domain_name
        edition = plugin.edition
        key = (name, edition)
        if key in self._plugins and not override:
            logger.warning(
                "[PluginRegistry] Plugin '%s' edition '%s' already registered; use override=True to replace",
                name,
                edition,
            )
            return
        self._plugins[key] = plugin
        logger.debug("[PluginRegistry] Registered plugin: %s (%s) [%s]", name, plugin.display_name, edition)

    def get(self, domain_name: str, edition: str = "community") -> DomainPlugin | None:
        self._ensure_discovered()
        return self._plugins.get((domain_name, edition))

    def get_first(self, domain_name: str) -> DomainPlugin | None:
        self._ensure_discovered()
        for ed in ("finance", "enterprise", "community"):
            p = self._plugins.get((domain_name, ed))
            if p:
                return p
        return None

    def list_by_edition(self, edition: str) -> list[DomainPlugin]:
        self._ensure_discovered()
        return [p for (_, ed), p in self._plugins.items() if ed == edition]

    def list_domains(self) -> dict[str, list[str]]:
        self._ensure_discovered()
        domains: dict[str, list[str]] = {}
        for (name, ed), _p in self._plugins.items():
            domains.setdefault(name, []).append(ed)
        return domains

    def list_plugins(self) -> dict[str, str]:
        self._ensure_discovered()
        result = {}
        for (name, _ed), p in sorted(self._plugins.items()):
            if name not in result:
                result[name] = p.display_name
        return result

    def get_all_scene_keywords(self) -> dict[str, Sequence[str]]:
        self._ensure_discovered()
        result: dict[str, Sequence[str]] = {}
        for (name, _ed), p in sorted(self._plugins.items()):
            if p.scene_keywords and name not in result:
                result[name] = p.scene_keywords
        return result

    def build_domain_data(
        self,
        domain_name: str,
        metadata: dict[str, Any],
        entities: dict[str, Any],
    ) -> Any | None:
        plugin = self.get_first(domain_name)
        if plugin is None:
            return None
        return plugin.build_domain_data(metadata, entities)

    def _ensure_discovered(self) -> None:
        if self._discovered:
            return
        self._discovered = True
        self._discover_builtin_plugins()

    def _discover_builtin_plugins(self) -> None:
        try:
            from docmirror.plugins.community import community_plugin_module, list_community_plugin_domains

            for domain in list_community_plugin_domains():
                modpath = community_plugin_module(domain)
                try:
                    mod = importlib.import_module(f"docmirror.plugins.{modpath}")
                    if hasattr(mod, "plugin"):
                        self.register(mod.plugin)
                    elif hasattr(mod, "Plugin"):
                        self.register(mod.Plugin())
                except Exception as e:
                    logger.warning(
                        "[PluginRegistry] Failed to load community plugin docmirror.plugins.%s: %s",
                        modpath,
                        e,
                    )

            try:
                from docmirror_enterprise import enable as enterprise_enable

                enterprise_enable.register_enterprise_plugins(self)
                logger.info("[PluginRegistry] Enterprise plugins discovered from docmirror-enterprise")
            except ImportError:
                logger.debug("[PluginRegistry] No docmirror-enterprise package found; community edition only")
            except Exception as e:
                logger.warning("[PluginRegistry] Error discovering enterprise plugins: %s", e)

            try:
                from docmirror_finance import enable as finance_enable

                finance_enable.register_finance_plugins(self)
                logger.info("[PluginRegistry] Finance plugins discovered from docmirror-finance")
            except ImportError:
                logger.debug("[PluginRegistry] No docmirror-finance package found; baseline edition only")
            except Exception as e:
                logger.warning("[PluginRegistry] Error discovering finance plugins: %s", e)
        except ImportError:
            logger.debug("[PluginRegistry] No docmirror.plugins package found")


registry = PluginRegistry()

__all__ = ["DomainPlugin", "PluginRegistry", "registry"]
