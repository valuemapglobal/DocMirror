# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for JSON-safe mirror/debug serialization."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum

import pytest

from docmirror.input.bridge.parse_result_bridge import ParseResultBridge
from docmirror.models.entities.domain import BaseResult
from docmirror.models.entities.parse_result import (
    DocumentSection,
    ParseResult,
    ResultStatus,
    TableOperation,
)
from docmirror.runtime.debug_artifact import build_debug_artifact, write_debug_artifact
from docmirror.runtime.serialization import assert_json_serializable, dumps_json, to_json_safe


class _SampleEnum(str, Enum):
    A = "alpha"


def test_to_json_safe_coerces_pydantic_enum_and_datetime():
    payload = {
        "when": datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
        "section": DocumentSection(id="1.1", title="Summary", page_start=2, level=2),
        "tag": _SampleEnum.A,
        "nested": [{"op": TableOperation(logical_id="lt_1", merge_method="span")}],
    }
    safe = to_json_safe(payload)
    json.dumps(safe)
    assert safe["section"]["title"] == "Summary"
    assert safe["tag"] == "alpha"
    assert safe["nested"][0]["op"]["logical_id"] == "lt_1"


def test_to_mirror_json_vnext_always_json_serializable():
    pr = ParseResult(
        sections=[
            DocumentSection(id="1", title="Account", page_start=1, level=1, line_count=8),
        ],
        table_operations=[
            TableOperation(logical_id="lt_0", merge_method="concat", source_pages=[1, 2]),
        ],
    )
    pr.entities.document_type = "bank_statement"
    pr.entities.domain_specific = {"currency": "CNY", "institution": "中国银行"}

    api = pr.to_mirror_json_vnext()
    assert_json_serializable(api)
    assert "sections" not in api
    assert "meta" not in api
    assert api["source"]["provenance"]["sections"][0]["level"] == 1


def test_bridge_section_metadata_survives_to_mirror_json_vnext():
    base = BaseResult(
        pages=(),
        metadata={
            "sections": [
                {"id": "1", "title": "Header", "page_start": 1, "level": 1, "line_count": 3},
            ],
        },
    )
    pr = ParseResultBridge.from_base_result(base)
    api = pr.to_mirror_json_vnext()
    dumps_json(api)


def test_debug_artifact_serializes_sections_and_table_operations(tmp_path):
    pr = ParseResult(
        sections=[DocumentSection(id="1", title="Credit summary", page_start=1)],
        table_operations=[TableOperation(logical_id="lt_x", merge_method="merge")],
    )
    pr.entities.document_type = "credit_report"

    artifact = build_debug_artifact(pr)
    assert_json_serializable(artifact)

    out = tmp_path / "debug.json"
    write_debug_artifact(pr, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["sections"][0]["title"] == "Credit summary"
    assert loaded["table_operations"][0]["logical_id"] == "lt_x"


def test_failed_parse_result_to_mirror_json_vnext_is_json_safe():
    from docmirror.models.entities.parse_result import ErrorDetail

    pr = ParseResult(
        status=ResultStatus.FAILURE,
        error=ErrorDetail(code="parse_error", message="boom"),
        sections=[DocumentSection(id="1", title="orphan", page_start=1)],
    )
    api = pr.to_mirror_json_vnext()
    dumps_json(api)
