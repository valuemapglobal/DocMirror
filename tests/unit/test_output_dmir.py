# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for DMIR serializer and projection engine."""

from __future__ import annotations

import json

import pytest

from docmirror.output.dmir import DMIR_VERSION, serialize_dmir, serialize_dmir_json
from docmirror.output.exporters.dispatch import export_dmir, EXPORTER_REGISTRY
from docmirror.output.projection.engine import (
    ProjectionEngine,
    _resolve_jsonpath,
    _transform_table_to_markdown,
)


def _fake_parse_result():
    """Build a minimal fake ParseResult for testing."""
    from unittest.mock import MagicMock

    pr = MagicMock()
    pr.entities.document_type = "test_report"
    pr.entities.organization = "Test Corp"
    pr.entities.subject_name = "Test Subject"
    pr.entities.subject_id = "ID-001"
    pr.entities.document_date = "2026-06-01"
    pr.entities.period_start = "2026-01-01"
    pr.entities.period_end = "2026-06-01"
    pr.confidence = 0.95
    pr.trust = MagicMock()
    pr.trust.trust_score = 0.92
    pr.trust.validation_passed = True
    pr.trust.is_forged = False
    pr.trust.forgery_reasons = []
    pr.parser_info.parser_name = "DocMirror-Test"
    pr.parser_info.parser_version = "1.0.0"
    pr.parser_info.elapsed_ms = 42.5
    pr.parser_info.page_count = 2
    from docmirror.models.entities.parse_result import ExtractionMethod
    pr.parser_info.extraction_method = ExtractionMethod.DIGITAL
    pr.parser_info.ocr_engine = ""
    pr.parser_info.table_engine = "pymupdf"
    pr.parser_info.overall_confidence = 0.95
    pr.parser_info.warnings = []
    pr.pages = []
    pr.total_tables = 0
    pr.total_rows = 0
    pr.full_text = "Test document content"
    pr.extractor_full_text = "Test document content"
    pr.logical_tables = []
    pr.sections = []
    return pr


def test_dmir_version():
    assert DMIR_VERSION == "1.0"


def test_serialize_dmir_structure():
    pr = _fake_parse_result()
    dmir = serialize_dmir(pr)

    assert dmir["dmir_version"] == "1.0"
    assert "document" in dmir
    assert "quality" in dmir
    assert "evidence" in dmir
    assert "meta" in dmir

    # Document section
    doc = dmir["document"]
    assert doc["type"] == "test_report"
    assert doc["properties"]["organization"] == "Test Corp"

    # Quality section
    q = dmir["quality"]
    assert q["confidence"] == 0.95
    assert q["trust_score"] == 0.92

    # Meta section
    meta = dmir["meta"]
    assert meta["parser"] == "DocMirror-Test"
    assert meta["page_count"] == 2
    assert meta["dmir_version"] == "1.0"


def test_serialize_dmir_json():
    pr = _fake_parse_result()
    json_str = serialize_dmir_json(pr)
    parsed = json.loads(json_str)
    assert parsed["dmir_version"] == "1.0"
    assert parsed["document"]["type"] == "test_report"


def test_export_dmir_via_registry():
    """Verify dmir format is registered and callable."""
    assert "dmir" in EXPORTER_REGISTRY.formats()

    pr = _fake_parse_result()
    payload, media_type, suffix = EXPORTER_REGISTRY.export(pr, "dmir")
    assert media_type == "application/json"
    assert suffix == ".dmir.json"
    parsed = json.loads(payload)
    assert parsed["dmir_version"] == "1.0"


def test_export_dmir_direct():
    pr = _fake_parse_result()
    payload, media_type, suffix = export_dmir(pr)
    assert media_type == "application/json"
    assert suffix == ".dmir.json"


class TestProjectionEngine:
    """Tests for the schema-driven projection engine."""

    def setup_method(self):
        self.engine = ProjectionEngine()
        self.mock_dmir = {
            "dmir_version": "1.0",
            "document": {
                "type": "bank_statement",
                "properties": {"organization": "Bank", "subject_name": "Client"},
                "pages": [
                    {
                        "page_number": 1,
                        "tables": [
                            {
                                "table_id": "t1",
                                "headers": ["A", "B"],
                                "data_rows": [
                                    {
                                        "cells": [
                                            {"text": "x", "data_type": "text"},
                                            {"text": "1", "data_type": "number"},
                                        ],
                                        "row_type": "data",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "full_text": "Statement content",
            },
            "quality": {"confidence": 0.97, "trust_score": 0.95, "validation_passed": True},
            "evidence": {"ledger": [], "summary": {}},
            "meta": {"parser": "DocMirror", "version": "1.0", "elapsed_ms": 50, "page_count": 1, "table_count": 1, "row_count": 1, "extraction_method": "digital", "ocr_engine": "", "table_engine": "", "overall_confidence": 0.97, "warnings": [], "dmir_version": "1.0"},
        }

    def test_templates_available(self):
        templates = self.engine.templates_available()
        assert "langchain" in templates
        assert "llamaindex" in templates
        assert "haystack" in templates
        assert "spring-ai" in templates
        assert "semantic-kernel" in templates

    def test_langchain_projection(self):
        result = self.engine.project_to_dict(self.mock_dmir, "langchain")
        assert result["page_content"] == "Statement content"
        meta = result["metadata"]
        assert meta["document_type"] == "bank_statement"
        assert meta["confidence"] == 0.97
        assert meta["organization"] == "Bank"
        assert "tables_markdown" in meta

    def test_llamaindex_projection(self):
        result = self.engine.project_to_dict(self.mock_dmir, "llamaindex")
        assert result["text"] == "Statement content"
        ei = result["extra_info"]
        assert ei["document_type"] == "bank_statement"

    def test_haystack_projection(self):
        result = self.engine.project_to_dict(self.mock_dmir, "haystack")
        assert result["content"] == "Statement content"
        assert result["meta"]["confidence"] == 0.97

    def test_code_generation(self):
        code = self.engine.project(self.mock_dmir, "langchain")
        assert "Document(" in code
        assert "page_content=" in code

    def test_imports(self):
        imports = self.engine.project_imports("langchain")
        assert any("langchain_core.documents" in imp for imp in imports)
        assert any("Document" in imp for imp in imports)

    def test_jsonpath_resolve_simple(self):
        data = {"a": {"b": {"c": "hello"}}}
        assert _resolve_jsonpath(data, "$.a.b.c") == "hello"

    def test_jsonpath_resolve_wildcard(self):
        data = {"pages": [{"tables": [{"id": 1}, {"id": 2}]}]}
        result = _resolve_jsonpath(data, "$.pages[*].tables")
        assert result == [{"id": 1}, {"id": 2}]

    def test_jsonpath_resolve_nonexistent(self):
        data = {"a": 1}
        assert _resolve_jsonpath(data, "$.x.y.z") is None

    def test_table_to_markdown(self):
        tables = [
            {
                "headers": ["Date", "Amount"],
                "data_rows": [
                    {"cells": [{"text": "2026-01-15"}, {"text": "100"}]}
                ],
            }
        ]
        md = _transform_table_to_markdown(tables)
        assert "Date" in md
        assert "Amount" in md
        assert "100" in md

    def test_table_to_markdown_empty(self):
        assert _transform_table_to_markdown([]) == ""
        assert _transform_table_to_markdown(None) == ""
