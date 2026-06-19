# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Mirror → generic community v2.0 output adapter for non-premium classified types.

Maps a complete Mirror ``ParseResult`` into a minimal structured community envelope
when the document type is classified but not one of the six premium domains.
Collects entity fields, KV pairs, and flat table rows without domain-specific logic.

Pipeline role: ``runner._run_community_extract`` calls ``build_generic_community_output``
via ``generic.community_plugin`` when generic fallback is enabled and the type is
not enterprise-only; emits ``community_generic_fallback`` warning in status.

Key exports: ``build_generic_community_output`` (and internal collectors used by
``kv_community_extract``).

Dependencies: ``build_classification_block``, ``edition_serializer``,
``core.table.access.get_logical_tables``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docmirror.models.edition_serializer import EditionContext, edition_serializer
from docmirror.models.entities.domain_result import DomainExtractionResult, DomainQuality
from docmirror.plugins._base import build_classification_block

_GENERIC_WARNING = "community_generic_fallback"


def _collect_entity_fields(parse_result: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    entities = getattr(parse_result, "entities", None)
    if entities is None:
        return fields

    raw = getattr(entities, "domain_specific", None)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if value is not None and value != "":
                fields[str(key)] = value

    raw = getattr(entities, "entities", None)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if value is not None and value != "":
                fields[str(key)] = value

    for attr in (
        "document_type",
        "period_start",
        "period_end",
        "institution",
        "account_number",
        "account_holder",
    ):
        val = getattr(entities, attr, None)
        if val is not None and val != "" and attr not in fields:
            fields[attr] = val

    for page in getattr(parse_result, "pages", []) or []:
        for kv in getattr(page, "key_values", []) or []:
            key = (getattr(kv, "key", None) or "").strip()
            val = (getattr(kv, "value", None) or "").strip()
            if key and val and key not in fields:
                fields[key] = val

    return fields


def _collect_table_records(parse_result: Any) -> list[dict[str, Any]]:
    from docmirror.core.table.access import get_logical_tables

    records: list[dict[str, Any]] = []
    logical = get_logical_tables(parse_result)
    if logical:
        tables = logical
    else:
        tables = []
        for page in getattr(parse_result, "pages", []) or []:
            tables.extend(getattr(page, "tables", []) or [])

    row_index = 0
    for table in tables:
        headers = list(getattr(table, "headers", None) or [])
        for row in getattr(table, "rows", []) or []:
            cells = [getattr(c, "text", str(c)) for c in getattr(row, "cells", [])]
            if not any(str(c).strip() for c in cells):
                continue
            row_index += 1
            if headers and len(headers) == len(cells):
                raw = {str(h): str(c) for h, c in zip(headers, cells)}
            else:
                raw = {f"col_{i}": str(c) for i, c in enumerate(cells)}
            records.append({"row_index": row_index, "raw": raw, "normalized": {}})

    return records


def _collect_structure_projected_records(parse_result: Any) -> list[dict[str, Any]]:
    """Project L1 regions via structure_project registry (Design 20 PMCC)."""
    from docmirror.core.ocr.structure_project import project_structure
    from docmirror.core.ocr.structure_projectors import core as _core  # noqa: F401

    if hasattr(parse_result, "sync_page_canvases"):
        parse_result.sync_page_canvases()

    projected: list[dict[str, Any]] = []
    for page in getattr(parse_result, "pages", []) or []:
        canvas = getattr(page, "page_canvas", None)
        if canvas is None or not canvas.blocks:
            continue
        page_num = int(getattr(page, "page_number", 0) or 0)
        region_by_id = {r.region_id: r for r in canvas.regions}
        for block in canvas.blocks:
            ref = str(block.ref or "")
            if not ref.startswith("region:"):
                continue
            region_id = ref.split(":", 1)[1]
            region = region_by_id.get(region_id)
            if region is None:
                continue
            hint = block.schema_hint or "core.field_grid.kv_block"
            result = project_structure(region.structure, page=page_num, schema_hint=hint)
            if result.rejected or result.record is None:
                continue
            projected.append(
                {
                    **result.record,
                    "block_id": block.block_id,
                    "schema_hint": hint,
                    "projection_completeness": result.completeness,
                    "missing_fields": list(result.missing_fields),
                }
            )
    return projected


def build_generic_community_output(
    parse_result: Any,
    detected_type: str,
    full_text: str = "",
) -> dict[str, Any]:
    """Build v2.0 community JSON using generic plugin presentation."""
    fields = _collect_entity_fields(parse_result)
    records = _collect_table_records(parse_result)
    structure_records = _collect_structure_projected_records(parse_result)
    if structure_records:
        records = records + structure_records
    file_path = getattr(parse_result, "file_path", "") or ""
    doc_name = Path(file_path).name if file_path else detected_type
    page_count = len(getattr(parse_result, "pages", []) or [])

    summary = {"total_rows": len(records)}
    warnings: list[str] = [_GENERIC_WARNING]
    if not fields and not records:
        warnings.append("no_fields_extracted")

    dec = DomainExtractionResult(
        document_type=detected_type,
        properties={},
        entities=fields,
        structured_data={
            "records": records,
            "structure_projected_records": structure_records,
            "summary": summary,
            "sections": [],
            "tables": [],
            "line_items": [],
        },
        quality=DomainQuality(
            validation_passed=bool(fields or records),
            issues=[f"warning:{w}" for w in warnings],
        ),
        metadata={
            "classification": build_classification_block(
                document_type=detected_type,
                domain=detected_type,
                archetype="generic_mirror",
                match_method="generic_fallback",
                text=full_text,
                scene_keywords=(),
            ),
            "plugin": {
                "name": "generic",
                "display_name": "Generic Community",
                "version": "community-2.0",
                "support_level": "generic",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    ctx = EditionContext(
        edition="community",
        detected_type=detected_type,
        full_text=full_text,
        document_name=doc_name,
        page_count=page_count,
        archetype="generic_mirror",
        domain=detected_type,
        match_method="generic_fallback",
        scene_keywords=(),
        plugin_name="generic",
        plugin_display_name="Generic Community",
        plugin_version="community-2.0",
        support_level="generic",
        parser_label="docmirror-community",
        extra_plugins={
            detected_type: {
                "display_name": detected_type,
                "edition": "community",
                "resolved_by": "generic",
            }
        },
        mirror_ref={
            "document_type": detected_type,
            "table_count": getattr(parse_result, "total_tables", 0),
            "page_count": page_count,
        },
    )
    out = edition_serializer(dec, context=ctx)
    out.setdefault("document", {})["document_type"] = detected_type
    out.setdefault("classification", {})["matched_document_type"] = detected_type
    out["classification"]["matched"] = True
    return out
