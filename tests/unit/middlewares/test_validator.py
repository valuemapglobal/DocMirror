# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Unit tests for Validator middleware."""

import pytest
from docmirror.models.entities.parse_result import (
    ParseResult, PageContent, TableBlock, TableRow, CellValue, TextBlock,
    TextLevel, ParserInfo,
)
from docmirror.middlewares.validation.validator import Validator


@pytest.fixture
def minimal_parse_result():
    """ParseResult with one page and one small table (no artifacts)."""
    table = TableBlock(
        table_id="page1_table0",
        headers=["Date", "Amount"],
        rows=[
            TableRow(cells=[
                CellValue(text="2024-01-01"),
                CellValue(text="100.00", numeric=100.0),
            ]),
        ],
        page=1,
    )
    page = PageContent(
        page_number=1,
        tables=[table],
        texts=[TextBlock(content="Date Amount 2024-01-01 100.00", level=TextLevel.BODY)],
    )
    return ParseResult(
        pages=[page],
        parser_info=ParserInfo(parser_name="test", page_count=1),
    )


class TestValidator:
    def test_process_writes_trust_result(self, minimal_parse_result):
        validator = Validator(config={}, pass_threshold=0.7)
        result = validator.process(minimal_parse_result)
        assert result.trust is not None
        assert result.trust.validation_score > 0
        assert result.trust.validation_passed is not None
        assert "column_alignment" in result.trust.details

    def test_process_clean_table_scores_above_threshold(self, minimal_parse_result):
        validator = Validator(config={}, pass_threshold=0.5)
        result = validator.process(minimal_parse_result)
        assert result.trust.validation_score >= 0.5
        assert result.trust.validation_passed is True