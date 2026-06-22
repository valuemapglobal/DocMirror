# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""RenderableDocumentFlow — builds a document-level renderable flow from Mirror Facts.

GA 1.0 design §8.2: Markdown must be a rendering of a Document Flow, not a
page-local text concatenation. This module takes a ParseResult (or Mirror dict),
applies noise filtering, resolves cross-page continuity, and produces a list of
flow blocks ready for the Markdown Renderer.

Block types:
    heading / paragraph / list / table / formula / image / page_break / noise

Usage::

    from docmirror.exporters.document_flow import build_renderable_flow
    blocks = build_renderable_flow(result)
    for block in blocks:
        print(block.block_type, block.text[:80])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


BlockType = Literal[
    "heading",
    "paragraph",
    "list",
    "table",
    "formula",
    "image",
    "page_break",
    "noise",
]

TableFidelity = Literal["markdown", "html", "degraded"]
FormulaDegradation = Literal["latex", "raw", "omml", "unavailable"]


@dataclass
class FlowBlock:
    """A single renderable block in the document flow.

    Each block carries its type, content, source fact_ids, evidence_ids,
    and fidelity metadata so that the Markdown renderer, RAG chunker, and
    Evidence bundle can all consume the same flow.
    """

    block_type: BlockType = "paragraph"
    page: int = 1
    bbox: list[float] | None = None
    text: str = ""
    heading_level: int = 0  # 1-6 for headings, 0 for non-headings
    fact_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    reading_order: int = 0
    confidence: float = 1.0

    # Table-specific
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    table_fidelity: TableFidelity = "markdown"

    # Formula-specific
    latex: str = ""
    formula_degradation: FormulaDegradation = "unavailable"

    # Noise-specific
    noise_policy: str = ""  # excluded_from_markdown, preserved, etc.
    noise_reason: str = ""

    # Key-value support
    key_value: dict[str, str] = field(default_factory=dict)

    # Cross-page continuity
    continues_from_page: int | None = None
    continues_to_page: int | None = None

    # Evidence comment (optional)
    evidence_comment: str = ""


def build_renderable_flow(
    result: Any,
    *,
    profile: str = "human_default",
    include_evidence_comments: bool = False,
) -> list[FlowBlock]:
    """Build a renderable document flow from a ParseResult or Mirror dict.

    Args:
        result: ParseResult or dict with pages containing texts, tables, key_values, etc.
        profile: Noise suppression profile ("human_default", "rag_default", "forensic", "layout_debug").
        include_evidence_comments: If True, embed evidence comments in blocks.

    Returns:
        List of FlowBlock in reading order.
    """
    pages = _get_pages(result)

    # Detect noise for the given profile
    from docmirror.models.mirror.noise_policy import detect_repeated_noise

    noise_entries = detect_repeated_noise(pages, profile=profile)
    excluded_texts: set[tuple[int, str]] = set()
    noise_page_texts: dict[tuple[int, str], dict[str, Any]] = {}
    for noise in noise_entries:
        policy = noise.get("policy", "")
        if policy == "excluded_from_markdown":
            for p in noise.get("pages", []):
                sample = str(noise.get("text_sample", ""))
                if sample:
                    excluded_texts.add((int(p), sample))
                    noise_page_texts[(int(p), sample)] = noise

    blocks: list[FlowBlock] = []
    global_ro = 0
    prev_page = 0

    for page in pages:
        page_no = int(page.get("page_number") or 1)

        # Page break
        if prev_page > 0 and page_no > prev_page:
            blocks.append(
                FlowBlock(
                    block_type="page_break",
                    page=page_no,
                    text=f"--- page {page_no} ---",
                    reading_order=global_ro,
                )
            )
            global_ro += 1
        prev_page = page_no

        # Collect all page items
        page_items: list[tuple[int, str, Any]] = []

        for text in page.get("texts") or []:
            if not isinstance(text, dict):
                continue
            ro = int(text.get("reading_order", 0) or 0)
            page_items.append((ro, "text", text))

        for kv in page.get("key_values") or []:
            if not isinstance(kv, dict):
                continue
            ro = int(kv.get("reading_order", 0) or 0)
            page_items.append((ro, "key_value", kv))

        for tbl in page.get("tables") or []:
            if not isinstance(tbl, dict):
                continue
            ro = int(tbl.get("reading_order", 0) or 0)
            page_items.append((ro, "table", tbl))

        for fm in page.get("formulas") or []:
            if not isinstance(fm, dict):
                continue
            ro = int(fm.get("reading_order", 0) or 0)
            page_items.append((ro, "formula", fm))

        for img in page.get("images") or []:
            if not isinstance(img, dict):
                continue
            ro = int(img.get("reading_order", 0) or 0)
            page_items.append((ro, "image", img))

        page_items.sort(key=lambda x: (x[0], x[1]))

        for ro, item_type, item in page_items:
            global_ro += 1

            if item_type == "text":
                content = str(item.get("content") or "")
                role = str(item.get("mirror_role") or item.get("level") or "").lower()
                level = str(item.get("level") or "").lower()

                # Check noise exclusion
                is_excluded = (page_no, content) in excluded_texts

                if is_excluded and profile in ("human_default", "rag_default"):
                    noise_info = noise_page_texts.get((page_no, content), {})
                    blocks.append(
                        FlowBlock(
                            block_type="noise",
                            page=page_no,
                            text=content[:200],
                            fact_refs=[],
                            evidence_refs=item.get("evidence_ids") or [],
                            reading_order=global_ro,
                            confidence=float(item.get("confidence", 1.0) or 1.0),
                            noise_policy="excluded_from_markdown",
                            noise_reason=noise_info.get("type", role),
                            bbox=item.get("bbox"),
                        )
                    )
                    continue

                # Heading detection
                heading_level = 0
                if level in ("title", "h1"):
                    heading_level = 1
                elif level == "h2":
                    heading_level = 2
                elif level == "h3":
                    heading_level = 3

                block = FlowBlock(
                    block_type="heading" if heading_level > 0 else "paragraph",
                    page=page_no,
                    text=content,
                    heading_level=heading_level,
                    fact_refs=[],
                    evidence_refs=item.get("evidence_ids") or [],
                    reading_order=global_ro,
                    confidence=float(item.get("confidence", 1.0) or 1.0),
                    bbox=item.get("bbox"),
                )
                if include_evidence_comments and block.evidence_refs:
                    block.evidence_comment = f"evidence: {','.join(block.evidence_refs[:3])}"
                blocks.append(block)

            elif item_type == "key_value":
                key = str(item.get("key") or "").strip()
                value = str(item.get("value") or "").strip()
                block = FlowBlock(
                    block_type="paragraph",
                    page=page_no,
                    text=f"**{key}**: {value}" if key else value,
                    fact_refs=[],
                    evidence_refs=item.get("evidence_ids") or [],
                    reading_order=global_ro,
                    confidence=float(item.get("confidence", 1.0) or 1.0),
                    bbox=item.get("bbox"),
                    key_value={key: value} if key else {},
                )
                blocks.append(block)

            elif item_type == "table":
                headers = list(item.get("headers") or [])
                rows = _extract_table_rows(item)
                table_text = str(item.get("text", "") or "")

                # Table fidelity assessment
                fidelity: TableFidelity = "markdown"
                if _is_complex_table(headers, rows):
                    fidelity = "html"
                if not headers and not rows and not table_text:
                    fidelity = "degraded"

                block = FlowBlock(
                    block_type="table",
                    page=page_no,
                    text=table_text,
                    headers=[str(h) for h in headers],
                    rows=rows,
                    table_fidelity=fidelity,
                    fact_refs=[],
                    evidence_refs=item.get("evidence_ids") or [],
                    reading_order=global_ro,
                    confidence=float(item.get("confidence", 1.0) or 1.0),
                    bbox=item.get("bbox"),
                )
                blocks.append(block)

            elif item_type == "formula":
                latex = str(item.get("latex") or "")
                raw = str(item.get("raw") or item.get("content") or "")
                degradation: FormulaDegradation = "unavailable"
                if latex:
                    degradation = "latex"
                elif raw:
                    degradation = "raw"
                elif item.get("omml"):
                    degradation = "omml"

                block = FlowBlock(
                    block_type="formula",
                    page=page_no,
                    text=latex or raw or "[Formula]",
                    latex=latex,
                    formula_degradation=degradation,
                    fact_refs=[],
                    evidence_refs=item.get("evidence_ids") or [],
                    reading_order=global_ro,
                    confidence=float(item.get("confidence", 1.0) or 1.0),
                    bbox=item.get("bbox"),
                )
                blocks.append(block)

            elif item_type == "image":
                alt = str(item.get("alt") or item.get("caption") or "")
                block = FlowBlock(
                    block_type="image",
                    page=page_no,
                    text=alt or f"[Image on page {page_no}]",
                    fact_refs=[],
                    evidence_refs=item.get("evidence_ids") or [],
                    reading_order=global_ro,
                    confidence=float(item.get("confidence", 1.0) or 1.0),
                    bbox=item.get("bbox"),
                )
                blocks.append(block)

    return blocks


def _get_pages(result: Any) -> list[dict[str, Any]]:
    """Extract pages from a result, handling both ParseResult objects and dicts."""
    if isinstance(result, dict):
        data = result.get("data") or {}
        pages = data.get("pages") or []
        if pages:
            return pages
        # Fallback: try result["pages"] directly
        return result.get("pages") or []
    pages = list(getattr(result, "pages", []) or [])
    if pages and not isinstance(pages[0], dict):
        # ParseResult Pages -> dict
        return _pages_to_dicts(pages)
    return pages


def _pages_to_dicts(pages: list[Any]) -> list[dict[str, Any]]:
    """Convert ParseResult PageContent objects to dicts."""
    result: list[dict[str, Any]] = []
    for page in pages:
        d: dict[str, Any] = {
            "page_number": getattr(page, "page_number", 1),
            "texts": [],
            "tables": [],
            "key_values": [],
            "images": [],
            "formulas": [],
        }
        for text in getattr(page, "texts", []) or []:
            d["texts"].append({
                "content": getattr(text, "content", ""),
                "level": str(getattr(text, "level", "") or ""),
                "mirror_role": getattr(text, "mirror_role", ""),
                "reading_order": getattr(text, "reading_order", 0),
                "confidence": getattr(text, "confidence", 1.0),
                "bbox": getattr(text, "bbox", None),
                "evidence_ids": getattr(text, "evidence_ids", []),
            })
        for tbl in getattr(page, "tables", []) or []:
            d["tables"].append({
                "table_id": getattr(tbl, "table_id", ""),
                "headers": list(getattr(tbl, "headers", []) or []),
                "data_rows": list(getattr(tbl, "data_rows", []) or getattr(tbl, "rows", []) or []),
                "reading_order": getattr(tbl, "reading_order", 0),
                "confidence": getattr(tbl, "confidence", 1.0),
                "bbox": getattr(tbl, "bbox", None),
                "evidence_ids": getattr(tbl, "evidence_ids", []),
                "text": getattr(tbl, "text", ""),
            })
        for kv in getattr(page, "key_values", []) or []:
            d["key_values"].append({
                "key": getattr(kv, "key", ""),
                "value": getattr(kv, "value", ""),
                "reading_order": getattr(kv, "reading_order", 0),
                "confidence": getattr(kv, "confidence", 1.0),
                "bbox": getattr(kv, "bbox", None),
                "evidence_ids": getattr(kv, "evidence_ids", []),
            })
        result.append(d)
    return result


def _extract_table_rows(table: dict[str, Any]) -> list[list[str]]:
    """Extract rows from a table dict, handling both data_rows and rows."""
    rows: list[list[str]] = []
    data_rows = table.get("data_rows") or table.get("rows") or []
    for row in data_rows:
        if isinstance(row, dict):
            cells = row.get("cells") or []
            row_texts = []
            for cell in cells:
                if isinstance(cell, dict):
                    row_texts.append(str(cell.get("cleaned") or cell.get("text") or ""))
                else:
                    row_texts.append(str(getattr(cell, "cleaned", None) or getattr(cell, "text", "") or ""))
            rows.append(row_texts)
        elif hasattr(row, "cells"):
            row_texts = []
            for cell in getattr(row, "cells", []) or []:
                row_texts.append(str(getattr(cell, "cleaned", None) or getattr(cell, "text", "") or ""))
            rows.append(row_texts)
    return rows


def _is_complex_table(headers: list[str], rows: list[list[str]]) -> bool:
    """Determine if a table is too complex for simple markdown rendering.

    Criteria:
    - More than 8 columns
    - Cells with multi-line content (> 200 chars)
    - Merged cell indicators (empty cells in non-empty rows)
    - More than 50 rows
    """
    if not rows:
        return False
    width = max(len(h or []) for h in [headers, *rows])
    if width > 8:
        return True
    for row in rows:
        for cell in row:
            if len(cell) > 200 or "\n" in cell:
                return True
    if len(rows) > 50:
        return True
    empty_cells = sum(1 for row in rows for cell in row if not cell.strip())
    total_cells = sum(len(row) for row in rows)
    if total_cells > 0 and empty_cells / total_cells > 0.3:
        return True
    return False


__all__ = [
    "build_renderable_flow",
    "FlowBlock",
    "BlockType",
    "TableFidelity",
    "FormulaDegradation",
]
