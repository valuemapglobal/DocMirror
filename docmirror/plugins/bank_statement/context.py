# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build StyleContext from mirror ParseResult."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StyleContext:
    tables: list[list[list[str]]]
    full_text: str
    institution: str | None
    page_count: int
    parse_result: Any = None


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
    institution = None
    entities = getattr(parse_result, "entities", None)
    if entities is not None:
        props = getattr(entities, "metadata", None) or getattr(entities, "properties", None)
        if isinstance(props, dict):
            institution = props.get("institution") or props.get("organization")
        if not institution:
            doc_props = getattr(entities, "document_properties", None)
            if isinstance(doc_props, dict):
                institution = doc_props.get("institution")

    pages = getattr(parse_result, "pages", []) or []
    tables = collect_tables_from_parse_result(parse_result)
    if not tables and text.strip():
        from docmirror.plugins.bank_statement.text_table_builder import build_tables_from_ocr_text

        tables = build_tables_from_ocr_text(text)

    return StyleContext(
        tables=tables,
        full_text=text,
        institution=institution,
        page_count=len(pages),
        parse_result=parse_result,
    )
