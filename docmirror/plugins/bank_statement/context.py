# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Build ``StyleContext`` from Mirror ``ParseResult`` for bank style detection.

Aggregates table cell matrices, full text, institution hints, LTRO reconstruction
meta, and page count into a single context object passed to ``BankStyleDetector``
and style parsers.

Pipeline role: first step inside ``bank_statement.community_plugin.extract_from_mirror``
before style detection and parser dispatch.

Key exports: ``StyleContext``, ``build_style_context``, ``collect_tables_from_parse_result``.

Dependencies: ``ltro``, ``institution_authority``, ``BaseTableParser._collect_tables``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docmirror.plugins.bank_statement.institution_authority import resolve_institution_from_context
from docmirror.plugins.bank_statement.ltro import ReconstructionMeta, reconstruct_tables


def _structure_spe_from_parse_result(parse_result: Any) -> dict | None:
    from docmirror.evidence.spe_consumer import read_structure_spe

    return read_structure_spe(parse_result)


@dataclass
class StyleContext:
    tables: list[list[list[str]]]
    full_text: str
    institution: str | None
    page_count: int
    parse_result: Any = None
    reconstruction: ReconstructionMeta | None = None
    institution_authority: str = ""


def collect_tables_from_parse_result(parse_result: Any) -> list[list[list[str]]]:
    from docmirror.plugins._base.base_table_parser import BaseTableParser

    class _Collector(BaseTableParser):
        @property
        def domain_name(self):
            return "bank_statement"

        @property
        def display_name(self):
            return "collector"

        @property
        def column_registry(self):
            return {}

        @property
        def standard_fields(self):
            return []

    tables = _Collector()._collect_tables(parse_result)
    if tables:
        return tables
    return _collect_tables_from_vnext_mirror(getattr(parse_result, "mirror", None))


def _collect_tables_from_vnext_mirror(mirror: Any) -> list[list[list[str]]]:
    if mirror is None:
        return []
    if hasattr(mirror, "model_dump"):
        payload = mirror.model_dump(by_alias=True, exclude_none=True)
    elif isinstance(mirror, dict):
        payload = mirror
    else:
        return []

    tables: list[list[list[str]]] = []
    for block in payload.get("blocks") or []:
        if block.get("type") != "table":
            continue
        grid = (block.get("content") or {}).get("grid") or {}
        cells = grid.get("cells") or []
        if not cells:
            continue
        max_row = max((int(cell.get("row", 0) or 0) for cell in cells), default=-1)
        max_col = max((int(cell.get("col", 0) or 0) for cell in cells), default=-1)
        if max_row < 0 or max_col < 0:
            continue
        rows = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
        for cell in cells:
            row_idx = int(cell.get("row", 0) or 0)
            col_idx = int(cell.get("col", 0) or 0)
            if row_idx > max_row or col_idx > max_col:
                continue
            rows[row_idx][col_idx] = str(cell.get("text") or "")
        if rows and any(any(value.strip() for value in row) for row in rows):
            tables.append(rows)
    return tables


def build_style_context(parse_result: Any, full_text: str = "") -> StyleContext:
    text = full_text or getattr(parse_result, "full_text", "") or ""
    institution, authority = resolve_institution_from_context(parse_result, text)

    pages = getattr(parse_result, "pages", []) or []
    mirror_tables = collect_tables_from_parse_result(parse_result)
    structure_spe = _structure_spe_from_parse_result(parse_result)
    tables, reconstruction = reconstruct_tables(
        mirror_tables,
        text,
        page_count=len(pages),
        structure_spe=structure_spe,
        parse_result=parse_result,
    )

    return StyleContext(
        tables=tables,
        full_text=text,
        institution=institution,
        page_count=len(pages),
        parse_result=parse_result,
        reconstruction=reconstruction,
        institution_authority=authority,
    )
