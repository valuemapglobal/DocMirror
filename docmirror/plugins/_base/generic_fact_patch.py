# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CanonicalPatch construction for generic document recognition."""

from __future__ import annotations

from typing import Any

from docmirror.input.canonical.fact_patch import CanonicalPatch


def make_generic_fact_patch(
    detected_type: str,
    fields: dict[str, Any],
    structured_data: dict[str, Any],
    warnings: list[str],
) -> CanonicalPatch:
    records = structured_data["records"]
    canonical_records = [
        {**dict(record), "record_id": str(record.get("record_id") or f"records:r{index:06d}")}
        for index, record in enumerate(records, start=1)
        if isinstance(record, dict)
    ]
    return CanonicalPatch(
        capability_id="generic",
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
        reason="native generic recognizer facts",
    )


def build_generic_fact_patch(parse_result: Any, detected_type: str, full_text: str = "") -> CanonicalPatch:
    """Run generic recognition and return facts without edition serialization."""
    from docmirror.plugins._base.generic_community_adapter import recognize_generic_facts

    patch = recognize_generic_facts(parse_result, detected_type, full_text)
    if not isinstance(patch, CanonicalPatch):
        raise TypeError("generic fact recognition did not return CanonicalPatch")
    return patch
