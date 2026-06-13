# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Lightweight document-type classification without full parse (EFPA L1 / Phase 5.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _sample_text(path: Path, *, max_chars: int = 8000) -> tuple[str, int]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PDF classification requires PyMuPDF") from exc
        doc = fitz.open(str(path))
        try:
            parts: list[str] = []
            for page in doc:
                parts.append(page.get_text())
                if sum(len(p) for p in parts) >= max_chars:
                    break
            text = "\n".join(parts)[:max_chars]
            return text, len(doc)
        finally:
            doc.close()

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        text = ""
    return text, 1


def classify_document_path(path: Path) -> dict[str, Any]:
    """Classify document type from sampled text + resolver."""
    from docmirror.core.resolution.document_type_candidates import collect_document_type_candidates
    from docmirror.core.resolution.document_type_resolver import DocumentTypeResolver
    from docmirror.models.entities.parse_result import PageContent, ParseResult

    text, page_count = _sample_text(path)
    result = ParseResult(pages=[PageContent(page_number=1)])

    candidates = collect_document_type_candidates(
        full_text=text,
        table_blocks=[],
        entities={},
        result=result,
    )
    resolver = DocumentTypeResolver()
    doc_type, decisions = resolver.resolve(candidates)
    if doc_type in ("unknown", ""):
        doc_type = "generic"

    confidence = decisions[0].final_score if decisions else 0.0
    from docmirror.core.agent.router import route_document

    route = route_document(doc_type, page_count=page_count, confidence=confidence)
    return {
        "document_type": doc_type,
        "confidence": round(confidence, 4),
        "page_count": page_count,
        "candidates": [
            {
                "document_type": c.payload.get("document_type"),
                "confidence": c.confidence,
                "method": c.method,
            }
            for c in sorted(candidates, key=lambda x: x.confidence, reverse=True)
        ],
        "route": route.model_dump(),
    }
