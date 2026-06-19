# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
KV community plugin extract helper for premium L2 key-value documents.

Builds v2.0 community edition output for plugins whose primary archetype is
key-value (VAT invoice, business license, credit report): match identity labels
against Mirror KV pairs and entities, collect table records as structured data,
and serialize via ``edition_serializer``.

Pipeline role: called from domain ``community_plugin.extract_from_mirror`` methods;
``runner`` may also reach KV output through ``build_domain_data`` + ``dec_builder``.

Key exports: ``extract_kv_community_output``.

Dependencies: ``generic_mirror_adapter`` (field/record collectors),
``models.edition_serializer``, ``models.entities.domain_result``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from docmirror.models.edition_serializer import EditionContext, edition_serializer
from docmirror.models.entities.domain_result import DomainExtractionResult, DomainQuality
from docmirror.plugins._base.generic_mirror_adapter import _collect_entity_fields, _collect_table_records
from docmirror.models.mirror.block_fields import collect_kv_fields_from_blocks


def _match_identity_fields(
    parse_result: Any,
    identity_specs: Sequence[tuple[str, Sequence[str]]],
    entity_dict: dict[str, Any],
) -> dict[str, Any]:
    """Map identity field keys using entity dict + KV label matching."""
    out: dict[str, Any] = {}
    for field_key, labels in identity_specs:
        if field_key in entity_dict and entity_dict[field_key]:
            out[field_key] = entity_dict[field_key]
            continue
        for page in getattr(parse_result, "pages", []) or []:
            for kv in getattr(page, "key_values", []) or []:
                key = (getattr(kv, "key", None) or "").strip()
                val = (getattr(kv, "value", None) or "").strip()
                if not val:
                    continue
                if any(label in key for label in labels):
                    out[field_key] = val
                    break
            if field_key in out:
                break
    return out


def extract_kv_community_output(
    plugin: Any,
    parse_result: Any,
    *,
    identity_specs: Sequence[tuple[str, Sequence[str]]],
    full_text: str = "",
    match_method: str = "keyword_kv_hybrid",
    support_level: str = "L2",
) -> dict[str, Any]:
    """Build v2.0 community output for key-value premium plugins."""
    detected_type = getattr(plugin, "domain_name", "unknown")
    entity_pool = _collect_entity_fields(parse_result)
    block_kv = collect_kv_fields_from_blocks(parse_result)
    for key, value in block_kv.items():
        entity_pool.setdefault(key, value)
    fields = _match_identity_fields(parse_result, identity_specs, entity_pool)
    if not fields:
        fields = {k: v for k, v in entity_pool.items() if v not in (None, "")}

    records = _collect_table_records(parse_result)
    file_path = getattr(parse_result, "file_path", "") or ""
    doc_name = Path(file_path).name if file_path else getattr(plugin, "display_name", detected_type)
    page_count = len(getattr(parse_result, "pages", []) or [])

    warnings: list[str] = []
    if not fields:
        warnings.append("no_fields_extracted")

    dec = DomainExtractionResult(
        document_type=detected_type,
        properties={},
        entities=fields,
        structured_data={
            "records": records,
            "summary": {"total_rows": len(records)},
            "sections": [],
            "tables": [],
            "line_items": [],
        },
        quality=DomainQuality(
            validation_passed=bool(fields or records),
            issues=[f"warning:{w}" for w in warnings],
        ),
    )

    ctx = EditionContext(
        edition="community",
        detected_type=detected_type,
        full_text=full_text,
        document_name=doc_name,
        page_count=page_count,
        archetype="key_value_document",
        domain=detected_type,
        match_method=match_method,
        scene_keywords=getattr(plugin, "scene_keywords", ()) or (),
        plugin_name=detected_type,
        plugin_display_name=getattr(plugin, "display_name", detected_type),
        plugin_version="community-2.0",
        support_level=support_level,
        parser_label="docmirror-community",
    )
    return edition_serializer(dec, context=ctx)
