import json
from types import SimpleNamespace

from docmirror.output.exporters.dispatch import export_parse_result
from docmirror.output.mirror_vnext_projection import (
    export_chunks_from_vnext,
    export_markdown_from_vnext,
)


def _mirror_vnext():
    return {
        "document": {
            "document_type_candidates": [{"type": "test_document", "confidence": 1.0}],
            "root_block_ids": ["blk:heading:0001", "blk:para:0001", "blk:table:0001"],
            "primary_reading_flow_id": "flow:main",
        },
        "pages": [{"page_id": "page:0001", "page_number": 1}],
        "blocks": [
            {
                "id": "blk:header:0001",
                "type": "header",
                "role": "page_header",
                "page_ids": ["page:0001"],
                "text": "页眉文本",
                "quality": {"suppressed_from_reading_flow": True},
            },
            {
                "id": "blk:heading:0001",
                "type": "heading",
                "role": "h1",
                "page_ids": ["page:0001"],
                "text": "正文标题",
                "evidence_ids": ["ev:h"],
            },
            {
                "id": "blk:para:0001",
                "type": "paragraph",
                "role": "body",
                "page_ids": ["page:0001"],
                "text": "正文内容",
                "evidence_ids": ["ev:p"],
            },
            {
                "id": "blk:table:0001",
                "type": "table",
                "role": "table",
                "page_ids": ["page:0001"],
                "content": {
                    "grid": {
                        "columns": [{"index": 0, "header": "项目"}, {"index": 1, "header": "金额"}],
                        "rows": [{"index": 0, "role": "header"}, {"index": 1, "role": "data"}],
                        "cells": [
                            {"row_index": 0, "col_index": 0, "text": "项目"},
                            {"row_index": 0, "col_index": 1, "text": "金额"},
                            {"row_index": 1, "col_index": 0, "text": "收入"},
                            {"row_index": 1, "col_index": 1, "text": "100"},
                        ],
                    }
                },
                "evidence_ids": ["ev:t"],
            },
            {
                "id": "blk:footer:0001",
                "type": "footer",
                "role": "page_footer",
                "page_ids": ["page:0001"],
                "text": "页脚文本",
                "quality": {"suppressed_from_reading_flow": True},
            },
        ],
        "graph": {
            "reading_flows": [
                {
                    "flow_id": "flow:main",
                    "kind": "main_reading_order",
                    "node_ids": ["blk:heading:0001", "blk:para:0001", "blk:table:0001"],
                }
            ]
        },
    }


def test_export_markdown_from_vnext_uses_reading_flow_and_suppresses_header_footer():
    markdown = export_markdown_from_vnext(_mirror_vnext())

    assert "# 正文标题" in markdown
    assert "正文内容" in markdown
    assert "| 项目 | 金额 |" in markdown
    assert "| 收入 | 100 |" in markdown
    assert "页眉文本" not in markdown
    assert "页脚文本" not in markdown


def test_export_chunks_from_vnext_uses_stable_block_ids():
    chunks = export_chunks_from_vnext(_mirror_vnext())

    assert [chunk["chunk_id"] for chunk in chunks] == [
        "blk:heading:0001:chunk:0000",
        "blk:para:0001:chunk:0000",
        "blk:table:0001:chunk:0000",
    ]
    assert chunks[0]["chunk_type"] == "section"
    assert chunks[2]["chunk_type"] == "table"
    assert all("页眉文本" not in chunk["text"] for chunk in chunks)


def test_dispatch_markdown_and_chunks_can_read_mirror_vnext():
    result = SimpleNamespace(
        entities=SimpleNamespace(document_type="pipeline"),
        pages=[],
        sections=[],
        full_text="raw text",
        extractor_full_text="raw text",
    )

    markdown, markdown_media_type, markdown_suffix = export_parse_result(result, "markdown", mirror_vnext=_mirror_vnext())
    chunks_payload, chunks_media_type, chunks_suffix = export_parse_result(result, "chunks", mirror_vnext=_mirror_vnext())
    chunks = json.loads(chunks_payload)

    assert markdown_media_type == "text/markdown"
    assert markdown_suffix == ".md"
    assert "正文内容" in markdown
    assert "raw text" not in markdown
    assert chunks_media_type == "application/json"
    assert chunks_suffix == ".chunks.json"
    assert chunks["source"] == "mirror_vnext_reading_flow"
    assert chunks["chunk_count"] == 3
