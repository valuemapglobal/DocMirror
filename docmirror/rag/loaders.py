"""DocMirror RAG Loader — one-liner chunk extraction with source refs.

Usage::

    from docmirror.rag import load_for_rag

    docs = load_for_rag("sample.pdf", profile="compact")
    for doc in docs:
        print(doc.text)
        for ref in doc.source_refs:
            print(f"  page {ref['page']}, bbox {ref.get('bbox')}")
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docmirror.core.entry.factory import PerceiveOptions, perceive_document
from docmirror.server.edition_outputs import write_four_files
from docmirror.integration.observability import build_observability_context


@dataclass
class RAGDocument:
    """A single chunk ready for RAG ingestion.

    Attributes:
        text: The chunk text content.
        chunk_id: Unique chunk identifier (page_block_idx).
        chunk_type: Semantic type — ``text``, ``table``, ``header``, ``footer``, etc.
        page: 1-based page number.
        source_refs: List of dicts with page, bbox, evidence_id.
        metadata: Open metadata bag (language, confidence, etc.).
    """

    text: str
    chunk_id: str = ""
    chunk_type: str = "text"
    page: int = 0
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type,
            "page": self.page,
            "source_refs": self.source_refs,
            "metadata": self.metadata,
        }


def load_for_rag(
    file_path: str | Path,
    *,
    profile: str = "compact",
    mode: str = "auto",
    output_dir: str | Path = "output",
) -> list[RAGDocument]:
    """One-shot document → RAG chunks with source references.

    Args:
        file_path: Path to the document.
        profile: Output profile — ``compact`` for fast retrieval chunks,
                 ``full`` for richer metadata.
        mode: Parse mode override.
        output_dir: Output directory for artifacts.

    Returns:
        List of RAGDocument chunks, each with text and source_refs.
    """
    return _run_async(_load_for_rag_async(file_path, profile=profile, mode=mode, output_dir=output_dir))


async def _load_for_rag_async(
    file_path: str | Path,
    *,
    profile: str = "compact",
    mode: str = "auto",
    output_dir: str | Path = "output",
) -> list[RAGDocument]:
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    obs = build_observability_context(profile=profile, entry="rag")
    output = Path(output_dir)

    try:
        result = await perceive_document(path, PerceiveOptions())
    except Exception as e:
        return [RAGDocument(text=f"[Parse error: {e}]", metadata={"error": str(e)})]

    mirror = result.mirror if hasattr(result, "mirror") else result
    full_text = getattr(mirror, "full_text", "") or ""

    task_id, written = write_four_files(
        mirror,
        output,
        file_path=str(path),
        full_text=full_text,
        editions=("mirror",),
    )

    return _extract_rag_docs(output / task_id, mirror, task_id)


def _extract_rag_docs(task_dir: Path, mirror: Any, task_id: str) -> list[RAGDocument]:
    """Extract RAGDocument list from chunk artifacts or fall back to page-level text."""
    chunks_path = task_dir / "006_chunks.json"

    if chunks_path.is_file():
        try:
            chunks_data = json.loads(chunks_path.read_text(encoding="utf-8"))
            chunk_list = chunks_data if isinstance(chunks_data, list) else chunks_data.get("chunks", [])
            return [
                RAGDocument(
                    text=c.get("text", ""),
                    chunk_id=c.get("chunk_id", f"chunk_{i}"),
                    chunk_type=c.get("chunk_type", "text"),
                    page=c.get("page", 0),
                    source_refs=c.get("source_refs", []),
                    metadata=c.get("metadata", {}),
                )
                for i, c in enumerate(chunk_list)
            ]
        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: page-level extraction from mirror
    pages = getattr(mirror, "pages", [])
    docs: list[RAGDocument] = []
    for page in pages:
        page_num = getattr(page, "page_number", 0)
        text = getattr(page, "text", "") or getattr(page, "full_text", "")
        if text:
            docs.append(
                RAGDocument(
                    text=text,
                    chunk_id=f"p{page_num}",
                    chunk_type="page",
                    page=page_num,
                    source_refs=[{"page": page_num, "evidence_id": f"page_{page_num}"}],
                )
            )
    return docs


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)
