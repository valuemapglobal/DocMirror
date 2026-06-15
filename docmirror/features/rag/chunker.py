# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""
Structure-aware RAG chunker for retrieval-augmented generation (L10 / P6).

Splits a completed ``ParseResult`` into semantically coherent ``RagChunk``
records that respect headings, paragraphs, tables, and page boundaries.
Chunks carry stable IDs, source provenance, and optional embedding metadata
fields for downstream vector stores.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from docmirror.models.entities.parse_result import ParseResult, TableBlock


class RagChunk(BaseModel):
    """One retrievable unit for RAG / Agent pipelines."""

    chunk_id: str
    text: str
    page: int = 1
    chunk_type: Literal["text", "table", "section", "kv"] = "text"
    section_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _table_to_markdown(table: TableBlock) -> str:
    rows: list[list[str]] = []
    if table.headers:
        rows.append([str(h or "") for h in table.headers])
    for row in table.data_rows or table.rows or []:
        rows.append([str(c.cleaned or c.text or "") for c in row.cells])
    if not rows:
        return ""
    headers = rows[0]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows[1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        lines.append("| " + " | ".join(padded[: len(headers)]) + " |")
    return "\n".join(lines)


def _split_text(text: str, *, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    idx = 0
    while idx < len(text):
        end = min(idx + max_chars, len(text))
        if end < len(text):
            nl = text.rfind("\n", idx, end)
            if nl > idx:
                end = nl + 1
        parts.append(text[idx:end].strip())
        if end >= len(text):
            break
        idx = max(end - overlap, idx + 1)
    return [p for p in parts if p]


def chunk_parse_result(
    result: ParseResult,
    *,
    max_text_chars: int = 2000,
    overlap: int = 200,
) -> list[RagChunk]:
    """Build structure-aware chunks from mirror pages, sections, and tables."""
    chunks: list[RagChunk] = []
    full_text = result.extractor_full_text or result.full_text or ""

    if result.sections and full_text:
        for sec in result.sections:
            title = str(sec.get("title") or sec.get("name") or "").strip()
            if not title:
                continue
            start = full_text.find(title)
            if start < 0:
                continue
            end = len(full_text)
            for other in result.sections:
                other_title = str(other.get("title") or other.get("name") or "").strip()
                if other_title and other_title != title:
                    pos = full_text.find(other_title, start + len(title))
                    if 0 <= pos < end:
                        end = pos
            body = full_text[start:end].strip()
            if not body:
                continue
            sec_id = str(sec.get("id") or title)
            for part_idx, part in enumerate(_split_text(body, max_chars=max_text_chars, overlap=overlap)):
                chunks.append(
                    RagChunk(
                        chunk_id=f"sec_{sec_id}_{part_idx}",
                        text=part,
                        page=int(sec.get("page_start") or 1),
                        chunk_type="section",
                        section_id=sec_id,
                        metadata={"title": title, "part": part_idx},
                    )
                )

    for page in result.pages:
        page_no = page.page_number or 1
        ordered: list[tuple[int, str, Any]] = []
        for text in page.texts:
            ordered.append((text.reading_order, "text", text))
        for table in page.tables:
            ordered.append((table.reading_order, "table", table))
        for kv in page.key_values:
            ordered.append((kv.reading_order, "kv", kv))
        ordered.sort(key=lambda x: x[0])

        for _, kind, item in ordered:
            if kind == "text":
                content = str(getattr(item, "content", "") or "").strip()
                if not content:
                    continue
                for part_idx, part in enumerate(_split_text(content, max_chars=max_text_chars, overlap=overlap)):
                    chunks.append(
                        RagChunk(
                            chunk_id=f"p{page_no}_t_{uuid.uuid4().hex[:8]}",
                            text=part,
                            page=page_no,
                            chunk_type="text",
                            evidence_ids=list(getattr(item, "evidence_ids", []) or []),
                            metadata={
                                "level": getattr(item, "level", None),
                                "mirror_role": getattr(item, "mirror_role", ""),
                                "part": part_idx,
                            },
                        )
                    )
            elif kind == "table":
                md = _table_to_markdown(item)
                if not md:
                    continue
                chunks.append(
                    RagChunk(
                        chunk_id=f"p{page_no}_tbl_{getattr(item, 'table_id', uuid.uuid4().hex[:8])}",
                        text=md,
                        page=page_no,
                        chunk_type="table",
                        evidence_ids=list(getattr(item, "evidence_ids", []) or []),
                        metadata={
                            "table_id": getattr(item, "table_id", ""),
                            "method": getattr(item, "method", ""),
                            "rows": len(getattr(item, "data_rows", []) or []),
                        },
                    )
                )
            elif kind == "kv":
                key = str(getattr(item, "key", "") or "")
                val = str(getattr(item, "value", "") or "")
                if not key and not val:
                    continue
                chunks.append(
                    RagChunk(
                        chunk_id=f"p{page_no}_kv_{uuid.uuid4().hex[:8]}",
                        text=f"{key}: {val}".strip(": "),
                        page=page_no,
                        chunk_type="kv",
                        evidence_ids=list(getattr(item, "evidence_ids", []) or []),
                        metadata={"key": key, "group_id": getattr(item, "group_id", None)},
                    )
                )

    if not chunks and full_text.strip():
        for part_idx, part in enumerate(_split_text(full_text, max_chars=max_text_chars, overlap=overlap)):
            chunks.append(
                RagChunk(
                    chunk_id=f"full_{part_idx}",
                    text=part,
                    page=1,
                    chunk_type="text",
                    metadata={"fallback": "full_text"},
                )
            )
    return chunks
