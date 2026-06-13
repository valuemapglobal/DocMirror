# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
ParseResult Bridge — Core-extraction boundary only (MOC, design 09 §4 / Appendix C)
==================================================================================

**Allowed conversion** (Path B adapters only):

    BaseResult  →  ParseResult   via ``from_base_result()``
    ParseResult   →  BaseResult   via ``to_base_result()`` (legacy Excel fallback only)

Primary entry: ``CoreExtractor.extract_parse_result()``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _infer_cell_value(text: str) -> CellValue:
    """Infer CellValue type from raw text string.

    Returns CellValue with proper data_type, numeric, and cleaned fields.
    """
    import re

    from docmirror.models.entities.parse_result import CellValue, DataType

    text = str(text).strip()
    if not text:
        return CellValue(text=text, data_type=DataType.EMPTY)

    # Date patterns: 2025-03-27, 2025/03/27, 2025年03月27日
    if re.match(r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?$", text):
        return CellValue(text=text, data_type=DataType.DATE)

    # Time pattern: 14:21:48
    if re.match(r"^\d{2}:\d{2}(:\d{2})?$", text):
        return CellValue(text=text, data_type=DataType.TEXT)

    # Currency/Number: try parsing
    cleaned = text.replace(",", "").replace("，", "").replace(" ", "")
    # Remove currency symbols
    cleaned = re.sub(r"^[¥$€£]", "", cleaned)

    # Try numeric parse
    try:
        float(cleaned)
        # Long digit-only strings (>10 chars, no decimal) are identifiers
        # (account numbers, ID numbers, invoice codes), not values
        if re.match(r"^\d{10,}$", cleaned):
            return CellValue(text=text, data_type=DataType.TEXT)
        # Determine if currency (has comma formatting or decimal places typical of money)
        has_comma = "," in text or "，" in text
        has_decimal = "." in cleaned and len(cleaned.split(".")[-1]) == 2
        if has_comma or has_decimal:
            return CellValue(text=text, data_type=DataType.CURRENCY)
        else:
            return CellValue(text=text, data_type=DataType.NUMBER)
    except (ValueError, TypeError):
        pass

    return CellValue(text=text, data_type=DataType.TEXT)


def _blocks_to_pages(base: BaseResult):
    """Convert BaseResult pages/blocks → List[PageContent] for ParseResult.

    Mapping:
        - Block(type=table, raw_content=List[List[str]]) → TableBlock with typed CellValue
        - Block(type=text/title) → TextBlock with heading level
        - Block(type=key_value, raw_content=dict) → KeyValuePair
    """
    from docmirror.models.entities.parse_result import (
        CellValue,
        KeyValuePair,
        PageContent,
        RowType,
        TableBlock,
        TableRow,
        TextBlock,
        TextLevel,
    )

    pages = []
    for page_layout in base.pages:
        tables = []
        texts = []
        key_values = []

        for block in page_layout.blocks:
            if block.block_type == "table" and isinstance(block.raw_content, list):
                raw = block.raw_content
                headers = []
                rows = []
                table_index = len(tables)
                pt_id = f"pt_{page_layout.page_number}_{table_index}"
                if raw:
                    headers = [str(h) for h in raw[0]]
                    for row_idx, row_data in enumerate(raw[1:]):
                        if isinstance(row_data, list):
                            cells = [_infer_cell_value(v) for v in row_data]
                            rows.append(
                                TableRow(
                                    cells=cells,
                                    row_type=RowType.DATA,
                                    source_page=page_layout.page_number,
                                    source_physical_id=pt_id,
                                    source_row_index=row_idx,
                                )
                            )
                tables.append(
                    TableBlock(
                        table_id=pt_id,
                        headers=headers,
                        rows=rows,
                        page=page_layout.page_number,
                        page_span=1,
                    )
                )

            elif block.block_type in ("text", "title") and isinstance(block.raw_content, str):
                level = TextLevel.BODY
                if block.block_type == "title" or block.heading_level == 1:
                    level = TextLevel.H1
                elif block.heading_level == 2:
                    level = TextLevel.H2
                elif block.heading_level == 3:
                    level = TextLevel.H3
                texts.append(
                    TextBlock(
                        content=block.raw_content,
                        level=level,
                    )
                )

            elif block.block_type == "key_value" and isinstance(block.raw_content, dict):
                for k, v in block.raw_content.items():
                    key_values.append(KeyValuePair(key=str(k), value=str(v)))

            elif block.block_type == "footer" and isinstance(block.raw_content, str):
                texts.append(
                    TextBlock(
                        content=block.raw_content,
                        level=TextLevel.FOOTER,
                    )
                )

        pages.append(
            PageContent(
                page_number=page_layout.page_number,
                tables=tables,
                texts=texts,
                key_values=key_values,
            )
        )

    return pages


class ParseResultBridge:
    """Unified converter between ParseResult and Core-internal BaseResult.

    Primary methods:
        - ``from_base_result(base)`` → BaseResult → ParseResult (Core boundary)
        - ``to_base_result(pr)``     → ParseResult → BaseResult (legacy Excel fallback)
    """

    # ══════════════════════════════════════════════════════════════════════
    # BaseResult → ParseResult (for adapters that extract to BaseResult)
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def from_base_result(base: BaseResult) -> ParseResult:
        """
        Convert BaseResult → ParseResult.

        Used by adapters (e.g. PDFAdapter) that extract to BaseResult
        and need to convert to ParseResult before the middleware pipeline.

        Mapping:
            - Block(type=table) → TableBlock with CellValue per cell
            - Block(type=text/title) → TextBlock with appropriate level
            - Block(type=key_value) → KeyValuePair
        """
        from docmirror.models.entities.parse_result import (
            ParseResult,
            ParserInfo,
        )

        pages = _blocks_to_pages(base)
        meta = base.metadata or {}
        pr = ParseResult(
            pages=pages,
            parser_info=ParserInfo(
                parser=meta.get("parser", ""),
                elapsed_ms=meta.get("elapsed_ms", 0),
                page_count=len(base.pages),
            ),
            sections=meta.get("sections", []),
        )

        # ── Compose logical tables (from extractor metadata or physical pages) ──
        _compose_logical_tables(pr, base_metadata=meta)
        return pr

    @staticmethod
    def to_base_result(pr: ParseResult) -> BaseResult:
        """
        Convert ParseResult → BaseResult for middleware pipeline consumption.

        Mapping:
            - PageContent → PageLayout (1:1)
            - TableBlock.rows → Block(block_type="table", raw_content=List[List[str]])
            - TextBlock → Block(block_type="text"/"title")
            - KeyValuePair → Block(block_type="key_value", raw_content={key: value})
        """
        from docmirror.models.entities.domain import BaseResult, Block, PageLayout

        pages = []
        reading_order = 0

        for page_content in pr.pages:
            blocks = []

            for text in page_content.texts:
                from docmirror.models.entities.parse_result import TextLevel

                block_type = "title" if text.level in (TextLevel.TITLE, TextLevel.H1) else "text"
                blocks.append(
                    Block(
                        block_type=block_type,
                        raw_content=text.content,
                        page=page_content.page_number,
                        reading_order=reading_order,
                        heading_level=(
                            1
                            if text.level == TextLevel.TITLE
                            else 1
                            if text.level == TextLevel.H1
                            else 2
                            if text.level == TextLevel.H2
                            else 3
                            if text.level == TextLevel.H3
                            else None
                        ),
                    )
                )
                reading_order += 1

            for kv in page_content.key_values:
                blocks.append(
                    Block(
                        block_type="key_value",
                        raw_content={kv.key: kv.value},
                        page=page_content.page_number,
                        reading_order=reading_order,
                    )
                )
                reading_order += 1

            for table in page_content.tables:
                # Convert CellValue rows to List[List[str]]
                raw_rows = []
                if table.headers:
                    raw_rows.append(table.headers)
                for row in table.rows:
                    raw_rows.append([c.text for c in row.cells])

                blocks.append(
                    Block(
                        block_type="table",
                        raw_content=raw_rows,
                        page=page_content.page_number,
                        reading_order=reading_order,
                    )
                )
                reading_order += 1

            pages.append(
                PageLayout(
                    page_number=page_content.page_number,
                    blocks=tuple(blocks),
                )
            )

        # Build full text from ParseResult
        full_text = pr.full_text

        # Build metadata from entities + parser_info
        metadata: dict[str, Any] = {
            "source_format": pr.provenance.file_type if pr.provenance else "unknown",
        }
        # Carry entities into metadata for downstream middleware access
        if pr.entities.organization:
            metadata["organization"] = pr.entities.organization
        if pr.entities.subject_name:
            metadata["subject_name"] = pr.entities.subject_name

        return BaseResult(
            pages=tuple(pages),
            full_text=full_text,
            metadata=metadata,
        )


def _compose_logical_tables(pr, base_metadata: dict | None = None):
    """Compose logical tables from physical pages and set ParseResult.logical_tables.

    Priority:
      1. Pre-composed logical tables from extractor metadata (most accurate —
         composed before destructive merge, preserves cross-page provenance).
      2. Live composition from physical pages (fallback when metadata unavailable).
    """
    from docmirror.models.entities.parse_result import CellValue, DataType, RowType, TableRow, RowProvenance, LogicalTable
    from docmirror.core.table.composer import build_table_operations

    # Priority 1: Pre-composed from extractor metadata
    raw_tables = None
    if base_metadata:
        raw_tables = base_metadata.get("_logical_tables")

    if raw_tables:
        logical = []
        for raw in raw_tables:
            rows = []
            provenance = []
            for ri, raw_row in enumerate(raw.get("rows", [])):
                cells = []
                for rc in raw_row.get("cells", []):
                    text = rc.get("text", "")
                    dt_str = rc.get("data_type", "text")
                    try:
                        dt = DataType(dt_str)
                    except ValueError:
                        dt = DataType.TEXT
                    cells.append(CellValue(text=text, data_type=dt))
                src_page = raw_row.get("source_page", 1)
                src_phys = raw_row.get("source_physical_id", "")
                src_idx = raw_row.get("source_row_index", ri)
                rows.append(
                    TableRow(
                        cells=cells,
                        row_type=RowType.DATA,
                        source_page=src_page,
                        source_physical_id=src_phys,
                        source_row_index=src_idx,
                    )
                )
                provenance.append(
                    RowProvenance(
                        source_page=src_page,
                        source_table_id=src_phys,
                        source_row_index=src_idx,
                    )
                )

            sp = raw.get("source_pages", [])
            ps = raw.get("page_span", [1, 1])
            lid = raw.get("logical_id") or raw.get("table_id", "logical_0")
            logical.append(
                LogicalTable(
                    table_id=lid,
                    logical_id=lid,
                    headers=raw.get("headers", []),
                    rows=rows,
                    row_count=raw.get("row_count", len(rows)),
                    source_physical_ids=raw.get("source_physical_ids", []),
                    source_pages=sp,
                    page_span=(ps[0], ps[1]) if len(ps) >= 2 else (1, 1),
                    confidence=raw.get("confidence", 1.0),
                    merge_method=raw.get("merge_method", "cross_page_continuation"),
                    merge_confidence=raw.get("merge_confidence", raw.get("confidence", 1.0)),
                    provenance=provenance,
                    merge_log=raw.get("merge_log", []),
                    merge_audit=raw.get("merge_audit", []),
                )
            )
        if logical:
            pr.logical_tables = logical
            pr.table_operations = build_table_operations(logical)
            return

    # Priority 2: Live composition from physical pages (fallback)
    try:
        from docmirror.core.table.composer import TableComposer

        composer = TableComposer()
        logical = composer.compose(pr.pages)
        if logical:
            pr.logical_tables = logical
            pr.table_operations = build_table_operations(logical)
    except Exception:
        pass
