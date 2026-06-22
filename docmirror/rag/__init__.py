"""DocMirror RAG Integration — structured chunks ready for vector stores.

Provides ``load_for_rag()`` as the official one-liner for loading
Markdown, chunks, and source references from a parsed document.
"""

from docmirror.rag.loaders import load_for_rag, RAGDocument

__all__ = ["load_for_rag", "RAGDocument"]
