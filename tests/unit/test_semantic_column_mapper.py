# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.tables.char.semantic_column_mapper import SemanticColumnMapper
from docmirror.tables.pipeline.stage_structure import apply_structure_fixes


def test_semantic_column_mapper_exposes_design_components():
    mapper = SemanticColumnMapper()

    column_types = mapper.classify_columns(
        ["POSTING DATE 过账日", "VALUE DATE 起息日", "DESCRIPTION 过账内容"]
    )
    tokens = mapper.tokenize_row("2016-05-302016-05-31Salary")
    assigned = mapper.assign_to_columns(tokens, column_types)

    assert column_types == ["date", "date", "text"]
    assert tokens == [
        ("2016-05-30", "date"),
        ("2016-05-31", "date"),
        ("Salary", "text"),
    ]
    assert assigned == ["2016-05-30", "2016-05-31", "Salary"]


def test_semantic_column_mapper_keeps_duplicate_structured_values():
    mapper = SemanticColumnMapper()

    assigned = mapper.assign_to_columns(
        mapper.tokenize_row("2016-05-302016-05-30"),
        ["date", "date"],
    )

    assert assigned == ["2016-05-30", "2016-05-30"]


def test_semantic_column_mapper_repairs_fused_standard_chartered_dates():
    mapper = SemanticColumnMapper()
    column_types = mapper.classify_columns(
        ["POSTING DATE 过账日", "VALUE DATE 起息日", "DESCRIPTION 过账内容", "AMOUNT 金额"]
    )

    repaired = mapper.map_row(
        ["2016-05-302016-05-31", "", "ATM Withdrawal", "1,234.56"],
        column_types,
    )

    assert repaired == ["2016-05-30", "2016-05-31", "ATM Withdrawal", "1,234.56"]


def test_stage_structure_applies_semantic_column_mapper():
    header = ["POSTING DATE 过账日", "VALUE DATE 起息日", "DESCRIPTION 过账内容", "AMOUNT 金额"]
    rows = [
        ["2016-05-302016-05-31", "", "ATM Withdrawal", "1,234.56"],
        ["2016-06-012016-06-02", "", "Salary", "9,876.54"],
    ]

    fixed_header, fixed_rows = apply_structure_fixes(header, rows)

    assert fixed_header == header
    assert fixed_rows == [
        ["2016-05-30", "2016-05-31", "ATM Withdrawal", "1,234.56"],
        ["2016-06-01", "2016-06-02", "Salary", "9,876.54"],
    ]
