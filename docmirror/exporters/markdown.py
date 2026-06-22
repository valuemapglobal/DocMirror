# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Product Markdown exporter for ParseResult — v2 with DFG reading_flow support.

DFG-aware export reads ``document_structure.reading_flow`` for ordering,
renders formula blocks as LaTeX, and includes image references.
Legacy page-local ordering is preserved via ``--legacy-structure-renderer`` flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from docmirror.models.entities.parse_result import ParseResult, TableBlock, TextLevel


@dataclass(frozen=True)
class MarkdownExportOptions:
    include_page_breaks: bool = False
    include_headers_footers: bool = False
    table_format: Literal["markdown", "html"] = "markdown"
    formula_format: Literal["latex", "raw"] = "latex"
    evidence_comments: bool = False
    legacy_structure_renderer: bool = False


def _clean_cell(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def table_to_markdown(table: TableBlock) -> str:
    rows: list[list[str]] = []
    if table.headers:
        rows.append([_clean_cell(h) for h in table.headers])
    for row in table.data_rows or table.rows or []:
        rows.append([_clean_cell(c.cleaned or c.text) for c in row.cells])
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header = rows[0]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _text_heading_prefix(level: object) -> str:
    if level in (TextLevel.TITLE, TextLevel.H1, "title", "h1"):
        return "# "
    if level in (TextLevel.H2, "h2"):
        return "## "
    if level in (TextLevel.H3, "h3"):
        return "### "
    return ""


def export_markdown(result: ParseResult, *, options: MarkdownExportOptions | None = None) -> str:
    opts = options or MarkdownExportOptions()
    parts: list[str] = []
    for page in result.pages:
        page_parts: list[tuple[int, str]] = []
        for text in page.texts:
            role = str(getattr(text, "mirror_role", "") or getattr(text, "level", "") or "").lower()
            if not opts.include_headers_footers and role in {"header", "footer", "watermark"}:
                continue
            content = str(getattr(text, "content", "") or "").strip()
            if not content:
                continue
            page_parts.append(
                (int(getattr(text, "reading_order", 0) or 0), f"{_text_heading_prefix(text.level)}{content}")
            )
        for kv in page.key_values:
            key = str(getattr(kv, "key", "") or "").strip()
            value = str(getattr(kv, "value", "") or "").strip()
            if key or value:
                page_parts.append((int(getattr(kv, "reading_order", 0) or 0), f"**{key}**: {value}".strip()))
        for table in page.tables:
            rendered = table_to_markdown(table)
            if rendered:
                page_parts.append((int(getattr(table, "reading_order", 0) or 0), rendered))
        page_parts.sort(key=lambda item: item[0])
        if opts.include_page_breaks and parts and page_parts:
            parts.append(f"\n<!-- page:{page.page_number} -->\n")
        parts.extend(part for _, part in page_parts if part)
    if not parts and result.full_text.strip():
        return result.full_text.strip()
    return "\n\n".join(parts).strip() + ("\n" if parts else "")

def export_markdown_v2(
    result: ParseResult,
    *,
    options: MarkdownExportOptions | None = None,
    document_structure: dict[str, Any] | None = None,
) -> str:
    """Export Markdown using DFG reading_flow for ordering — GA 1.0 v2 path.

    When ``options.legacy_structure_renderer`` is True, falls back to
    page-local ordering (identical to ``export_markdown``).

    DFG integration:
    - Reads ``reading_flow:main`` node_ids to determine output order.
    - Excludes nodes in ``excluded_node_ids`` (headers, footers, watermarks).
    - Renders formula nodes as ``$...$`` / ``$$...$$``.
    - Includes image nodes as ``[Image: id]`` references.
    """
    opts = options or MarkdownExportOptions()

    # Legacy path — same as export_markdown
    if opts.legacy_structure_renderer:
        return export_markdown(result, options=opts)

    # Build DFG if not provided
    if document_structure is None:
        from docmirror.models.mirror.document_structure import build_document_structure

        document_structure = build_document_structure(result, profile="ga_full")

    # Build node lookup by node_id
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in document_structure.get("nodes") or []:
        nodes_by_id[node.get("node_id", "")] = node

    # Read main reading_flow
    reading_flows = document_structure.get("reading_flow") or []
    main_flow: dict[str, Any] | None = None
    for rf in reading_flows:
        if rf.get("type") == "main_reading_order":
            main_flow = rf
            break

    parts: list[str] = []

    if main_flow:
        node_ids = main_flow.get("node_ids") or []
        excluded = set(main_flow.get("excluded_node_ids") or [])

        # Filter excluded based on options
        if not opts.include_headers_footers:
            node_ids = [nid for nid in node_ids if nid not in excluded]

        last_page: int | None = None
        for nid in node_ids:
            node = nodes_by_id.get(nid)
            if node is None:
                continue

            node_type = node.get("type", "paragraph")
            text = node.get("text", "")
            page = node.get("page", 1)

            # Optional page breaks
            if opts.include_page_breaks and last_page is not None and page != last_page:
                parts.append(f"\n<!-- page:{page} -->\n")
            last_page = page

            if node_type == "heading":
                level = node.get("metadata", {}).get("heading_level", 1)
                prefix = "#" * min(int(level), 6) + " "
                parts.append(f"{prefix}{text}" if text else "")
            elif node_type == "paragraph":
                if text.strip():
                    parts.append(text)
            elif node_type == "list_item":
                parts.append(f"- {text}")
            elif node_type in ("physical_table", "logical_table"):
                table_md = _render_table_from_node(node, result)
                if table_md:
                    parts.append(table_md)
            elif node_type == "image":
                img_id = node.get("metadata", {}).get("image_id", "")
                caption = node.get("metadata", {}).get("caption", "") or text
                img_line = f"[Image: {img_id or 'unknown'}]"
                if caption and not caption.startswith("[Image:"):
                    img_line += f" — {caption}"
                parts.append(img_line)
            elif node_type == "caption":
                parts.append(f"*{text}*")
            elif node_type == "formula":
                latex = text
                if latex and opts.formula_format == "latex":
                    display_type = node.get("metadata", {}).get("formula_display_type", "display")
                    if display_type in ("display", "multiline") or "\n" in latex:
                        parts.append(f"$$\n{latex}\n$$")
                    else:
                        parts.append(f"${latex}$")
                elif latex:
                    raw = node.get("metadata", {}).get("raw", latex)
                    parts.append(raw)
            elif node_type == "header":
                if opts.include_headers_footers:
                    parts.append(f"<!-- header: {text} -->")
            elif node_type == "footer":
                if opts.include_headers_footers:
                    parts.append(f"<!-- footer: {text} -->")
            else:
                if text.strip():
                    parts.append(text)

            # Evidence comments: embed fact refs as HTML comments when enabled (MD-6)
            if opts.evidence_comments:
                fact_refs = node.get("fact_refs") or []
                evidence_refs = node.get("evidence_refs") or []
                all_refs = list(fact_refs) + list(evidence_refs)
                if all_refs:
                    comment_parts = []
                    if fact_refs:
                        comment_parts.append("facts: " + ",".join(str(r) for r in fact_refs))
                    if evidence_refs:
                        comment_parts.append("evidence: " + ",".join(str(r) for r in evidence_refs))
                    parts.append("<!-- " + "; ".join(comment_parts) + " -->")

    else:
        # Fallback: use legacy export
        return export_markdown(result, options=opts)

    if not parts and result.full_text.strip():
        return result.full_text.strip()
    return "\n\n".join(parts).strip() + ("\n" if parts else "")


def _render_table_from_node(node: dict[str, Any], result: ParseResult) -> str:
    """Render a table from DFG node by looking up the corresponding table block."""
    page = node.get("page", 1)
    table_id = node.get("fact_refs", [None])[0] if node.get("fact_refs") else None

    for pg in result.pages:
        if pg.page_number == page:
            for tbl in pg.tables:
                if tbl.table_id == table_id or table_id is None:
                    return table_to_markdown(tbl)
    return ""

