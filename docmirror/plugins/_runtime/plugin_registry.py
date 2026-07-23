# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Domain plugin registry — ``DomainPlugin`` ABC and ``PluginRegistry`` singleton.

Defines the abstract contract every domain plugin implements (``domain_name``,
``display_name``, optional ``extract`` / ``recognize`` /
``build_domain_data``) and maintains a keyed registry of
``(domain_name, edition)`` instances. On first access, auto-discovers community
plugins from package-local ``plugin.yaml`` manifests. It also optionally loads
``docmirror_enterprise`` / ``docmirror_finance`` extension packages.

Pipeline role: ``runner`` looks up edition-specific plugins through ``registry.get``;
``manager`` lists registered domains for CLI enable/disable; scene keywords and
``build_domain_data`` support classification and KV fallback paths.

Key exports: ``DomainPlugin``, ``PluginRegistry``, ``registry``.

Dependencies: package-local plugin manifests, ``configs.scene.loader`` (scene
keywords), optional ``docmirror_enterprise`` / ``docmirror_finance`` packages.
"""

from __future__ import annotations

import copy
import importlib
import logging
import threading
import time
from collections.abc import Sequence
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any

import yaml

from docmirror.plugin_api import DomainPlugin, PluginProvider

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Central registry for domain plugins."""

    def __init__(self):
        self._plugins: dict[tuple[str, str], DomainPlugin] = {}
        self._providers: dict[str, PluginProvider] = {}
        self._recognizers: dict[str, Any] = {}
        self._projectors: dict[tuple[str, str], Any] = {}
        self._provider_manifests: dict[str, dict[str, Any]] = {}
        self._discovered = False
        self._frozen = False
        self._lock = threading.Lock()

    def register(self, plugin: DomainPlugin, *, override: bool = False) -> None:
        if self._frozen:
            raise RuntimeError("PluginRegistry is frozen after discovery")
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

    def register_provider(self, provider: PluginProvider, *, override: bool = False) -> None:
        """Register all roles from one provider manifest into the runtime SSOT."""
        if self._frozen:
            raise RuntimeError("PluginRegistry is frozen after discovery")
        provider = PluginProvider.model_validate(provider)
        if provider.provider_id in self._providers and not override:
            raise ValueError(f"provider already registered: {provider.provider_id}")
        self._providers[provider.provider_id] = provider
        for recognizer in provider.recognizers:
            domain = str(getattr(recognizer, "domain_name", provider.provider_id))
            if domain in self._recognizers and not override:
                raise ValueError(f"recognizer already registered for domain: {domain}")
            self._recognizers[domain] = recognizer
        for projector in provider.projectors:
            domain = str(getattr(projector, "domain_name", provider.provider_id))
            edition = str(getattr(projector, "edition", "community"))
            key = (domain, edition)
            if key in self._projectors and not override:
                raise ValueError(f"projector already registered for {domain}:{edition}")
            self._projectors[key] = projector

    def get_recognizer(self, domain_name: str):
        self._ensure_discovered()
        return self._recognizers.get(domain_name)

    def get_projector(self, domain_name: str, edition: str):
        self._ensure_discovered()
        return self._projectors.get((domain_name, edition))

    def list_providers(self) -> tuple[PluginProvider, ...]:
        self._ensure_discovered()
        return tuple(self._providers[key] for key in sorted(self._providers))

    def get_provider_manifest(self, provider_id: str) -> dict[str, Any] | None:
        """Return an isolated copy of a bundled provider's resource manifest."""
        self._ensure_discovered()
        manifest = self._provider_manifests.get(provider_id)
        return copy.deepcopy(manifest) if manifest is not None else None

    def list_provider_manifests(self) -> tuple[dict[str, Any], ...]:
        """Return bundled provider manifests in stable provider-id order."""
        self._ensure_discovered()
        return tuple(copy.deepcopy(self._provider_manifests[key]) for key in sorted(self._provider_manifests))

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
            self._discover_third_party_providers()
            self._discovered = True
            self._frozen = True

    def _discover_builtin_plugins(self) -> None:
        _discovery_start = time.perf_counter()
        logger.info("[PluginRegistry] Beginning plugin discovery...")
        try:
            manifest_plugins = self._discover_manifest_plugins()
            for plugin, version, manifest in manifest_plugins:
                self.register(plugin)
                self.register_provider(
                    PluginProvider(
                        provider_id=plugin.provider_id,
                        version=version,
                        recognizers=(plugin,),
                    )
                )
                self._provider_manifests[plugin.provider_id] = manifest

            _community_elapsed = (time.perf_counter() - _discovery_start) * 1000
            logger.info(
                "[PluginRegistry] Community plugins registered in %.0f ms (%d plugins)",
                _community_elapsed,
                sum(1 for (_name, edition) in self._plugins if edition == "community"),
            )

            try:
                _ent_start = time.perf_counter()
                logger.info("[PluginRegistry] Discovering enterprise plugins...")
                _pre_ent_count = len(self._plugins)
                from docmirror_enterprise import enable as enterprise_enable

                enterprise_enable.register_enterprise_plugins(self)
                _ent_elapsed = (time.perf_counter() - _ent_start) * 1000
                _ent_count = len(self._plugins) - _pre_ent_count
                logger.info(
                    "[PluginRegistry] Enterprise plugins registered in %.0f ms (%d plugins total)",
                    _ent_elapsed,
                    _ent_count,
                )
            except ImportError:
                logger.debug("[PluginRegistry] No docmirror-enterprise package found; community edition only")
            except Exception as e:
                logger.warning("[PluginRegistry] Error discovering enterprise plugins: %s", e)

            try:
                _fin_start = time.perf_counter()
                logger.info("[PluginRegistry] Discovering finance plugins...")
                from docmirror_finance import enable as finance_enable

                finance_enable.register_finance_plugins(self)
                _fin_elapsed = (time.perf_counter() - _fin_start) * 1000
                logger.info(
                    "[PluginRegistry] Finance plugins registered in %.0f ms (%d plugins total)",
                    _fin_elapsed,
                    len(self._plugins),
                )
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

    def _discover_manifest_plugins(self) -> list[tuple[DomainPlugin, str, dict[str, Any]]]:
        """Load bundled plugins that declare package-local resource ownership."""
        plugin_root = files("docmirror").joinpath("plugins")
        discovered: list[tuple[DomainPlugin, str, dict[str, Any]]] = []
        seen_provider_ids: set[str] = set()

        for plugin_dir in sorted(plugin_root.iterdir(), key=lambda item: item.name):
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir.joinpath("plugin.yaml")
            if not manifest_path.is_file():
                continue

            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError(f"invalid plugin manifest mapping: {manifest_path}")
            if raw.get("schema_version") != 1:
                raise ValueError(f"unsupported plugin manifest schema: {manifest_path}")

            provider = raw.get("provider")
            if not isinstance(provider, dict):
                raise ValueError(f"missing provider mapping: {manifest_path}")
            required = ("id", "domain_name", "edition", "version", "implementation")
            missing = [key for key in required if not str(provider.get(key) or "").strip()]
            if missing:
                raise ValueError(f"missing provider fields {missing}: {manifest_path}")

            provider_id = str(provider["id"])
            if provider_id in seen_provider_ids:
                raise ValueError(f"duplicate bundled provider id: {provider_id}")
            seen_provider_ids.add(provider_id)

            implementation = str(provider["implementation"])
            module_name, separator, attribute = implementation.partition(":")
            package_name = f"docmirror.plugins.{plugin_dir.name}"
            if (
                not separator
                or not attribute
                or not (module_name == package_name or module_name.startswith(f"{package_name}."))
            ):
                raise ValueError(f"implementation must stay inside {package_name}: {implementation}")

            module = importlib.import_module(module_name)
            plugin = getattr(module, attribute, None)
            if not isinstance(plugin, DomainPlugin):
                raise ValueError(f"implementation is not a DomainPlugin: {implementation}")
            if plugin.provider_id != provider_id:
                raise ValueError(f"provider id mismatch in {manifest_path}")
            if plugin.domain_name != str(provider["domain_name"]):
                raise ValueError(f"domain name mismatch in {manifest_path}")
            if plugin.edition != str(provider["edition"]):
                raise ValueError(f"edition mismatch in {manifest_path}")

            resources = raw.get("resources") or {}
            if not isinstance(resources, dict):
                raise ValueError(f"resources must be a mapping: {manifest_path}")
            for resource_name, relative_value in resources.items():
                relative_text = str(relative_value or "").strip()
                relative_path = PurePosixPath(relative_text)
                if not relative_text or relative_path.is_absolute() or ".." in relative_path.parts:
                    raise ValueError(f"unsafe resource path {resource_name}: {relative_value}")
                resource_path = plugin_dir.joinpath(*relative_path.parts)
                if not resource_path.is_file():
                    raise ValueError(f"missing plugin resource {resource_name}: {resource_path}")

            discovered.append((plugin, str(provider["version"]), raw))

        return discovered

    def _discover_third_party_providers(self) -> None:
        """Load entry-point providers through pluggy discovery transport."""
        try:
            from docmirror.plugins._runtime.discovery import load_plugin_providers

            for provider in load_plugin_providers():
                try:
                    self.register_provider(provider)
                except Exception as exc:
                    logger.warning("[PluginRegistry] Third-party provider rejected: %s", exc)
        except Exception as exc:
            logger.debug("[PluginRegistry] Third-party provider discovery skipped: %s", exc)


def resolve_dgc_status(domain: str) -> str:
    from docmirror.configs.ga_readiness import dgc_status_for_domain

    return dgc_status_for_domain(domain)


registry = PluginRegistry()

__all__ = ["DomainPlugin", "PluginRegistry", "registry", "resolve_dgc_status"]
