# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Merge plugin recognition results into the existing ParseResult contract.

This module deliberately does not create a domain-fact object or an edition
payload cache.  Plugins may recognize additional fields and record collections,
but ParseResult remains the only retained source consumed by output projectors.
"""

from __future__ import annotations

import re
from typing import Any

from docmirror.models.entities.parse_result import DocumentSection, ParseResult

_DATA_RESERVED = frozenset({"fields", "field_details", "sections", "tables", "data_dictionary"})
_ENTITY_FIELDS = {
    "subject_name": "subject_name",
    "subject_id": "subject_id",
    "organization": "organization",
    "document_date": "document_date",
    "period_start": "period_start",
    "period_end": "period_end",
}


def _record_id_prefix(dataset_id: str) -> str:
    prefix = re.sub(r"[^0-9A-Za-z_]+", "_", dataset_id).strip("_").lower()
    return prefix or "records"


def _canonicalize_dataset_records(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Assign deterministic record identities inside the canonical merge boundary."""
    catalog = data.get("datasets") if isinstance(data.get("datasets"), list) else []
    dataset_keys = {
        str(item.get("id"))
        for item in catalog
        if isinstance(item, dict) and item.get("id") and isinstance(data.get(str(item.get("id"))), list)
    }
    if not dataset_keys:
        dataset_keys = {
            str(key)
            for key, value in data.items()
            if key not in _DATA_RESERVED
            and key not in {"datasets", "notes", "document_flow"}
            and isinstance(value, list)
            and value
            and all(isinstance(item, dict) for item in value)
        }

    canonical: dict[str, list[dict[str, Any]]] = {}
    for key in dataset_keys:
        rows = data.get(key)
        if not isinstance(rows, list):
            continue
        prefix = _record_id_prefix(key)
        canonical_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, raw_row in enumerate(rows, start=1):
            if not isinstance(raw_row, dict):
                continue
            row = dict(raw_row)
            record_id = str(row.get("record_id") or row.get("row_id") or f"{prefix}:r{index:06d}")
            if record_id in seen:
                raise ValueError(f"duplicate canonical record_id in dataset {key}: {record_id}")
            seen.add(record_id)
            row["record_id"] = record_id
            canonical_rows.append(row)
        canonical[key] = canonical_rows
    return canonical


def _positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value or fallback)
    except (TypeError, ValueError):
        return fallback
    return max(1, parsed)


def _merge_sections(result: ParseResult, raw_sections: Any) -> None:
    if not isinstance(raw_sections, list) or not raw_sections:
        return
    sections: list[DocumentSection] = []
    for index, raw in enumerate(raw_sections, start=1):
        if not isinstance(raw, dict):
            continue
        start = _positive_int(
            raw.get("source_page_start") or raw.get("page_start") or raw.get("logical_page_start"),
            1,
        )
        end = _positive_int(
            raw.get("source_page_end") or raw.get("page_end") or raw.get("logical_page_end"),
            start,
        )
        sections.append(
            DocumentSection(
                id=str(raw.get("id") or f"section_{index}"),
                title=str(raw.get("title") or raw.get("name") or f"章节 {index}"),
                name=str(raw.get("name") or raw.get("title") or f"章节 {index}"),
                page_start=start,
                page_end=max(start, end),
                **{
                    key: value
                    for key, value in raw.items()
                    if key
                    not in {
                        "id",
                        "title",
                        "name",
                        "source_page_start",
                        "source_page_end",
                        "logical_page_start",
                        "logical_page_end",
                        "page_start",
                        "page_end",
                    }
                },
            )
        )
    if sections:
        result.sections = sections


def merge_plugin_projection_into_parse_result(
    result: ParseResult,
    payload: dict[str, Any] | None,
) -> ParseResult:
    """Merge recognized values into ParseResult and discard the payload layer."""
    if not isinstance(payload, dict):
        return result

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    document = payload.get("document") if isinstance(payload.get("document"), dict) else {}
    properties = document.get("properties") if isinstance(document.get("properties"), dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    details = data.get("field_details") if isinstance(data.get("field_details"), dict) else {}
    dictionary = data.get("data_dictionary") if isinstance(data.get("data_dictionary"), dict) else {}

    extension = dict(result.entities.domain_specific or {})
    extension.update(fields)
    canonical_datasets = _canonicalize_dataset_records(data)
    for key, value in data.items():
        if key not in _DATA_RESERVED:
            extension[str(key)] = canonical_datasets.get(str(key), value)
    for key, value in properties.items():
        extension.setdefault(str(key), value)
    if details:
        extension["field_details"] = details
    if dictionary:
        extension["data_dictionary"] = dictionary

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if metadata.get("domain_status"):
        extension["community_support_level"] = metadata["domain_status"]
    result.entities.domain_specific = extension

    detected_type = str(document.get("document_type") or document.get("domain") or "")
    if detected_type and result.entities.document_type in {"", "unknown", "generic"}:
        result.entities.document_type = detected_type
    for source_key, target_key in _ENTITY_FIELDS.items():
        value = fields.get(source_key)
        if value in (None, "") or getattr(result.entities, target_key, None) not in (None, ""):
            continue
        if isinstance(value, dict):
            value = next(
                (
                    value.get(key)
                    for key in ("normalized_value", "value", "normalized", "raw")
                    if value.get(key) not in (None, "")
                ),
                "",
            )
        if value not in (None, ""):
            setattr(result.entities, target_key, str(value))

    _merge_sections(result, data.get("sections"))

    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    for warning in [*(status.get("warnings") or []), *(status.get("errors") or [])]:
        text = str(warning or "").strip()
        if text and text not in result.parser_info.warnings:
            result.parser_info.warnings.append(text)
    return result


__all__ = ["merge_plugin_projection_into_parse_result"]
