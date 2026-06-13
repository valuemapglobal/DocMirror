# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DEC helpers for plugin ``build_domain_data`` (design 09 §4.4)."""

from __future__ import annotations

from typing import Any


def build_dec_kv(
    document_type: str,
    entities: dict[str, Any],
    *,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a DEC-compatible dict from flat entity fields.

    Returned shape is accepted by ``normalize_domain_result()`` and
    ``plugins/runner._kv_community_payload()``.
    """
    cleaned: dict[str, Any] = {}
    for key, value in entities.items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        cleaned[key] = value
    return {
        "document_type": document_type,
        "entities": cleaned,
        "properties": properties or {},
    }


def dec_fields(raw: Any) -> dict[str, Any]:
    """Extract edition ``data.fields`` dict from ``build_domain_data`` output."""
    if raw is None:
        return {}
    from docmirror.models.entities.domain_result import DomainExtractionResult, normalize_domain_result

    if isinstance(raw, DomainExtractionResult):
        return dict(raw.entities)
    dec = normalize_domain_result(raw)
    return dict(dec.entities or {})
