# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SPE consumer + SDU row reconciliation tests."""

from __future__ import annotations

from docmirror.evidence.spe_consumer import (
    read_structure_spe,
    should_block_pipe_ltro,
    should_force_ltro,
    spe_ltro_warnings,
)
from docmirror.evidence.structure_provenance import apply_logical_tables_spe
from docmirror.tables.structure_detect import count_primary_pipe_rows, detect_pipe_grid_in_text
from docmirror.models.entities.parse_result import ParserInfo, ParseResult
from docmirror.plugins.bank_statement.ltro import reconstruct_tables
from docmirror.plugins.bank_statement.pipe_text_table_builder import build_tables_from_pipe_text
from tests.unit.test_pipe_text_table_builder import _synthetic_boc_text


def test_should_force_ltro_on_mismatch_reason():
    spe = {
        "primary": "section_led",
        "competitors": {"H_pipe_grid": 0.9},
        "table_extraction": "skipped",
        "table_extraction_skipped_reason": "route_section_dominant_mismatch",
    }
    assert should_force_ltro(mirror_tables=[], full_text="", structure_spe=spe) is True


def test_should_block_pipe_ltro_on_section_route():
    spe = {
        "primary": "section_led",
        "competitors": {"H_pipe_grid": 0.1},
        "table_extraction": "skipped",
        "table_extraction_skipped_reason": "route_section_dominant",
    }
    assert should_block_pipe_ltro(spe) is True
    assert should_force_ltro(mirror_tables=[], full_text="", structure_spe=spe) is False


def test_ltro_skips_pipe_when_spe_blocks():
    spe = {
        "primary": "section_led",
        "competitors": {"H_pipe_grid": 0.1},
        "table_extraction": "skipped",
        "table_extraction_skipped_reason": "route_section_dominant",
    }
    text = _synthetic_boc_text([])
    tables, meta = reconstruct_tables([], text, structure_spe=spe)
    assert meta.source != "pipe_text"
    assert tables == []


def test_spe_ltro_warnings_mismatch():
    spe = {"table_extraction_skipped_reason": "route_section_dominant_mismatch", "competitors": {}}
    warnings = spe_ltro_warnings(spe, "pipe_text")
    assert "spe:mismatch_section_route_with_pipe_grid" in warnings


def test_read_structure_spe_from_parse_result():
    pr = ParseResult()
    pr.parser_info = ParserInfo(
        structure={
            "primary": "table_led",
            "competitors": {"H_pipe_grid": 0.9},
            "table_extraction": "full",
        }
    )
    spe = read_structure_spe(pr)
    assert spe["primary"] == "table_led"


def test_sdu_plugin_row_count_within_one_percent():
    rows = []
    for i in range(2, 77):
        rows.append(
            f"| {i:2d} |220401|220401|网上支付|    |ref{i}|        100.00|                  |"
            f"           {1000 + i}.00|ref |counterparty |"
        )
    text = _synthetic_boc_text(rows)
    sdu_rows = count_primary_pipe_rows(text)
    plugin_tables = build_tables_from_pipe_text(text)
    plugin_rows = len(plugin_tables[0]) - 1 if plugin_tables else 0
    assert sdu_rows >= 3
    assert plugin_rows >= 3
    assert abs(sdu_rows - plugin_rows) / max(sdu_rows, 1) <= 0.01


def test_reconstruct_tables_records_spe_fields():
    spe = {"primary": "table_led", "table_extraction": "full", "competitors": {"H_pipe_grid": 1.0}}
    tables = [[["a"], ["1"]]]
    _, meta = reconstruct_tables(tables, "x", structure_spe=spe)
    assert meta.spe_primary == "table_led"
    assert meta.spe_table_extraction == "full"


def test_apply_logical_tables_spe_m11():
    spe = {"primary": "table_led", "competitors": {}, "table_extraction": "full"}
    out = apply_logical_tables_spe(
        spe,
        logical_table_count=1,
        physical_table_count=42,
        dual_view=True,
    )
    assert out["logical_table_count"] == 1
    assert out["physical_table_count"] == 42
    assert out["dual_view"] is True
