# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""RAG chunker edition section integration."""

from __future__ import annotations

import json
from unittest.mock import PropertyMock, patch

from docmirror.exporters.rag_chunks import export_chunks_to_json
from docmirror.features.rag.chunker import chunk_parse_result
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus


def test_chunk_parse_result_uses_edition_sections():
    text = "Enterprise Section\nbody text here"
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type="credit_report")
    sections = [{"id": "ent", "title": "Enterprise Section", "page_start": 1}]
    with patch.object(type(pr), "full_text", new_callable=PropertyMock, return_value=text):
        chunks = chunk_parse_result(pr, sections=sections, max_text_chars=500)
    assert any(c.chunk_type == "section" for c in chunks)


def test_export_chunks_json_reads_edition_sections():
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type="credit_report")
    text = "Enterprise Section\nbody text here"
    editions = {
        "enterprise": {
            "data": {"sections": [{"id": "ent", "title": "Enterprise Section", "page_start": 1}]}
        }
    }
    with patch.object(type(pr), "full_text", new_callable=PropertyMock, return_value=text):
        payload = json.loads(export_chunks_to_json(pr, editions=editions))
    assert payload["chunk_count"] >= 1
