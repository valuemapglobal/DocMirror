# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Domain Plugin Interface
=======================

Extensible plugin system for domain-specific document processing.
Each domain (bank_statement, invoice, contract, etc.) registers as a plugin
that provides:

1. Scene matching rules (keywords, patterns)
2. Entity extraction logic (key fields to extract)
3. Domain data construction (structured output model)

Built-in plugins are auto-discovered from ``docmirror.plugins.*``.
Third-party plugins can register via the ``docmirror.plugins``
entry point group.

Usage::

    from docmirror.plugins import registry

    # Get all registered plugins
    registry.list_plugins()

    # Get plugin for a specific domain
    plugin = registry.get("bank_statement")
    domain_data = plugin.build_domain_data(metadata, entities)
"""

from __future__ import annotations
from pathlib import Path

import importlib
import logging
import pkgutil
import yaml
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class DomainPlugin(ABC):
    """
    Abstract base class for domain plugins.

    Each plugin handles one document domain (e.g., bank_statement, invoice).
    Subclass this and register via the plugin registry to add new domains.
    """

    @property
    @abstractmethod
    def domain_name(self) -> str:
        """Unique domain identifier (e.g., 'bank_statement', 'invoice')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g., 'Bank Statement')."""
        ...

    @property
    def edition(self) -> str:
        """Plugin edition: 'community' (built-in, no license needed) or 'enterprise' (requires license)."""
        return "community"

    @property
    def requires_license(self) -> bool:
        """Whether this plugin requires a valid enterprise license."""
        return False

    @property
    def scene_keywords(self) -> Sequence[str]:
        """
        Keywords that indicate this domain when found in document text.
        Loaded from ``configs/yaml/scene_keywords.yaml`` via scene loader.
        Used by EvidenceEngine for automatic classification and by plugins
        for output metadata (matched_keywords field).
        Returns empty sequence if the domain is not in the config.
        """
        return get_plugin_scene_keywords().get(self.domain_name, ())

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        """
        Identity field definitions: (display_name, candidate_keys...).
        Used by domain registry for entity extraction.
        Returns empty sequence if not applicable.
        """
        return ()

    def build_domain_data(
        self,
        metadata: dict[str, Any],
        entities: dict[str, Any],
    ) -> Any | None:
        """
        Build domain-specific data model from extracted metadata and entities.

        Returns a domain data object (e.g., BankStatementData) or None if
        insufficient data is available.

        Default implementation returns None (no domain-specific data).
        """
        return None

    def get_middleware_config(self) -> dict[str, Any]:
        """
        Return plugin-specific middleware configuration overrides.

        Default implementation returns empty dict (no overrides).
        """
        return {}


class PluginRegistry:
    """
    Central registry for domain plugins.

    Plugins are registered in order of priority. The registry supports:
    - Built-in plugins (auto-discovered from docmirror.plugins.*)
    - Manual registration via register()
    - Entry point discovery (future: via importlib.metadata)
    """

    def __init__(self):
        self._plugins: dict[tuple[str, str], DomainPlugin] = {}
        self._discovered = False

    def register(self, plugin: DomainPlugin, *, override: bool = False) -> None:
        """Register a domain plugin."""
        name = plugin.domain_name
        edition = plugin.edition
        key = (name, edition)
        if key in self._plugins and not override:
            logger.warning(f"[PluginRegistry] Plugin '{name}' edition '{edition}' already registered; use override=True to replace")
            return
        self._plugins[key] = plugin
        logger.debug(f"[PluginRegistry] Registered plugin: {name} ({plugin.display_name}) [{edition}]")

    def get(self, domain_name: str, edition: str = "community") -> DomainPlugin | None:
        """Get a registered plugin by domain name and edition."""
        self._ensure_discovered()
        return self._plugins.get((domain_name, edition))

    def get_first(self, domain_name: str) -> DomainPlugin | None:
        """Get the highest-edition plugin for a domain (finance > enterprise > community)."""
        self._ensure_discovered()
        for ed in ("finance", "enterprise", "community"):
            p = self._plugins.get((domain_name, ed))
            if p:
                return p
        return None

    def list_by_edition(self, edition: str) -> list[DomainPlugin]:
        """List all plugins for a specific edition."""
        self._ensure_discovered()
        return [p for (_, ed), p in self._plugins.items() if ed == edition]

    def list_domains(self) -> dict[str, list[str]]:
        """Return {domain_name: [edition, ...]} for all registered plugins."""
        self._ensure_discovered()
        domains: dict[str, list[str]] = {}
        for (name, ed), p in self._plugins.items():
            domains.setdefault(name, []).append(ed)
        return domains

    def list_plugins(self) -> dict[str, str]:
        """Return {domain_name: display_name} for all registered plugins (highest edition per domain)."""
        self._ensure_discovered()
        result = {}
        for (name, ed), p in sorted(self._plugins.items()):
            # Keep the highest edition per domain
            if name not in result:
                result[name] = p.display_name
        return result

    def get_all_scene_keywords(self) -> dict[str, Sequence[str]]:
        """Return {domain_name: keywords} for plugins with scene keywords."""
        self._ensure_discovered()
        result: dict[str, Sequence[str]] = {}
        for (name, ed), p in sorted(self._plugins.items()):
            if p.scene_keywords and name not in result:
                result[name] = p.scene_keywords
        return result

    def build_domain_data(
        self,
        domain_name: str,
        metadata: dict[str, Any],
        entities: dict[str, Any],
    ) -> Any | None:
        """Build domain data using the highest-edition plugin."""
        plugin = self.get_first(domain_name)
        if plugin is None:
            return None
        return plugin.build_domain_data(metadata, entities)

    def _ensure_discovered(self) -> None:
        """Auto-discover built-in plugins on first access."""
        if self._discovered:
            return
        self._discovered = True
        self._discover_builtin_plugins()

    def _discover_builtin_plugins(self) -> None:
        """Discover and load plugins from docmirror.plugins subpackage.

        Two-phase loading:
          1. Single-file plugins (*.py, community baseline)
          2. Directory plugins (enterprise edition, override community versions)
        """
        try:
            import docmirror.plugins as plugins_pkg

            # Phase 1: single-file community plugins (*_community.py)
            for _, modname, ispkg in pkgutil.iter_modules(plugins_pkg.__path__):
                if ispkg or not modname.endswith("_community") or modname.startswith("_"):
                    continue
                try:
                    mod = importlib.import_module(f"docmirror.plugins.{modname}")
                    if hasattr(mod, "plugin"):
                        self.register(mod.plugin)
                    elif hasattr(mod, "Plugin"):
                        self.register(mod.Plugin())
                except Exception as e:
                    logger.warning(f"[PluginRegistry] Failed to load community plugin docmirror.plugins.{modname}: {e}")

            # Phase 2: enterprise plugins (from docmirror-enterprise package, if installed)
            try:
                from docmirror_enterprise import enable as enterprise_enable
                enterprise_enable.register_enterprise_plugins(self)
                logger.info("[PluginRegistry] Enterprise plugins discovered from docmirror-enterprise")
            except ImportError:
                logger.debug("[PluginRegistry] No docmirror-enterprise package found; community edition only")
            except Exception as e:
                logger.warning(f"[PluginRegistry] Error discovering enterprise plugins: {e}")

            # Phase 3: finance plugins (from docmirror-finance package, if installed)
            try:
                from docmirror_finance import enable as finance_enable
                finance_enable.register_finance_plugins(self)
                logger.info("[PluginRegistry] Finance plugins discovered from docmirror-finance")
            except ImportError:
                logger.debug("[PluginRegistry] No docmirror-finance package found; baseline edition only")
            except Exception as e:
                logger.warning(f"[PluginRegistry] Error discovering finance plugins: {e}")
        except ImportError:
            logger.debug("[PluginRegistry] No docmirror.plugins package found")


# Global singleton registry
registry = PluginRegistry()

# Lazy-loaded license/plugin managers (defined in sibling modules)
_license_manager = None
_plugin_manager = None


def _get_license_manager():
    global _license_manager
    if _license_manager is None:
        from docmirror.plugins.license import license_manager as _lm
        _license_manager = _lm
    return _license_manager


def _get_plugin_manager():
    global _plugin_manager
    if _plugin_manager is None:
        from docmirror.plugins.manager import plugin_manager as _pm
        _plugin_manager = _pm
    return _plugin_manager


# Backward-compatible singletons (for docmirror.cli.plugins)
license_manager = _get_license_manager()
plugin_manager = _get_plugin_manager()

__all__ = [
    "DomainPlugin",
    "PluginRegistry",
    "registry",
    "license_manager",
    "plugin_manager",
]

from docmirror.configs.scene.loader import get_plugin_scene_keywords



