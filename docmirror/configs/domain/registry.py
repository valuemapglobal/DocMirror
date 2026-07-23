# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Domain Registry — document-type identity fields and multilingual key normalization.
=====================================================================================

Builds document identity definitions and multilingual key normalization from
plugin-owned resources declared in each ``plugin.yaml`` manifest.

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

import logging
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# Multilingual Key Synonyms — loaded from plugin resources
# ══════════════════════════════════════════════════════════════════════════════


def load_plugin_domain_resources() -> tuple[dict[str, dict[str, Any]], dict[str, list[tuple[str, ...]]]]:
    """Load key synonyms and identity definitions without importing plugin code."""
    domains: dict[str, dict[str, Any]] = {}
    identity_fields: dict[str, list[tuple[str, ...]]] = {}
    plugin_root = files("docmirror").joinpath("plugins")

    for plugin_dir in sorted(plugin_root.iterdir(), key=lambda item: item.name):
        manifest_path = plugin_dir.joinpath("plugin.yaml")
        if not plugin_dir.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            relative_text = str(((manifest.get("resources") or {}).get("key_synonyms")) or "").strip()
            relative_path = PurePosixPath(relative_text)
            if not relative_text or relative_path.is_absolute() or ".." in relative_path.parts:
                continue
            resource_path = plugin_dir.joinpath(*relative_path.parts)
            payload = yaml.safe_load(resource_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("Failed to load plugin key synonyms from %s: %s", plugin_dir.name, exc)
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
    logger.info("[Config] Loaded %d key synonyms from plugin resources", len(flat))
    return flat


KEY_SYNONYMS_BY_DOMAIN, DOMAIN_IDENTITY = load_plugin_domain_resources()
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
