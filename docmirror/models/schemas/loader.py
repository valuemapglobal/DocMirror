# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
DEC schema registry loader and validator (design 09 §4.4).

Loads declarative ``dec_validation`` constraints from bundled plugin manifests
and validates ``DomainExtractionResult`` instances without importing business
schema modules into Core.

Functions::

    load_schema_registry()   LRU-cached document_type → declarative constraints
    validate_dec()           Return issue strings (empty = ok); optional strict mode
"""

from __future__ import annotations

import logging
from functools import lru_cache
from importlib.resources import files

import yaml

from docmirror.models.entities.domain_result import DomainExtractionResult

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_schema_registry() -> dict[str, dict]:
    registry: dict[str, dict] = {}
    plugin_root = files("docmirror").joinpath("plugins")
    for plugin_dir in sorted(plugin_root.iterdir(), key=lambda item: item.name):
        manifest_path = plugin_dir.joinpath("plugin.yaml")
        if not plugin_dir.is_dir() or not manifest_path.is_file():
            continue
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        provider = manifest.get("provider") or {}
        document_type = str(provider.get("domain_name") or "")
        constraints = manifest.get("dec_validation")
        if document_type and isinstance(constraints, dict):
            registry[document_type] = dict(constraints)
    return registry


def validate_dec(dec: DomainExtractionResult, *, strict: bool = False) -> list[str]:
    """
    Validate DEC against registered schema for ``dec.document_type``.

    Returns list of issue strings (empty = ok). Does not raise unless ``strict=True``.
    """
    issues: list[str] = []
    registry = load_schema_registry()
    constraints = registry.get(dec.document_type)
    if constraints is None:
        return []
    try:
        structured_data = dec.structured_data
        if constraints.get("structured_data") == "mapping" and not isinstance(structured_data, dict):
            issues.append(f"{dec.document_type}: structured_data must be a dict")
            return issues
        if constraints.get("require_entities_or_records") is True and not dec.entities:
            records = structured_data.get("records") if isinstance(structured_data, dict) else structured_data
            if isinstance(records, list) and not records:
                issues.append(f"{dec.document_type}: no entities or structured_data records")
        if isinstance(structured_data, dict):
            for field_name in constraints.get("list_fields") or []:
                value = structured_data.get(str(field_name))
                if not isinstance(value, list):
                    issues.append(f"{dec.document_type}: structured_data.{field_name} must be a list")
                elif not value and dec.quality.validation_passed:
                    issues.append(f"{dec.document_type}: validation_passed but {field_name} empty")
            for field_name in constraints.get("optional_mapping_fields") or []:
                value = structured_data.get(str(field_name))
                if value is not None and not isinstance(value, dict):
                    issues.append(f"{dec.document_type}: structured_data.{field_name} must be a dict")
    except Exception as exc:
        msg = f"DEC validation error for {dec.document_type}: {exc}"
        if strict:
            raise ValueError(msg) from exc
        issues.append(msg)

    return issues
