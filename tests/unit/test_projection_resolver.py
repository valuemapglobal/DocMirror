# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for compact projection_lineage generation."""

from __future__ import annotations

from docmirror.output.projection_resolver import build_projection_lineage


def _bank_payload(*, records: list[dict]) -> dict:
    return {
        "edition": "community",
        "plugin": {"name": "bank_statement"},
        "data": {"fields": {}, "records": records},
        "metadata": {
            "domain": "bank_statement",
            "support_level": "L2",
            "source_fact_ids": ["cell:p1:t0:r0:c0"],
            "evidence_ids": ["ev:cell:p1:t0:r0:c0"],
        },
        "quality": {"confidence": 0.9},
    }


def test_record_lineages_omitted_when_records_have_no_source_refs():
    records = [
        {"row_index": i, "raw": {"amount": str(i)}, "normalized": {"amount": float(i)}}
        for i in range(200)
    ]
    lineage = build_projection_lineage(_bank_payload(records=records))

    assert lineage["record_lineages"] == []
    assert lineage["projection_summary"]["total_records"] == 200
    assert lineage["projection_summary"]["materialized_record_lineages"] == 0
    assert lineage["projection_summary"]["record_lineage_scope"] == "edition_level"
    assert lineage["edition_lineage"]["source_fact_ids"] == ["cell:p1:t0:r0:c0"]


def test_record_lineages_materialized_only_for_records_with_source_refs():
    records = [
        {"row_index": 1, "raw": {}, "normalized": {}},
        {
            "row_index": 2,
            "raw": {},
            "normalized": {},
            "source_fact_ids": ["cell:p2:t0:r1:c0"],
            "evidence_ids": ["ev:cell:p2:t0:r1:c0"],
        },
    ]
    lineage = build_projection_lineage(_bank_payload(records=records))

    assert len(lineage["record_lineages"]) == 1
    assert lineage["record_lineages"][0]["target"] == "community.data.records[1]"
    assert lineage["projection_summary"]["materialized_record_lineages"] == 1
    assert "record_lineage_scope" not in lineage["projection_summary"]


def test_field_lineages_do_not_duplicate_edition_fact_ids():
    payload = {
        "edition": "community",
        "plugin": {"name": "business_license"},
        "data": {
            "fields": {
                "company_name": {
                    "raw_value": "Acme",
                    "normalized_value": "Acme",
                },
                "unified_social_credit_code": {
                    "raw_value": "91310000",
                    "normalized_value": "91310000",
                    "source_refs": [{"page": 1, "bbox": [0, 0, 1, 1]}],
                },
            },
            "records": [],
        },
        "metadata": {
            "domain": "business_license",
            "support_level": "L2",
            "source_fact_ids": [f"cell:p1:t0:r0:c{i}" for i in range(50)],
            "evidence_ids": [f"ev:cell:p1:t0:r0:c{i}" for i in range(50)],
        },
        "quality": {"confidence": 0.95},
    }

    lineage = build_projection_lineage(payload)

    assert len(lineage["field_lineages"]) == 1
    assert lineage["field_lineages"][0]["target"] == "community.data.fields.unified_social_credit_code"
    assert lineage["field_lineages"][0]["source_fact_ids"] == []
    assert lineage["projection_summary"]["total_fields"] == 2
    assert lineage["projection_summary"]["materialized_field_lineages"] == 1
