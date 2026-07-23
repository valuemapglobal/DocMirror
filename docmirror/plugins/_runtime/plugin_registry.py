# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lazy post-seal registry for external edition projectors."""

from __future__ import annotations

import copy
import logging
import threading
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any

from docmirror.plugin_api import PluginProvider

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Central registry for post-seal projector providers."""

    def __init__(self):
        self._providers: dict[str, PluginProvider] = {}
        self._projectors: dict[tuple[str, str], Any] = {}
        self._projector_providers: dict[tuple[str, str], str] = {}
        self._provider_manifests: dict[str, dict[str, Any]] = {}
        self._provider_resource_roots: dict[str, Any] = {}
        self._discovering = False
        self._discovered = False
        self._frozen = False
        self._lock = threading.Lock()

    def register_provider(
        self,
        provider: PluginProvider,
        *,
        manifest: dict[str, Any] | None = None,
        resource_root: Any | None = None,
        override: bool = False,
    ) -> None:
        """Register one projector-only provider."""
        if self._frozen:
            raise RuntimeError("PluginRegistry is frozen after discovery")
        provider = PluginProvider.model_validate(provider)
        if provider.provider_id in self._providers and not override:
            raise ValueError(f"provider already registered: {provider.provider_id}")

        previous = self._providers.get(provider.provider_id)
        if previous is not None and override:
            for projector in previous.projectors:
                key = self._projector_key(projector, previous.provider_id)
                if self._projectors.get(key) is projector:
                    self._projectors.pop(key, None)
                    self._projector_providers.pop(key, None)

        if resource_root is None and previous is not None:
            resource_root = self._provider_resource_roots.get(provider.provider_id)
        if resource_root is None and provider.resource_package:
            resource_root = files(provider.resource_package)
        self._validate_provider_resources(provider, resource_root)

        keys: list[tuple[str, str]] = []
        for projector in provider.projectors:
            key = self._projector_key(projector, provider.provider_id)
            if key in self._projectors and not override:
                raise ValueError(f"projector already registered for {key[0]}:{key[1]}")
            if not callable(getattr(projector, "project", None)):
                raise ValueError(f"projector has no callable project(): {provider.provider_id}")
            keys.append(key)

        self._providers[provider.provider_id] = provider
        if resource_root is not None:
            self._provider_resource_roots[provider.provider_id] = resource_root
        self._provider_manifests[provider.provider_id] = copy.deepcopy(
            manifest
            or {
                "schema_version": 2,
                "provider": {
                    "id": provider.provider_id,
                    "version": provider.version,
                    "api_version": provider.api_version,
                    "supported_sealed_schemas": list(provider.supported_sealed_schemas),
                    "resource_package": provider.resource_package,
                },
                "resources": dict(provider.resources),
            }
        )
        for key, projector in zip(keys, provider.projectors, strict=True):
            self._projectors[key] = projector
            self._projector_providers[key] = provider.provider_id

    @staticmethod
    def _projector_key(projector: Any, provider_id: str) -> tuple[str, str]:
        domain = str(getattr(projector, "domain_name", "") or "").strip()
        edition = str(getattr(projector, "edition", "") or "").strip()
        if not domain or not edition:
            raise ValueError(f"projector must declare domain_name and edition: {provider_id}")
        return domain, edition

    def get_projector(
        self,
        domain_name: str,
        edition: str,
        *,
        sealed_schema: str | None = None,
    ):
        self._ensure_discovered()
        key = (domain_name, edition)
        projector = self._projectors.get(key)
        if projector is None or sealed_schema is None:
            return projector
        provider_id = self._projector_providers[key]
        provider = self._providers[provider_id]
        return projector if sealed_schema in provider.supported_sealed_schemas else None

    def list_projectors(self, edition: str | None = None) -> tuple[Any, ...]:
        self._ensure_discovered()
        return tuple(
            projector
            for (_domain_name, projector_edition), projector in sorted(self._projectors.items())
            if edition is None or projector_edition == edition
        )

    def list_providers(self) -> tuple[PluginProvider, ...]:
        self._ensure_discovered()
        return tuple(self._providers[key] for key in sorted(self._providers))

    def get_provider_manifest(self, provider_id: str) -> dict[str, Any] | None:
        self._ensure_discovered()
        manifest = self._provider_manifests.get(provider_id)
        return copy.deepcopy(manifest) if manifest is not None else None

    def list_provider_manifests(self) -> tuple[dict[str, Any], ...]:
        self._ensure_discovered()
        return tuple(copy.deepcopy(self._provider_manifests[key]) for key in sorted(self._provider_manifests))

    def read_provider_resource(self, provider_id: str, resource_name: str) -> str | None:
        """Read a post-seal private resource declared by a projector provider."""
        self._ensure_discovered()
        provider = self._providers.get(provider_id)
        if provider is None:
            return None
        relative_path = provider.resources.get(resource_name)
        if not relative_path or not provider.resource_package:
            return None
        package_root = self._provider_resource_roots.get(provider_id) or files(provider.resource_package)
        resource = package_root.joinpath(*PurePosixPath(relative_path).parts)
        return resource.read_text(encoding="utf-8")

    def list_domains(self) -> dict[str, list[str]]:
        self._ensure_discovered()
        domains: dict[str, list[str]] = {}
        for domain_name, edition in self._projectors:
            domains.setdefault(domain_name, []).append(edition)
        return {name: sorted(set(editions)) for name, editions in sorted(domains.items())}

    @staticmethod
    def _validate_provider_resources(provider: PluginProvider, package_root: Any | None) -> None:
        if not provider.resources:
            return
        assert provider.resource_package is not None
        if package_root is None:
            raise ValueError(f"resource package is unavailable: {provider.resource_package}")
        for resource_name, relative_path in provider.resources.items():
            resource = package_root.joinpath(*PurePosixPath(relative_path).parts)
            if not resource.is_file():
                raise ValueError(f"missing plugin resource {provider.provider_id}:{resource_name}: {relative_path}")

    def _ensure_discovered(self) -> None:
        if self._discovered:
            return
        with self._lock:
            if self._discovered:
                return
            self._discovering = True
            try:
                self._discover_third_party_providers()
                self._discovered = True
                self._frozen = True
            finally:
                self._discovering = False

    def _discover_third_party_providers(self) -> None:
        """Load projector providers through pluggy only at the output boundary."""
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

__all__ = ["PluginRegistry", "registry", "resolve_dgc_status"]
