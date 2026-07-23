# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Domain Registry — document-type identity fields and multilingual key normalization.
=====================================================================================

 Builds document identity definitions and multilingual key normalization from
Core-owned canonical domain resources. The resources remain physically colocated
under ``docmirror.plugins`` for packaging stability, but they are loaded from a
closed Core inventory and never through ``PluginRegistry``.

Identity resolution::

    Each field definition is ``(display_name, candidate_key_1, candidate_key_2, …)``.
    ``resolve_identity(domain, entities)`` normalizes keys via ``KEY_SYNONYMS``,
    then returns the first non-empty candidate value per field.

Key synonyms::

    Each plugin's resource uses ``domains → locale → {raw_key: canonical_key}``.
    All installed bundled resources are flattened into ``KEY_SYNONYMS`` for O(1)
    lookup. Missing resources degrade gracefully.

Wildcard domain ``"*"`` provides fallback identity (title, date, author) for
unrecognized document types.

Usage::

    from docmirror.configs.domain.registry import resolve_identity

    identity = resolve_identity("bank_statement", extracted_entities)
    # {'document_type': 'bank_statement', 'institution': 'HSBC', ...}
"""

from __future__ import annotations

import copy
import logging
from functools import cache, lru_cache
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CANONICAL_DOMAIN_IDS = (
    "alipay_payment",
    "bank_statement",
    "business_license",
    "credit_report",
    "generic",
    "vat_invoice",
    "wechat_payment",
)


@lru_cache(maxsize=1)
def _canonical_domain_manifest_index() -> dict[str, dict[str, Any]]:
    """Load the fixed Core domain inventory without plugin discovery."""
    manifests: dict[str, dict[str, Any]] = {}
    package_root = files("docmirror").joinpath("plugins")
    for domain_id in CANONICAL_DOMAIN_IDS:
        manifest_path = package_root.joinpath(domain_id).joinpath("plugin.yaml")
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError(f"invalid canonical domain manifest: {manifest_path}")
        provider = payload.get("provider")
        if not isinstance(provider, dict) or str(provider.get("domain_name") or "") != domain_id:
            raise ValueError(f"canonical domain manifest identity mismatch: {manifest_path}")
        manifests[domain_id] = payload
    return manifests


def list_canonical_domain_manifests() -> tuple[dict[str, Any], ...]:
    """Return isolated manifests for the fixed Core domain capabilities."""
    manifests = _canonical_domain_manifest_index()
    return tuple(copy.deepcopy(manifests[domain_id]) for domain_id in CANONICAL_DOMAIN_IDS)


def get_canonical_domain_manifest(domain_id: str) -> dict[str, Any] | None:
    manifest = _canonical_domain_manifest_index().get(str(domain_id))
    return copy.deepcopy(manifest) if manifest is not None else None


def read_canonical_domain_resource(domain_id: str, resource_name: str) -> str | None:
    """Read one declared Core domain resource from its bundled package."""
    manifest = _canonical_domain_manifest_index().get(str(domain_id))
    if manifest is None:
        return None
    relative_text = str((manifest.get("resources") or {}).get(resource_name) or "").strip()
    relative = PurePosixPath(relative_text)
    if not relative_text or relative.is_absolute() or ".." in relative.parts:
        return None
    resource = files("docmirror").joinpath("plugins").joinpath(domain_id).joinpath(*relative.parts)
    return resource.read_text(encoding="utf-8") if resource.is_file() else None


def iter_canonical_domain_resources(resource_name: str) -> tuple[tuple[str, str], ...]:
    loaded: list[tuple[str, str]] = []
    for domain_id in CANONICAL_DOMAIN_IDS:
        text = read_canonical_domain_resource(domain_id, resource_name)
        if text is not None:
            loaded.append((domain_id, text))
    return tuple(loaded)


def iter_canonical_domain_resources_by_prefix(prefix: str) -> tuple[tuple[str, str, str], ...]:
    loaded: list[tuple[str, str, str]] = []
    for domain_id in CANONICAL_DOMAIN_IDS:
        manifest = _canonical_domain_manifest_index()[domain_id]
        for resource_name in sorted(manifest.get("resources") or {}):
            if not resource_name.startswith(prefix):
                continue
            text = read_canonical_domain_resource(domain_id, resource_name)
            if text is not None:
                loaded.append((domain_id, resource_name, text))
    return tuple(loaded)


@lru_cache(maxsize=1)
def load_canonical_domain_capability() -> dict[str, Any]:
    premium: list[tuple[int, str]] = []
    aliases: dict[str, str] = {}
    generic_enabled = False
    for manifest in list_canonical_domain_manifests():
        provider = manifest.get("provider") or {}
        capabilities = manifest.get("capabilities") or {}
        classification = manifest.get("classification") or {}
        domain = str(provider.get("domain_name") or "")
        if bool(capabilities.get("premium")):
            premium.append((int(capabilities.get("community_order") or 999), domain))
        if bool(capabilities.get("generic_fallback")):
            generic_enabled = True
        for alias in classification.get("aliases") or []:
            normalized = str(alias or "").strip()
            if normalized:
                aliases[normalized] = domain
    premium.sort(key=lambda item: (item[0], item[1]))
    return {
        "premium_domains": tuple(domain for _order, domain in premium),
        "generic_enabled": generic_enabled,
        "aliases": aliases,
    }


def get_canonical_premium_domains() -> tuple[str, ...]:
    return tuple(load_canonical_domain_capability()["premium_domains"])


def is_canonical_premium_domain(document_type: str) -> bool:
    return document_type in get_canonical_premium_domains()


def normalize_canonical_document_type(document_type: str) -> str:
    aliases = load_canonical_domain_capability().get("aliases") or {}
    return str(aliases.get(document_type, document_type))


@cache
def get_quality_group_domains(group: str) -> tuple[str, ...]:
    domains: list[str] = []
    for manifest in list_canonical_domain_manifests():
        provider = manifest.get("provider") or {}
        capabilities = manifest.get("capabilities") or {}
        domain = str(provider.get("domain_name") or "").strip()
        groups = {str(value).strip() for value in capabilities.get("quality_groups") or ()}
        if domain and group in groups:
            domains.append(domain)
    return tuple(sorted(set(domains)))


# ══════════════════════════════════════════════════════════════════════════════
# Multilingual Key Synonyms — loaded from Core domain resources
# ══════════════════════════════════════════════════════════════════════════════


def load_canonical_domain_resources() -> tuple[dict[str, dict[str, Any]], dict[str, list[tuple[str, ...]]]]:
    """Load key synonyms and identity definitions without plugin discovery."""
    domains: dict[str, dict[str, Any]] = {}
    identity_fields: dict[str, list[tuple[str, ...]]] = {}

    for domain_id, resource_text in iter_canonical_domain_resources("key_synonyms"):
        try:
            payload = yaml.safe_load(resource_text) or {}
        except Exception as exc:
            logger.warning("Failed to load canonical key synonyms from %s: %s", domain_id, exc)
            continue

        resource_domains = payload.get("domains") if isinstance(payload, dict) else None
        if isinstance(resource_domains, dict):
            for domain, locales in resource_domains.items():
                if not isinstance(locales, dict):
                    continue
                target_locales = domains.setdefault(str(domain), {})
                for locale, mappings in locales.items():
                    if not isinstance(mappings, dict):
                        continue
                    target_locales.setdefault(str(locale), {}).update(mappings)

        resource_identity = payload.get("identity_fields") if isinstance(payload, dict) else None
        if isinstance(resource_identity, dict):
            for domain, definitions in resource_identity.items():
                if not isinstance(definitions, list):
                    continue
                identity_fields[str(domain)] = [
                    tuple(str(item) for item in definition)
                    for definition in definitions
                    if isinstance(definition, list) and len(definition) >= 2
                ]
    return domains, identity_fields


def _flatten_key_synonyms(domains: dict[str, dict[str, Any]]) -> dict[str, str]:
    flat: dict[str, str] = {}
    for locales in domains.values():
        for mappings in locales.values():
            if isinstance(mappings, dict):
                flat.update({str(key): str(value) for key, value in mappings.items()})
    logger.info("[Config] Loaded %d key synonyms from canonical domain resources", len(flat))
    return flat


KEY_SYNONYMS_BY_DOMAIN, DOMAIN_IDENTITY = load_canonical_domain_resources()
KEY_SYNONYMS: dict[str, str] = _flatten_key_synonyms(KEY_SYNONYMS_BY_DOMAIN)


def normalize_entity_keys(entities: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize locale-specific entity keys to canonical English equivalents.

    Applies ``KEY_SYNONYMS`` (loaded from ``key_synonyms.yaml``) to translate
    raw extracted keys (e.g. ``"Account Number"``) into canonical English keys
    (e.g. ``"Account number"``).

    Rules:
        - If the canonical key already exists in the dict, the original
          value is preserved (extraction-level data takes priority).
        - Unknown keys pass through unchanged.
        - The original dict is not mutated; a new dict is returned.

    Args:
        entities: Raw entity dict from document extraction.

    Returns:
        New dict with normalized keys.
    """
    normalized: dict[str, Any] = {}

    for key, value in entities.items():
        canonical = KEY_SYNONYMS.get(key, key)
        # Don't overwrite if the canonical key was already set
        if canonical not in normalized:
            normalized[canonical] = value
        elif key not in KEY_SYNONYMS:
            # Original (non-synonym) key takes priority over synonym-derived
            normalized[key] = value

    return normalized


def resolve_identity(domain: str, entities: dict[str, Any]) -> dict[str, str]:
    """
    Extract standardized identity fields from raw entities by document type.

    Internally normalizes entity keys via ``normalize_entity_keys()`` before
    matching, so locale-specific keys (e.g. Chinese) are resolved
    transparently.

    Args:
        domain:   Document type string (e.g., "bank_statement", "invoice").
        entities: Dict of extracted key-value entities from the document.

    Returns:
        Dict with standardized identity fields. Always includes
        ``"document_type"`` as the first key. Missing fields are set
        to empty strings.
    """
    # Normalize locale-specific keys to canonical English
    normalized = normalize_entity_keys(entities)

    fields = DOMAIN_IDENTITY.get(domain, DOMAIN_IDENTITY.get("*", []))
    identity: dict[str, str] = {"document_type": domain}

    for field_def in fields:
        display_name = field_def[0]
        candidates = field_def[1:]
        # Try each candidate key in order; use the first non-empty value
        for key in candidates:
            val = normalized.get(key, "")
            if val:
                identity[display_name] = str(val)
                break
        else:
            # No candidate had a value — set to empty string
            identity[display_name] = ""

    logger.info(f"[Config] Resolved identity for domain '{domain}': extracted {len(identity) - 1}/{len(fields)} fields")
    return identity
