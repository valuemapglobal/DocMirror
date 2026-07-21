# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for MIRROR_STRUCTURE TQG oracles."""

from __future__ import annotations

from docmirror.eval.tqg.mirror_structure_oracles import run_mirror_structure_oracle
from docmirror.models.entities.parse_result import ParseResult, ParserInfo


def _meta(structure: dict, *, table_count: int = 0):
    result = ParseResult(parser_info=ParserInfo(structure=structure))
    return {"result": result, "table_count": table_count}


def test_oracle_passes_table_led_pipe():
    structure = {
        "primary": "table_led",
        "competitors": {"H_pipe_grid": 0.91, "H_section": 0.3},
        "table_extraction": "full",
        "table_extraction_skipped_reason": None,
    }
    report = run_mirror_structure_oracle(
        _meta(structure),
        {
            "primary": "table_led",
            "min_H_pipe_grid": 0.85,
            "forbidden_skip_reasons": ["route_section_dominant_mismatch"],
        },
        case_id="boc_pipe",
        track="mirror_structure",
    )
    assert report.passed, report.failures


def test_oracle_fails_mismatch_reason():
    structure = {
        "primary": "section_led",
        "competitors": {"H_pipe_grid": 0.9},
        "table_extraction_skipped_reason": "route_section_dominant_mismatch",
    }
    report = run_mirror_structure_oracle(
        _meta(structure, table_count=0),
        {"forbidden_skip_reasons": ["route_section_dominant_mismatch"]},
    )
    assert not report.passed
    assert any("route_section_dominant_mismatch" in f for f in report.failures)


def test_oracle_requires_skip_reason_when_empty_tables():
    structure = {
        "primary": "section_led",
        "competitors": {"H_pipe_grid": 0.1},
        "table_extraction": "skipped",
        "table_extraction_skipped_reason": "route_section_dominant",
    }
    report = run_mirror_structure_oracle(
        _meta(structure, table_count=0),
        {"require_skip_reason_when_tables_empty": True},
    )
    assert report.passed, report.failures
