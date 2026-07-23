# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import docmirror.plugins.credit_report.structure_projectors  # noqa: F401 — register projectors
from docmirror.ocr.structure_project import (
    completeness_level,
    finalize_partial_record,
    infer_schema_hint_v2,
    project_structure,
    projection_confidence,
)
from docmirror.plugins.credit_report.account_structure import _account_from_field_grid


def test_completeness_partial_below_threshold():
    assert completeness_level(2, expected=10) == "partial"
    assert completeness_level(6, expected=10) == "complete"
    assert completeness_level(0, expected=10) == "empty"


def test_finalize_partial_record_emits_with_two_fields_and_anchor():
    record = {
        "anchor": {"value": "账户1"},
        "account_status": {"value": "结清"},
        "close_date": {"value": "2021.02.23"},
        "audit": {},
        "confidence": 0.5,
    }
    out = finalize_partial_record(
        record,
        field_count=2,
        expected_fields=["account_status", "close_date", "open_date"],
        mapped_fields=["account_status", "close_date"],
        base_confidence=0.5,
        anchor_present=True,
    )
    assert out is not None
    assert out["audit"]["field_count"] == 2
    assert out["audit"]["projection_completeness"] == "partial"
    assert "open_date" in out["audit"]["missing_fields"]


def test_partial_field_grid_account_projects_via_registry():
    structure = {
        "structure_kind": "field_grid",
        "structure_id": "ls_p4_closed_0",
        "page": 4,
        "confidence": 0.72,
        "bbox": [72, 120, 730, 200],
        "anchors": ("账户1",),
        "nodes": [{"node_id": "n0", "role": "anchor", "text": "账户1"}],
        "cells": [
            {
                "cell_id": "c_status",
                "label_text": "账户状态",
                "text": "结清",
                "raw_text": "结清",
                "bbox": [180, 145, 260, 165],
                "geometry_status": "exact",
                "inferred_types": ["text"],
            },
            {
                "cell_id": "c_close",
                "label_text": "账户关闭日期",
                "text": "2021.02.23",
                "raw_text": "2021.02.23",
                "bbox": [400, 172, 500, 190],
                "geometry_status": "exact",
                "inferred_types": ["date"],
            },
        ],
    }
    direct = _account_from_field_grid(structure, page=4)
    assert direct is not None
    assert direct["audit"]["projection_completeness"] == "partial"
    assert direct["account_status"]["value"] == "结清"

    hint = infer_schema_hint_v2(structure, document_type="credit_report")
    assert hint == "credit.field_grid.account"
    projected = project_structure(structure, page=4, schema_hint=hint)
    assert not projected.rejected
    assert projected.record is not None
    assert projected.completeness == "partial"


def test_projection_confidence_scales_with_field_coverage():
    low = projection_confidence(base_confidence=0.8, field_count=1, expected=10)
    high = projection_confidence(base_confidence=0.8, field_count=8, expected=10)
    assert high > low
