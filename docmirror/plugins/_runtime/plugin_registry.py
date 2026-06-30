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

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any

from docmirror.configs.scene.loader import get_plugin_scene_keywords

logger = logging.getLogger(__name__)


class DomainPlugin(ABC):
    """Abstract base class for domain plugins."""

    @property
    @abstractmethod
    def domain_name(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

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
        self._lock = threading.Lock()
        self._progress_callback: Callable[[str, float, str], None] | None = None

    def set_progress_callback(self, callback: Callable[[str, float, str], None] | None) -> None:
        """Set a progress callback for plugin discovery operations.

        The callback receives (phase, phase_pct, message) during long-running
        discovery tasks such as enterprise/finance plugin registration.
        """
        self._progress_callback = callback

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
        # Fast path: already fully discovered.
        if self._discovered:
            return

        # First thread to enter acquires the lock and runs discovery.
        # Other threads wait until discovery completes, then return.
        with self._lock:
            if self._discovered:
                return
            self._discover_builtin_plugins()
            self._discovered = True

    def _discover_builtin_plugins(self) -> None:
        _discovery_start = time.perf_counter()
        _on_progress = self._progress_callback
        logger.info("[PluginRegistry] Beginning plugin discovery...")
        try:
            # Explicit static imports — replaces importlib.import_module() magic
            from docmirror.plugins._runtime.community import (
                alipay_payment_plugin,
                bank_statement_plugin,
                business_license_plugin,
                credit_report_plugin,
                generic_plugin,
                vat_invoice_plugin,
                wechat_payment_plugin,
            )

            _community_plugins = [
                alipay_payment_plugin,
                bank_statement_plugin,
                business_license_plugin,
                credit_report_plugin,
                generic_plugin,
                vat_invoice_plugin,
                wechat_payment_plugin,
            ]

            for plugin in _community_plugins:
                self.register(plugin)

            _community_elapsed = (time.perf_counter() - _discovery_start) * 1000
            logger.info(
                "[PluginRegistry] Community plugins registered in %.0f ms (%d plugins)",
                _community_elapsed,
                len(_community_plugins),
            )

            try:
                _ent_start = time.perf_counter()
                if _on_progress:
                    _on_progress("community_plugin", 55.0, "Discovering enterprise plugins...")
                logger.info("[PluginRegistry] Discovering enterprise plugins...")
                from docmirror_enterprise import enable as enterprise_enable

                enterprise_enable.register_enterprise_plugins(self)
                _ent_elapsed = (time.perf_counter() - _ent_start) * 1000
                _ent_count = len(self._plugins) - len(_community_plugins)
                logger.info(
                    "[PluginRegistry] Enterprise plugins registered in %.0f ms (%d plugins total)",
                    _ent_elapsed,
                    _ent_count,
                )
                if _on_progress:
                    _on_progress("community_plugin", 70.0, "Enterprise plugins registered...")
            except ImportError:
                logger.debug("[PluginRegistry] No docmirror-enterprise package found; community edition only")
            except Exception as e:
                logger.warning("[PluginRegistry] Error discovering enterprise plugins: %s", e)

            try:
                _fin_start = time.perf_counter()
                if _on_progress:
                    _on_progress("community_plugin", 70.0, "Discovering finance plugins...")
                logger.info("[PluginRegistry] Discovering finance plugins...")
                from docmirror_finance import enable as finance_enable

                finance_enable.register_finance_plugins(self)
                _fin_elapsed = (time.perf_counter() - _fin_start) * 1000
                _pre_fin_count = len(self._plugins)
                logger.info(
                    "[PluginRegistry] Finance plugins registered in %.0f ms (%d plugins total)",
                    _fin_elapsed,
                    len(self._plugins),
                )
                if _on_progress:
                    _on_progress("community_plugin", 85.0, "Finance plugins registered...")
            except ImportError:
                logger.debug("[PluginRegistry] No docmirror-finance package found; baseline edition only")
            except Exception as e:
                logger.warning("[PluginRegistry] Error discovering finance plugins: %s", e)
        except ImportError:
            logger.debug("[PluginRegistry] No docmirror.plugins package found")
        finally:
            _total_elapsed = (time.perf_counter() - _discovery_start) * 1000
            logger.info(
                "[PluginRegistry] Plugin discovery complete in %.0f ms — %d plugins in registry",
                _total_elapsed,
                len(self._plugins),
            )


def resolve_dgc_status(domain: str) -> str:
    from docmirror.configs.ga_readiness import dgc_status_for_domain

    return dgc_status_for_domain(domain)


registry = PluginRegistry()

__all__ = ["DomainPlugin", "PluginRegistry", "registry", "resolve_dgc_status"]
