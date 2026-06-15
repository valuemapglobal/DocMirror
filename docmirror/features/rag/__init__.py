"""
RAG asset layer (L10) — chunking utilities for vector indexing.

Re-exports ``RagChunk`` and ``chunk_parse_result`` so retrieval pipelines
can turn DocMirror parse output into embedding-ready segments without
re-implementing layout heuristics.
"""

from docmirror.features.rag.chunker import RagChunk, chunk_parse_result

__all__ = ["RagChunk", "chunk_parse_result"]
