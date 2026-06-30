"""
Fact Identity Layer — deterministic fact_id generation for Mirror facts.

GA 1.0 design §7.1: Every Mirror fact that can be consumed by a downstream
projection receives a stable, deterministic ``fact_id``. The id is
input-parsing-profile-stable: same input + same profile → same fact_id.

Fact types::

    page   → page:1
    text   → text:p1:b3
    span   → span:p1:b3:s2
    table  → table:p2:t0
    cell   → cell:p2:t0:r4:c3
    section→ section:s2
    formula→ formula:p3:f1
    image  → image:p4:i0

Rules:
    1. ``fact_id`` must be deterministic under the same input and profile.
    2. ``fact_id`` must not contain sensitive raw text.
    3. ``fact_id`` may change across major schema versions (recorded in schema_versions).
    4. Facts without bbox still receive a ``fact_id`` (evidence completeness reflects missing bbox).
"""

from __future__ import annotations

from typing import Any


def fact_id_for_page(page_number: int) -> str:
    """Stable fact_id for a page: ``page:{page_number}``."""
    return f"page:{page_number}"


def fact_id_for_text_block(page_number: int, block_index: int) -> str:
    """Stable fact_id for a text block: ``text:p{page}:b{block_index}``."""
    return f"text:p{page_number}:b{block_index}"


def fact_id_for_span(page_number: int, block_index: int, span_index: int) -> str:
    """Stable fact_id for a token/span: ``span:p{page}:b{block}:s{span}``."""
    return f"span:p{page_number}:b{block_index}:s{span_index}"


def fact_id_for_table(page_number: int, table_index: int) -> str:
    """Stable fact_id for a table: ``table:p{page}:t{table_index}``."""
    return f"table:p{page_number}:t{table_index}"


def fact_id_for_cell(
    page_number: int,
    table_index: int,
    row_index: int = 0,
    col_index: int = 0,
) -> str:
    """Stable fact_id for a cell: ``cell:p{page}:t{table}:r{row}:c{col}``."""
    return f"cell:p{page_number}:t{table_index}:r{row_index}:c{col_index}"


def fact_id_for_section(section_index: int) -> str:
    """Stable fact_id for a section: ``section:s{section_index}``."""
    return f"section:s{section_index}"


def fact_id_for_formula(page_number: int, formula_index: int) -> str:
    """Stable fact_id for a formula: ``formula:p{page}:f{formula_index}``."""
    return f"formula:p{page_number}:f{formula_index}"


def fact_id_for_image(page_number: int, image_index: int) -> str:
    """Stable fact_id for an image: ``image:p{page}:i{image_index}``."""
    return f"image:p{page_number}:i{image_index}"


def collect_mirror_fact_ids(result: Any) -> dict[str, list[str]]:
    """Collect all fact_ids from a ParseResult into a grouped summary.

    Returns a dict mapping fact categories to lists of fact_id strings.
    Useful for building the evidence ledger and mirror forensic output.
    """
    by_category: dict[str, list[str]] = {
        "page": [],
        "text": [],
        "table": [],
        "cell": [],
        "section": [],
        "formula": [],
        "image": [],
    }

    pages = list(getattr(result, "pages", []) or [])
    for page_idx, page in enumerate(pages, start=1):
        by_category["page"].append(fact_id_for_page(page_idx))

        for text_idx, _text in enumerate(list(getattr(page, "texts", []) or [])):
            by_category["text"].append(fact_id_for_text_block(page_idx, text_idx))

        for table_idx, table in enumerate(list(getattr(page, "tables", []) or [])):
            by_category["table"].append(fact_id_for_table(page_idx, table_idx))
            for row_idx, row in enumerate(
                list(getattr(table, "rows", []) or list(getattr(table, "data_rows", []) or []))
            ):
                for col_idx, _cell in enumerate(list(getattr(row, "cells", []) or [])):
                    by_category["cell"].append(fact_id_for_cell(page_idx, table_idx, row_idx, col_idx))

    # Sections from result.sections
    sections = list(getattr(result, "sections", []) or [])
    for sec_idx in range(len(sections)):
        by_category["section"].append(fact_id_for_section(sec_idx + 1))

    return by_category


__all__ = [
    "fact_id_for_page",
    "fact_id_for_text_block",
    "fact_id_for_span",
    "fact_id_for_table",
    "fact_id_for_cell",
    "fact_id_for_section",
    "fact_id_for_formula",
    "fact_id_for_image",
    "collect_mirror_fact_ids",
]
