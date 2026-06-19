# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Logical Table Reconstruction Orchestrator (LTRO) for bank statements.

When Mirror physical tables are empty, rebuilds logical ledger grids from full_text
using ordered strategies: pipe text → spaced OCR → none.

Pipeline role: called from ``build_style_context`` before style detection.

Key exports: ``ReconstructionMeta``, ``reconstruct_tables``.

Dependencies: ``pipe_text_table_builder``, ``text_table_builder``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from docmirror.plugins.bank_statement.pipe_text_table_builder import (
    build_tables_from_pipe_text,
    count_expected_primary_rows,
    detect_pipe_header_in_text,
)
from docmirror.plugins.bank_statement.text_table_builder import build_tables_from_spaced_ocr_text

SourceKind = Literal["mirror_table", "pipe_text", "spaced_ocr", "none"]


@dataclass
class ReconstructionMeta:
    source: SourceKind
    expected_primary_rows: int = 0
    pipe_header_detected: bool = False
    pipe_parse_failed: bool = False
    pages_scanned: int = 0
    spe_primary: str | None = None
    spe_table_extraction: str | None = None


def reconstruct_tables(
    mirror_tables: list[list[list[str]]],
    full_text: str,
    *,
    page_count: int = 0,
    structure_spe: dict | None = None,
    parse_result: Any | None = None,
) -> tuple[list[list[list[str]]], ReconstructionMeta]:
    """Rebuild logical tables from Mirror tables or full text."""
    spe_primary = (structure_spe or {}).get("primary")
    spe_mode = (structure_spe or {}).get("table_extraction")

    if mirror_tables:
        expected = _mirror_table_expected_rows(
            mirror_tables,
            parse_result=parse_result,
            structure_spe=structure_spe,
        )
        return mirror_tables, ReconstructionMeta(
            source="mirror_table",
            expected_primary_rows=expected,
            pipe_header_detected=detect_pipe_header_in_text(full_text),
            pages_scanned=page_count,
            spe_primary=spe_primary,
            spe_table_extraction=spe_mode,
        )

    from docmirror.core.analyze.spe_consumer import should_block_pipe_ltro, should_force_ltro

    blocked = should_block_pipe_ltro(structure_spe)
    if blocked:
        force_pipe = False
        pipe_detected = False
    else:
        force_pipe = should_force_ltro(
            mirror_tables=mirror_tables,
            full_text=full_text,
            structure_spe=structure_spe,
        )
        pipe_detected = detect_pipe_header_in_text(full_text) or force_pipe
    pipe_tables = build_tables_from_pipe_text(full_text) if pipe_detected else []
    if pipe_tables:
        data_rows = len(pipe_tables[0]) - 1
        return pipe_tables, ReconstructionMeta(
            source="pipe_text",
            expected_primary_rows=data_rows,
            pipe_header_detected=True,
            pages_scanned=page_count,
            spe_primary=spe_primary,
            spe_table_extraction=spe_mode,
        )

    if pipe_detected:
        return [], ReconstructionMeta(
            source="none",
            expected_primary_rows=count_expected_primary_rows(full_text),
            pipe_header_detected=True,
            pipe_parse_failed=True,
            pages_scanned=page_count,
        )

    ocr_tables = build_tables_from_spaced_ocr_text(full_text)
    if ocr_tables:
        expected = len(ocr_tables[0]) - 1
        return ocr_tables, ReconstructionMeta(
            source="spaced_ocr",
            expected_primary_rows=expected,
            pipe_header_detected=False,
            pages_scanned=page_count,
        )

    return [], ReconstructionMeta(
        source="none",
        expected_primary_rows=0,
        pipe_header_detected=pipe_detected,
        pages_scanned=page_count,
    )


def _mirror_table_expected_rows(
    mirror_tables: list[list[list[str]]],
    *,
    parse_result: Any | None = None,
    structure_spe: dict | None = None,
) -> int:
    """Mirror SSOT for coverage denominator (ADR-BS-07); legacy max fallback."""
    if parse_result is not None:
        from docmirror.core.analyze.spe_consumer import mirror_expected_primary_rows

        expected = mirror_expected_primary_rows(parse_result, structure_spe)
        if expected > 0:
            return expected
    if mirror_tables:
        return max(len(tbl) - 1 for tbl in mirror_tables if tbl)
    return 0
