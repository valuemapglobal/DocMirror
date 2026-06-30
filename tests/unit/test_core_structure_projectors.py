# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core structure projectors (Design 20 Phase 2)."""

from __future__ import annotations

from docmirror.ocr.structure_project import project_structure
from docmirror.ocr.structure_projectors import core as _core  # noqa: F401 — registers projectors


def test_core_field_grid_projector_partial_ok():
    structure = {
        "structure_kind": "field_grid",
        "confidence": 0.8,
        "cells": [
            {"label_text": "名称", "text": "测试公司"},
            {"label_text": "代码", "text": "12345"},
        ],
    }
    result = project_structure(structure, page=1, schema_hint="core.field_grid.kv_block")
    assert not result.rejected
    assert result.record is not None
    assert result.record["fields"]["名称"] == "测试公司"
    assert result.completeness == "partial"


def test_core_micro_grid_projector():
    structure = {
        "cells": [[{"text": "2021-01", "role": "month"}, {"text": "N", "role": "status"}]],
        "confidence": 0.7,
    }
    result = project_structure(structure, page=4, schema_hint="core.micro_grid.matrix")
    assert not result.rejected
    assert result.record["rows"][0]["month"] == "2021-01"
