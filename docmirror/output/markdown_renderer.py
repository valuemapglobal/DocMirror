# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DocMirror Markdown Profile (DMP) renderer.

The renderer is deliberately fed typed ``ParseResult`` or Mirror vNext nodes.
Provider-supplied Markdown/HTML is always treated as source text, never as
trusted presentation markup.  Raw HTML tables are forbidden; the only HTML-
shaped output is DocMirror's own namespaced comments.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from docmirror.layout.vocabulary import _is_header_row
from docmirror.tables.cell_normalizer import normalize_cell_line_breaks

MARKDOWN_PROFILE_VERSION = "1.0"
MARKDOWN_PROFILE_MARKER = f'<!-- docmirror:markdown-profile version="{MARKDOWN_PROFILE_VERSION}" -->'

_IMAGE_MARKDOWN_RE = re.compile(r"(?<!\\)!\[[^\]]*\]\([^\n)]*\)")
_IMAGE_REFERENCE_RE = re.compile(r"(?<!\\)!\[[^\]]*\]\s*\[[^\]]*\]")
_HTML_LIKE_RE = re.compile(r"</?[A-Za-z][^>]*>|<!--.*?-->", re.DOTALL)
_ORDERED_LIST_RE = re.compile(r"^(\s*)(\d+)([.)])\s+")
_UNORDERED_LIST_RE = re.compile(r"^(\s*)([-+])\s+")
_ALLOWED_HTML_TAGS: frozenset[str] = frozenset()
_ALLOWED_HTML_ATTRIBUTES: dict[str, frozenset[str]] = {}
_REGION_ROLES = frozenset({"header", "footer", "watermark", "stamp", "handwriting", "annotation"})
_PAYMENT_DIRECTION_VALUES = frozenset({"收入", "支出", "其他", "不计收支"})
_BLOCK_HTML_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "caption",
        "div",
        "dl",
        "dt",
        "dd",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)


class MarkdownContractError(ValueError):
    """Raised when renderer output violates DMP safety invariants."""


@dataclass(frozen=True)
class _SanitizedText:
    text: str
    image_count: int = 0


class _SourceHTMLTextExtractor(HTMLParser):
    """Convert untrusted source HTML to text while recording non-text images."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.image_count = 0
        self._suppressed_depth = 0

    def _break(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in {"script", "style", "template"}:
            self._suppressed_depth += 1
            return
        if self._suppressed_depth:
            return
        if tag == "img":
            self.image_count += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_HTML_TAGS:
            self._break()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "template"}:
            self._suppressed_depth = max(0, self._suppressed_depth - 1)
            return
        if not self._suppressed_depth and tag in _BLOCK_HTML_TAGS:
            self._break()

    def handle_data(self, data: str) -> None:
        if not self._suppressed_depth:
            self.parts.append(data)


class _RenderedHTMLValidator(HTMLParser):
    """Validate the small raw-HTML subset emitted by DMP."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.issues: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in _ALLOWED_HTML_TAGS:
            self.issues.append(f"forbidden_html_tag:{tag}")
            return
        allowed = _ALLOWED_HTML_ATTRIBUTES[tag]
        for name, value in attrs:
            name = name.lower()
            if name not in allowed:
                self.issues.append(f"forbidden_html_attribute:{tag}.{name}")
            elif name in {"rowspan", "colspan"} and (not str(value or "").isdigit() or int(str(value)) < 1):
                self.issues.append(f"invalid_html_span:{tag}.{name}")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def _normalize_source_text(value: Any) -> _SanitizedText:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    image_count = len(_IMAGE_MARKDOWN_RE.findall(text)) + len(_IMAGE_REFERENCE_RE.findall(text))
    text = _IMAGE_MARKDOWN_RE.sub("", text)
    text = _IMAGE_REFERENCE_RE.sub("", text)
    if _HTML_LIKE_RE.search(text):
        parser = _SourceHTMLTextExtractor()
        parser.feed(text)
        parser.close()
        text = "".join(parser.parts)
        image_count += parser.image_count
    text = text.replace("\t", "    ")
    text = re.sub(r"[ \u00a0]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return _SanitizedText(text=text, image_count=image_count)


def _escape_inline_text(value: Any) -> _SanitizedText:
    sanitized = _normalize_source_text(value)
    text = html.escape(sanitized.text, quote=False)
    text = text.replace("\\", "\\\\")
    text = re.sub(r"([`*_\[\]~])", r"\\\1", text)
    text = text.replace("|", "\\|")
    lines: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"^(\s*)(#{1,6})(\s+)", r"\1\\\2\3", line)
        line = _UNORDERED_LIST_RE.sub(r"\1\\\2 ", line)
        line = _ORDERED_LIST_RE.sub(r"\1\2\\\3 ", line)
        lines.append(line)
    return _SanitizedText(text="\n".join(lines), image_count=sanitized.image_count)


def _inline_single_line(value: Any) -> _SanitizedText:
    escaped = _escape_inline_text(value)
    return _SanitizedText(text=re.sub(r"\s*\n\s*", " ", escaped.text).strip(), image_count=escaped.image_count)


def _image_marker(count: int = 1) -> str:
    suffix = f' count="{count}"' if count > 1 else ""
    return f'<!-- docmirror:nontext type="image" disposition="omitted"{suffix} -->'


def _append_image_marker(parts: list[str], image_count: int) -> None:
    if image_count:
        parts.append(_image_marker(image_count))


def _page_marker(logical_page: int, source_page: int | None = None) -> str:
    marker = f'<!-- docmirror:page logical="{logical_page}"'
    if source_page is not None:
        marker += f' source="{source_page}"'
    return marker + " -->"


def _bbox_key(value: Any, sequence: int) -> tuple[float, float, float, int]:
    bbox = getattr(value, "bbox", None)
    reading_order = float(getattr(value, "reading_order", 0) or 0)
    top = float(bbox[1]) if isinstance(bbox, (list, tuple)) and len(bbox) >= 2 else 1_000_000.0
    left = float(bbox[0]) if isinstance(bbox, (list, tuple)) and len(bbox) >= 1 else 1_000_000.0
    return (reading_order if reading_order > 0 else 1_000_000.0, top, left, sequence)


def _int_or(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _typed_table_spans(table: Any) -> list[dict[str, int]]:
    metadata = dict(getattr(table, "metadata", None) or {})
    geometry_value = metadata.get("geometry")
    geometry: dict[str, Any] = geometry_value if isinstance(geometry_value, dict) else {}
    raw_spans = list(geometry.get("cell_spans") or metadata.get("cell_spans") or [])
    spans: list[dict[str, int]] = []
    for item in raw_spans:
        if not isinstance(item, dict):
            continue
        spans.append(
            {
                "row": _int_or(item.get("row"), -1),
                "col": _int_or(item.get("col"), -1),
                "row_span": max(1, _int_or(item.get("row_span", item.get("rowspan", 1)) or 1, 1)),
                "col_span": max(1, _int_or(item.get("col_span", item.get("colspan", 1)) or 1, 1)),
            }
        )
    headers = list(getattr(table, "headers", None) or [])
    row_offset = 1 if headers else 0
    for row_index, row in enumerate(getattr(table, "rows", None) or []):
        for col_index, cell in enumerate(getattr(row, "cells", None) or []):
            source_col_index = getattr(cell, "col_index", None)
            anchor_col = int(source_col_index) if source_col_index is not None else col_index
            row_span = max(1, int(getattr(cell, "row_span", 1) or 1))
            col_span = max(1, int(getattr(cell, "col_span", 1) or 1))
            if row_span > 1 or col_span > 1:
                spans.append(
                    {
                        "row": row_index + row_offset,
                        "col": anchor_col,
                        "row_span": row_span,
                        "col_span": col_span,
                    }
                )
    return spans


def _table_cell(value: Any) -> str:
    escaped = _escape_inline_text(normalize_cell_line_breaks(str(value or "")))
    return re.sub(r"\s*\n\s*", " ", escaped.text).strip()


def _render_gfm_table(headers: list[str], rows: list[list[str]], caption: str = "") -> str:
    width = max([len(headers), *(len(row) for row in rows)], default=0)
    if width <= 0:
        return ""
    padded_headers = [*headers, *("" for _ in range(width - len(headers)))]
    lines: list[str] = []
    if caption:
        rendered_caption = _inline_single_line(caption)
        if rendered_caption.text:
            lines.extend([f"**{rendered_caption.text}**", ""])
    lines.append("| " + " | ".join(_table_cell(value) for value in padded_headers) + " |")
    lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    for row in rows:
        padded = [*row, *("" for _ in range(width - len(row)))]
        lines.append("| " + " | ".join(_table_cell(value) for value in padded[:width]) + " |")
    return "\n".join(lines)


def _validated_table_spans(
    matrix: list[list[str]],
    spans: list[dict[str, int]],
) -> list[dict[str, int]]:
    """Discard spans that would suppress another non-empty source cell."""
    valid: list[dict[str, int]] = []
    for span in spans:
        row = _int_or(span.get("row"), -1)
        col = _int_or(span.get("col"), -1)
        row_span = max(1, _int_or(span.get("row_span"), 1))
        col_span = max(1, _int_or(span.get("col_span"), 1))
        if row < 0 or col < 0:
            continue
        conflicts = False
        for covered_row in range(row, row + row_span):
            for covered_col in range(col, col + col_span):
                if (covered_row, covered_col) == (row, col):
                    continue
                if covered_row < len(matrix) and covered_col < len(matrix[covered_row]):
                    if str(matrix[covered_row][covered_col] or "").strip():
                        conflicts = True
                        break
            if conflicts:
                break
        if not conflicts:
            valid.append(
                {
                    "row": row,
                    "col": col,
                    "row_span": row_span,
                    "col_span": col_span,
                }
            )
    return valid


def _typed_header_index(
    matrix: list[list[str]],
    headers: list[str],
    metadata: dict[str, Any],
    *,
    raw_matrix: bool,
) -> int:
    if not matrix:
        return -1
    first_header = re.sub(r"\s+", "", headers[0]) if headers else ""
    if first_header in _PAYMENT_DIRECTION_VALUES:
        return -1
    configured = metadata.get("header_row_index")
    if configured is not None:
        index = _int_or(configured, -1)
        if 0 <= index < len(matrix) and _is_header_row(matrix[index]):
            return index
    for index, row in enumerate(matrix[:10]):
        if _is_header_row(row):
            return index
    if not raw_matrix and headers:
        return 0
    return -1


def _render_typed_table(table: Any) -> str:
    headers = [str(value or "") for value in (getattr(table, "headers", None) or [])]
    row_maps: list[dict[int, str]] = []
    width = len(headers)
    for row in getattr(table, "rows", None) or []:
        values: dict[int, str] = {}
        cursor = 0
        for cell in getattr(row, "cells", None) or []:
            source_col_index = getattr(cell, "col_index", None)
            col_index = int(source_col_index) if source_col_index is not None else cursor
            values[col_index] = str(getattr(cell, "text", "") or "")
            cursor = col_index + 1
            width = max(width, cursor)
        row_maps.append(values)
    rows = [[values.get(index, "") for index in range(width)] for values in row_maps]
    metadata = dict(getattr(table, "metadata", None) or {})
    raw_rows = metadata.get("raw_rows") if isinstance(metadata.get("raw_rows"), list) else None
    raw_matrix = (
        [[str(value or "") for value in row] for row in raw_rows if isinstance(row, list)] if raw_rows else None
    )
    caption = str(getattr(table, "caption", "") or "")
    matrix = raw_matrix if raw_matrix is not None else ([headers] if headers else []) + rows
    if not matrix:
        return ""
    valid_spans = _validated_table_spans(matrix, _typed_table_spans(table))
    width = max(
        [
            *(len(row) for row in matrix),
            *(span["col"] + span["col_span"] for span in valid_spans),
        ],
        default=0,
    )
    matrix = [[*row, *("" for _ in range(width - len(row)))] for row in matrix]
    header_index = _typed_header_index(
        matrix,
        headers,
        metadata,
        raw_matrix=raw_matrix is not None,
    )
    preamble: list[str] = []
    if header_index > 0:
        for row in matrix[:header_index]:
            text = " ".join(_table_cell(value) for value in row if str(value or "").strip()).strip()
            if text:
                preamble.append(text)
    if header_index >= 0:
        rendered_headers = matrix[header_index]
        rendered_rows = matrix[header_index + 1 :]
    else:
        rendered_headers = []
        rendered_rows = matrix
    table_markdown = _render_gfm_table(rendered_headers, rendered_rows, caption)
    return "\n\n".join([*preamble, table_markdown] if table_markdown else preamble)


def _is_unproven_derived_table(table: Any) -> bool:
    """Return whether a derived table has no evidence ownership of its own.

    The geometric fallback reconstructs a convenience grid from existing text
    blocks. Until it carries cell evidence, rendering both views would consume
    the same source content twice.
    """
    metadata = dict(getattr(table, "metadata", None) or {})
    if str(metadata.get("source") or "") != "geometric_reconstructor":
        return False
    if list(getattr(table, "evidence_ids", None) or []):
        return False
    return not any(
        list(getattr(cell, "evidence_ids", None) or []) or list(getattr(cell, "token_ids", None) or [])
        for row in (getattr(table, "rows", None) or [])
        for cell in (getattr(row, "cells", None) or [])
    )


def _render_vnext_table(block: dict[str, Any]) -> str:
    grid = block.get("content", {}).get("grid", {})
    columns = list(grid.get("columns") or [])
    headers = [str(column.get("header", "") or "") for column in columns]
    row_roles = {
        _int_or(row.get("index"), index): str(row.get("role") or "")
        for index, row in enumerate(grid.get("rows") or [])
        if isinstance(row, dict)
    }
    cells_by_row: dict[int, dict[int, str]] = {}
    for cell in grid.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        row_index = _int_or(cell.get("row_index"), 0)
        col_index = _int_or(cell.get("col_index"), 0)
        cells_by_row.setdefault(row_index, {})[col_index] = str(cell.get("text", "") or "")
    width = max([len(headers), *(max(row.keys(), default=-1) + 1 for row in cells_by_row.values())], default=0)
    header_indexes = {index for index, role in row_roles.items() if role == "header"}
    if headers and not header_indexes and 0 in cells_by_row:
        first = [cells_by_row[0].get(index, "") for index in range(width)]
        if first[: len(headers)] == headers:
            header_indexes.add(0)
    data_indexes = [index for index in sorted(cells_by_row) if index not in header_indexes]
    rows = [[cells_by_row[index].get(column, "") for column in range(width)] for index in data_indexes]
    caption = str(block.get("content", {}).get("caption") or block.get("caption") or "")
    if not headers and header_indexes:
        first_header_index = min(header_indexes)
        headers = [cells_by_row.get(first_header_index, {}).get(column, "") for column in range(width)]
    return _render_gfm_table(headers, rows, caption)


def validate_markdown(markdown: str) -> list[str]:
    """Return DMP safety violations found in rendered Markdown."""
    issues: list[str] = []
    if _IMAGE_MARKDOWN_RE.search(markdown):
        issues.append("markdown_image_not_allowed")
    if _IMAGE_REFERENCE_RE.search(markdown):
        issues.append("markdown_reference_image_not_allowed")
    validator = _RenderedHTMLValidator()
    validator.feed(markdown)
    validator.close()
    issues.extend(validator.issues)
    return list(dict.fromkeys(issues))


class MarkdownRenderer:
    """Render all DocMirror Markdown through one DMP implementation."""

    def render_parse_result(self, result: Any) -> str:
        parts = [MARKDOWN_PROFILE_MARKER]
        page_sources = {
            int(getattr(page, "page_number", index) or index): int(
                getattr(page, "source_page_number", None) or getattr(page, "page_number", index) or index
            )
            for index, page in enumerate(getattr(result, "pages", None) or [], start=1)
        }
        flow = getattr(result, "document_flow", None)
        nodes = list(getattr(flow, "nodes", None) or [])
        reading_flows = list(getattr(flow, "reading_flow", None) or [])
        if nodes and reading_flows and list(getattr(reading_flows[0], "node_ids", None) or []):
            self._render_parse_flow(parts, result, nodes, reading_flows[0], page_sources)
        else:
            self._render_parse_fallback(parts, result, page_sources)
        return self._finish(parts)

    def _render_parse_flow(
        self,
        parts: list[str],
        result: Any,
        nodes: list[Any],
        reading_flow: Any,
        page_sources: dict[int, int],
    ) -> None:
        node_by_id = {str(getattr(node, "node_id", "") or ""): node for node in nodes}
        table_by_id = {
            str(getattr(table, "table_id", "") or ""): table
            for page in (getattr(result, "pages", None) or [])
            for table in (getattr(page, "tables", None) or [])
            if str(getattr(table, "table_id", "") or "")
        }
        tables_by_page = {
            int(getattr(page, "page_number", index) or index): list(getattr(page, "tables", None) or [])
            for index, page in enumerate(getattr(result, "pages", None) or [], start=1)
        }
        pages_with_text = {
            int(getattr(page, "page_number", index) or index)
            for index, page in enumerate(getattr(result, "pages", None) or [], start=1)
            if any(str(getattr(text, "content", "") or "").strip() for text in (getattr(page, "texts", None) or []))
        }
        consumed_tables: set[int] = set()
        consumed_nodes: set[str] = set()
        ordered_pages = list(page_sources)
        emitted_pages: set[int] = set()
        page_cursor = 0
        current_page: int | None = None
        for node_id in list(getattr(reading_flow, "node_ids", None) or []):
            node_key = str(node_id)
            if node_key in consumed_nodes:
                continue
            consumed_nodes.add(node_key)
            node = node_by_id.get(node_key)
            if node is None:
                continue
            page = max(1, int(getattr(node, "page", 1) or 1))
            if page != current_page:
                while page_cursor < len(ordered_pages):
                    pending_page = ordered_pages[page_cursor]
                    page_cursor += 1
                    if pending_page not in emitted_pages:
                        parts.append(_page_marker(pending_page, page_sources.get(pending_page, pending_page)))
                        emitted_pages.add(pending_page)
                    if pending_page == page:
                        break
                if page not in emitted_pages:
                    parts.append(_page_marker(page, page_sources.get(page, page)))
                    emitted_pages.add(page)
                current_page = page
            rendered = self._render_typed_node(
                node,
                table_by_id,
                tables_by_page,
                consumed_tables,
                pages_with_text,
            )
            parts.extend(rendered)
        for page in ordered_pages[page_cursor:]:
            if page not in emitted_pages:
                parts.append(_page_marker(page, page_sources.get(page, page)))
                emitted_pages.add(page)

    def _render_typed_node(
        self,
        node: Any,
        table_by_id: dict[str, Any],
        tables_by_page: dict[int, list[Any]],
        consumed_tables: set[int],
        pages_with_text: set[int],
    ) -> list[str]:
        node_type = str(getattr(node, "type", "") or "")
        role = str(getattr(node, "role", "") or "")
        metadata = dict(getattr(node, "metadata", None) or {})
        if node_type == "physical_table":
            table = table_by_id.get(str(metadata.get("table_id") or ""))
            if table is None:
                node_bbox = list(getattr(node, "bbox", None) or [])
                candidates = [
                    candidate
                    for candidate in tables_by_page.get(int(getattr(node, "page", 1) or 1), [])
                    if id(candidate) not in consumed_tables
                ]
                table = next(
                    (
                        candidate
                        for candidate in candidates
                        if node_bbox and list(getattr(candidate, "bbox", None) or []) == node_bbox
                    ),
                    candidates[0] if candidates else None,
                )
            if table is not None:
                consumed_tables.add(id(table))
                if int(getattr(node, "page", 1) or 1) in pages_with_text and _is_unproven_derived_table(table):
                    return []
            rendered = _render_typed_table(table) if table is not None else ""
            return [rendered] if rendered else []
        if node_type in {"image", "figure"}:
            return [_image_marker()]
        if role == "key_value":
            return self._render_key_value(metadata.get("key", ""), metadata.get("value", ""))
        text = getattr(node, "text", "")
        if node_type == "heading":
            return self._render_heading(text, metadata.get("level", ""))
        if node_type == "list_item":
            escaped = _inline_single_line(text)
            if not escaped.text:
                return [_image_marker(escaped.image_count)] if escaped.image_count else []
            ordered = str(metadata.get("list_type") or metadata.get("kind") or "").lower() == "ordered"
            list_rendered = [("1. " if ordered else "- ") + escaped.text]
            _append_image_marker(list_rendered, escaped.image_count)
            return list_rendered
        if role in _REGION_ROLES or node_type in _REGION_ROLES:
            return self._render_region(text, role if role in _REGION_ROLES else node_type)
        return self._render_plain(text)

    def _render_parse_fallback(
        self,
        parts: list[str],
        result: Any,
        page_sources: dict[int, int],
    ) -> None:
        pages = list(getattr(result, "pages", None) or [])
        pages_with_text = {
            int(getattr(page, "page_number", index) or index)
            for index, page in enumerate(pages, start=1)
            if any(str(getattr(text, "content", "") or "").strip() for text in (getattr(page, "texts", None) or []))
        }
        for page_index, page in enumerate(pages, start=1):
            logical_page = int(getattr(page, "page_number", page_index) or page_index)
            parts.append(_page_marker(logical_page, page_sources.get(logical_page, logical_page)))
            entries: list[tuple[tuple[float, float, float, int], str, Any]] = []
            sequence = 0
            for kind, values in (
                ("text", getattr(page, "texts", None) or []),
                ("key_value", getattr(page, "key_values", None) or []),
                ("table", getattr(page, "tables", None) or []),
            ):
                for value in values:
                    entries.append((_bbox_key(value, sequence), kind, value))
                    sequence += 1
            for _, kind, value in sorted(entries, key=lambda item: item[0]):
                if kind == "table":
                    if logical_page in pages_with_text and _is_unproven_derived_table(value):
                        continue
                    rendered = _render_typed_table(value)
                    if rendered:
                        parts.append(rendered)
                elif kind == "key_value":
                    parts.extend(self._render_key_value(getattr(value, "key", ""), getattr(value, "value", "")))
                else:
                    level = str(getattr(getattr(value, "level", None), "value", getattr(value, "level", "")) or "")
                    role = str(getattr(value, "role", "body") or "body")
                    if level in {"title", "h1", "h2", "h3", "h4", "h5", "h6"}:
                        parts.extend(self._render_heading(getattr(value, "content", ""), level))
                    elif role in _REGION_ROLES:
                        parts.extend(self._render_region(getattr(value, "content", ""), role))
                    else:
                        parts.extend(self._render_plain(getattr(value, "content", "")))
        if not pages:
            fallback = getattr(result, "raw_text", "") or getattr(result, "full_text", "") or ""
            parts.extend(self._render_plain(fallback))

    def _render_heading(self, value: Any, level: Any) -> list[str]:
        escaped = _inline_single_line(value)
        level_text = str(level or "").lower()
        depth = {"title": 1, "h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}.get(level_text, 2)
        rendered = [f"{'#' * depth} {escaped.text}"] if escaped.text else []
        _append_image_marker(rendered, escaped.image_count)
        return rendered

    def _render_key_value(self, key: Any, value: Any) -> list[str]:
        rendered_key = _inline_single_line(key)
        rendered_value = _escape_inline_text(value)
        if rendered_key.text:
            line = f"**{rendered_key.text}:**"
            if rendered_value.text:
                line += f" {rendered_value.text}"
            rendered = [line]
        elif rendered_value.text:
            rendered = [rendered_value.text]
        else:
            rendered = []
        _append_image_marker(rendered, rendered_key.image_count + rendered_value.image_count)
        return rendered

    def _render_plain(self, value: Any) -> list[str]:
        escaped = _escape_inline_text(value)
        rendered = [escaped.text] if escaped.text else []
        _append_image_marker(rendered, escaped.image_count)
        return rendered

    def _render_region(self, value: Any, role: str) -> list[str]:
        escaped = _escape_inline_text(value)
        rendered: list[str] = []
        if escaped.text:
            quoted = "\n".join(f"> {line}" if line else ">" for line in escaped.text.split("\n"))
            rendered.extend([f'<!-- docmirror:region role="{role}" -->', quoted])
        _append_image_marker(rendered, escaped.image_count)
        return rendered

    def render_mirror_vnext(self, mirror: dict[str, Any]) -> str:
        parts = [MARKDOWN_PROFILE_MARKER]
        blocks = {str(block.get("id")): block for block in mirror.get("blocks", []) if block.get("id")}
        document = mirror.get("document", {})
        flow_id = document.get("primary_reading_flow_id")
        flows = mirror.get("graph", {}).get("reading_flows", [])
        selected = next((flow for flow in flows if not flow_id or flow.get("flow_id") == flow_id), None)
        if selected is not None:
            reading_blocks = [blocks[node_id] for node_id in selected.get("node_ids", []) if node_id in blocks]
        else:
            reading_blocks = [
                block
                for block in mirror.get("blocks", [])
                if not block.get("quality", {}).get("suppressed_from_reading_flow")
            ]
        page_numbers = {
            str(page.get("page_id")): int(page.get("page_number", index) or index)
            for index, page in enumerate(mirror.get("pages", []) or [], start=1)
        }
        current_page: int | None = None
        consumed_blocks: set[str] = set()
        for block in reading_blocks:
            block_id = str(block.get("id") or "")
            if block_id and block_id in consumed_blocks:
                continue
            if block_id:
                consumed_blocks.add(block_id)
            page_ids = list(block.get("page_ids") or [])
            page = page_numbers.get(str(page_ids[0]), 1) if page_ids else 1
            if page != current_page:
                parts.append(_page_marker(page, page))
                current_page = page
            parts.extend(self._render_vnext_block(block))
        return self._finish(parts)

    def _render_vnext_block(self, block: dict[str, Any]) -> list[str]:
        block_type = str(block.get("type") or "")
        role = str(block.get("role") or "")
        if block_type == "table":
            rendered = _render_vnext_table(block)
            return [rendered] if rendered else []
        if block_type in {"image", "figure"}:
            return [_image_marker()]
        if block_type == "heading" or role in {"title", "h1", "h2", "h3", "h4", "h5", "h6"}:
            return self._render_heading(block.get("text", ""), role or block.get("level", ""))
        if role in {"page_header", "header"} or block_type == "header":
            return self._render_region(block.get("text", ""), "header")
        if role in {"page_footer", "footer"} or block_type == "footer":
            return self._render_region(block.get("text", ""), "footer")
        if role in _REGION_ROLES:
            return self._render_region(block.get("text", ""), role)
        return self._render_plain(block.get("text", ""))

    @staticmethod
    def _finish(parts: list[str]) -> str:
        markdown = "\n\n".join(part.strip() for part in parts if part and part.strip()).rstrip() + "\n"
        issues = validate_markdown(markdown)
        if issues:
            raise MarkdownContractError("; ".join(issues))
        return markdown


DEFAULT_MARKDOWN_RENDERER = MarkdownRenderer()


def render_markdown(result: Any) -> str:
    """Render a ParseResult using DMP 1.0."""
    return DEFAULT_MARKDOWN_RENDERER.render_parse_result(result)


def render_markdown_from_vnext(mirror: dict[str, Any]) -> str:
    """Render a Mirror vNext mapping using DMP 1.0."""
    return DEFAULT_MARKDOWN_RENDERER.render_mirror_vnext(mirror)


__all__ = [
    "DEFAULT_MARKDOWN_RENDERER",
    "MARKDOWN_PROFILE_MARKER",
    "MARKDOWN_PROFILE_VERSION",
    "MarkdownContractError",
    "MarkdownRenderer",
    "render_markdown",
    "render_markdown_from_vnext",
    "validate_markdown",
]
