"""RAG chunk JSON exporter."""

from __future__ import annotations

from typing import Any

from docmirror.runtime.serialization import dumps_json, to_json_safe


def export_chunks_to_json(result: Any, *, editions: dict[str, Any] | None = None, **kwargs: Any) -> str:
    sections = []
    for edition in (editions or {}).values():
        sections.extend((edition.get("data") or {}).get("sections") or [])
    from docmirror.features.rag.chunker import chunk_parse_result

    chunks = chunk_parse_result(result, sections=sections or None, **kwargs)
    payload = {
        "source": "parse_result",
        "chunk_count": len(chunks),
        "chunks": to_json_safe(chunks),
    }
    return dumps_json(payload)
