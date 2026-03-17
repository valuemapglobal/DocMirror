# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Unit tests for Validator middleware (G2 L1 middleware coverage)."""

import pytest
from docmirror.models.entities.domain import BaseResult, Block, PageLayout
from docmirror.models.entities.enhanced import EnhancedResult
from docmirror.middlewares.validation.validator import Validator


@pytest.fixture
def minimal_base_result():
    """BaseResult with one page and one small table (no artifacts)."""
    block = Block(
        block_type="table",
        raw_content=[["Date", "Amount"], ["2024-01-01", "100.00"]],
        page=1,
    )
    page = PageLayout(page_number=1, blocks=(block,))
    return BaseResult(pages=(page,), full_text="Date Amount 2024-01-01 100.00", metadata={})


@pytest.fixture
def enhanced_from_minimal(minimal_base_result):
    return EnhancedResult.from_base_result(minimal_base_result)


class TestValidator:
    def test_process_injects_validation_into_enhanced_data(self, enhanced_from_minimal):
        validator = Validator(config={}, pass_threshold=0.7)
        result = validator.process(enhanced_from_minimal)
        assert "validation" in result.enhanced_data
        val = result.enhanced_data["validation"]
        assert "total_score" in val
        assert "passed" in val
        assert "details" in val

    def test_process_clean_table_scores_above_threshold(self, enhanced_from_minimal):
        validator = Validator(config={}, pass_threshold=0.5)
        result = validator.process(enhanced_from_minimal)
        val = result.enhanced_data["validation"]
        assert val["total_score"] >= 0.5
        assert val["passed"] is True