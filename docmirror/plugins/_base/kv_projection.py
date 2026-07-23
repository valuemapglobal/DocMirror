# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ProjectionData derivation helper for post-seal key-value projectors."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from docmirror.models.mirror.block_fields import collect_kv_fields_from_blocks
from docmirror.plugins._base.generic_community_adapter import _collect_entity_fields, _collect_table_records
from docmirror.plugins._base.projector import ProjectionData


def _match_identity_fields(
    parse_result: Any,
    identity_specs: Sequence[tuple[str, Sequence[str]]],
    entity_dict: dict[str, Any],
    full_text: str = "",
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
    if full_text:
        for key, value in _recover_identity_fields_from_text(full_text, identity_specs).items():
            out.setdefault(key, value)
    return out


def _label_pattern(label: str) -> str:
    parts = []
    for part in re.split(r"\s+", label.strip()):
        if not part:
            continue
        if re.fullmatch(r"[\u3400-\u9fff]+", part):
            parts.append(r"\s*".join(re.escape(char) for char in part))
        else:
            parts.append(re.escape(part))
    return r"\s+".join(parts)


def _recover_identity_fields_from_text(
    full_text: str,
    identity_specs: Sequence[tuple[str, Sequence[str]]],
) -> dict[str, str]:
    """Recover label/value facts when PDF extraction splits every visual word."""
    text = re.sub(r"\s+", " ", full_text or "").strip()
    if not text:
        return {}
    labels = sorted(
        {label.strip() for _field, candidates in identity_specs for label in candidates if label.strip()},
        key=len,
        reverse=True,
    )
    if not labels:
        return {}
    structural_boundaries = ("Date", "Transaction", "Description", "Amount", "Balance", "Note", "Type")
    all_boundaries = sorted({*labels, *structural_boundaries}, key=len, reverse=True)
    boundary = "|".join(_label_pattern(label) for label in all_boundaries)
    recovered: dict[str, str] = {}
    for field_name, candidates in identity_specs:
        for label in sorted(candidates, key=len, reverse=True):
            pattern = re.compile(
                rf"(?:^|\s){_label_pattern(label)}\s*[:：]?\s*(.+?)(?=\s+(?:{boundary})\s*[:：]?|$)",
                re.IGNORECASE,
            )
            match = pattern.search(text)
            if not match:
                continue
            value = match.group(1).strip(" \t:：,，;；*")
            if value and len(value) <= 500 and value.strip("*·-— "):
                recovered[field_name] = value
                break
    return recovered


def _collect_identity_field_metadata(
    parse_result: Any,
    fields: dict[str, Any],
    identity_specs: Sequence[tuple[str, Sequence[str]]],
    full_text: str = "",
) -> dict[str, Any]:
    """Preserve where each KV business field came from without wrapping its value."""
    metadata: dict[str, Any] = {}
    labels_by_field = {field: tuple(labels) for field, labels in identity_specs}
    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        for kv in getattr(page, "key_values", []) or []:
            raw_key = str(getattr(kv, "key", "") or "").strip()
            for field_name, labels in labels_by_field.items():
                if field_name not in fields or field_name in metadata:
                    continue
                if not any(label in raw_key for label in labels):
                    continue
                item: dict[str, Any] = {
                    "source": "canonical_key_value",
                    "source_label": raw_key,
                    "page": page_number,
                    "confidence": round(float(getattr(kv, "confidence", 0.0) or 0.0), 4),
                }
                bbox = getattr(kv, "bbox", None)
                if bbox:
                    item["bbox"] = list(bbox)
                evidence_ids = list(getattr(kv, "evidence_ids", []) or [])
                if evidence_ids:
                    item["evidence_ids"] = evidence_ids
                metadata[field_name] = item
    if full_text:
        for field_name in fields:
            metadata.setdefault(field_name, {"source": "full_text", "confidence": 0.7})
    return metadata


def extract_kv_projection(
    plugin: Any,
    parse_result: Any,
    *,
    identity_specs: Sequence[tuple[str, Sequence[str]]],
    full_text: str = "",
    include_block_kv: bool = True,
    include_generic_records: bool = True,
) -> ProjectionData:
    """Extract key-value facts directly without constructing an edition."""
    entity_pool = _collect_entity_fields(parse_result)
    if include_block_kv:
        for key, value in collect_kv_fields_from_blocks(parse_result).items():
            entity_pool.setdefault(key, value)
    fields = _match_identity_fields(parse_result, identity_specs, entity_pool, full_text)
    if not fields:
        fields = {key: value for key, value in entity_pool.items() if value not in (None, "")}
    field_details = _collect_identity_field_metadata(parse_result, fields, identity_specs, full_text)
    records = _collect_table_records(parse_result) if include_generic_records else []
    canonical_records = [
        {
            **dict(record),
            "record_id": str(record.get("record_id") or f"records:r{index:06d}"),
        }
        for index, record in enumerate(records, start=1)
        if isinstance(record, dict)
    ]
    evidence_ids = tuple(
        dict.fromkeys(
            str(item)
            for detail in field_details.values()
            if isinstance(detail, dict)
            for item in detail.get("evidence_ids", [])
            if str(item)
        )
    )
    return ProjectionData(
        projector_id=str(plugin.domain_name),
        document_type=str(plugin.domain_name),
        entity_fields={
            key: fields[key]
            for key in ("subject_name", "subject_id", "organization", "document_date", "period_start", "period_end")
            if fields.get(key) not in (None, "")
        },
        domain_facts={**fields, "field_details": field_details},
        datasets={"records": canonical_records} if canonical_records else {},
        warnings=() if fields or canonical_records else ("no_fields_extracted",),
        evidence_ids=evidence_ids,
        reason="post-seal key-value projection",
    )
