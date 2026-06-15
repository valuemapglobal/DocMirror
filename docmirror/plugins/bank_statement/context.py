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

    return _Collector()._collect_tables(parse_result)


def build_style_context(parse_result: Any, full_text: str = "") -> StyleContext:
    text = full_text or getattr(parse_result, "full_text", "") or ""
    institution, authority = resolve_institution_from_context(parse_result, text)

    pages = getattr(parse_result, "pages", []) or []
    mirror_tables = collect_tables_from_parse_result(parse_result)
    tables, reconstruction = reconstruct_tables(
        mirror_tables,
        text,
        page_count=len(pages),
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
