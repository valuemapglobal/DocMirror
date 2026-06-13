# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""RAG chunk JSON export (L10 / P6)."""

from __future__ import annotations

import json

from docmirror.core.rag.chunker import chunk_parse_result
from docmirror.models.entities.parse_result import ParseResult


def export_chunks_to_json(result: ParseResult, *, max_text_chars: int = 2000) -> str:
    """Serialize structure-aware RAG chunks."""
    chunks = chunk_parse_result(result, max_text_chars=max_text_chars)
    payload = {
        "document_type": result.entities.document_type,
        "page_count": result.page_count,
        "chunk_count": len(chunks),
        "chunks": [c.model_dump() for c in chunks],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def export_chunks_payload(result: ParseResult) -> tuple[str, str, str]:
    """Return (json_string, media_type, suffix) for API export."""
    return export_chunks_to_json(result), "application/json", ".chunks.json"
