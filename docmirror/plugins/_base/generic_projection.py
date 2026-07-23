# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ProjectionData construction for the generic post-seal projector."""

from __future__ import annotations

from typing import Any

from docmirror.plugins._base.projector import ProjectionData


def make_generic_projection(
    detected_type: str,
    fields: dict[str, Any],
    structured_data: dict[str, Any],
    warnings: list[str],
) -> ProjectionData:
    records = structured_data["records"]
    canonical_records = [
        {**dict(record), "record_id": str(record.get("record_id") or f"records:r{index:06d}")}
        for index, record in enumerate(records, start=1)
        if isinstance(record, dict)
    ]
    return ProjectionData(
        projector_id="generic",
        document_type=detected_type,
        entity_fields={
            key: fields[key]
            for key in ("subject_name", "subject_id", "organization", "document_date", "period_start", "period_end")
            if fields.get(key) not in (None, "")
        },
        domain_facts={
            **fields,
            "field_details": structured_data["field_metadata"],
            "summary": structured_data["summary"],
            "normalized_fields": structured_data["normalized_fields"],
            "field_schema": structured_data["field_schema"],
            "columns": structured_data.get("columns", {}),
            "identities": structured_data.get("identities", {}),
        },
        datasets={"records": canonical_records} if canonical_records else {},
        sections=tuple(dict(section) for section in structured_data["sections"]),
        warnings=tuple(warnings),
        reason="post-seal generic projection",
    )


def build_generic_projection(parse_result: Any, detected_type: str, full_text: str = "") -> ProjectionData:
    """Derive generic projection data from a sealed read view."""
    from docmirror.plugins._base.generic_community_adapter import derive_generic_projection

    projection = derive_generic_projection(parse_result, detected_type, full_text)
    if not isinstance(projection, ProjectionData):
        raise TypeError("generic projector did not return ProjectionData")
    return projection
