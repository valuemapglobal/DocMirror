# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
DEC schema registry loader and validator (design 09 §4.4).

Loads ``schemas/registry.yaml`` which maps ``document_type`` strings to Python
schema module names under ``docmirror.models.schemas``. Validates
``DomainExtractionResult`` instances against the registered schema for their
document type.

Functions::

    load_schema_registry()   LRU-cached document_type → module_key mapping
    validate_dec()             Return issue strings (empty = ok); optional strict mode

Each schema module exposes ``validate_dec(dec) -> list[str]`` or the legacy
``validate_entities`` alias. Unknown document types with no registry entry pass
validation silently. Strict mode raises ``ValueError`` on import or validation errors.
"""

from __future__ import annotations

import importlib
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from docmirror.models.entities.domain_result import DomainExtractionResult

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parent / "registry.yaml"


@lru_cache(maxsize=1)
def load_schema_registry() -> dict[str, str | None]:
    if not _REGISTRY_PATH.is_file():
        return {}
    data = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    raw = data.get("schemas") or {}
    return {str(k): (None if v is None else str(v)) for k, v in raw.items()}


def validate_dec(dec: DomainExtractionResult, *, strict: bool = False) -> list[str]:
    """
    Validate DEC against registered schema for ``dec.document_type``.

    Returns list of issue strings (empty = ok). Does not raise unless ``strict=True``.
    """
    issues: list[str] = []
    registry = load_schema_registry()
    module_key = registry.get(dec.document_type)
    if module_key is None:
        if dec.document_type in registry:
            return []
        return issues

    try:
        mod = importlib.import_module(f"docmirror.models.schemas.{module_key}")
    except ImportError as exc:
        msg = f"schema module {module_key!r} not found for {dec.document_type!r}: {exc}"
        if strict:
            raise ValueError(msg) from exc
        logger.debug("[DEC] %s", msg)
        return [msg]

    validator = getattr(mod, "validate_dec", None) or getattr(mod, "validate_entities", None)
    if validator is None:
        return issues

    try:
        result = validator(dec)
        if isinstance(result, list):
            issues.extend(str(x) for x in result)
        elif result is False:
            issues.append(f"validation failed for {dec.document_type}")
    except Exception as exc:
        msg = f"DEC validation error for {dec.document_type}: {exc}"
        if strict:
            raise ValueError(msg) from exc
        issues.append(msg)

    return issues
