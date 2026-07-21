# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Data model tests — verify frozen models and serialization.
"""

import pytest

from docmirror.models.entities.domain import Block, PageLayout

pytestmark = [pytest.mark.tier_smoke]


class TestBlock:
    """Test Block model."""

    def test_create_text_block(self):
        """Should create a text block."""
        block = Block(block_type="text", raw_content="Hello world", page=0)
        assert block.block_type == "text"
        assert block.raw_content == "Hello world"
        assert block.page == 0

    def test_create_table_block(self):
        """Should create a table block with list data."""
        data = [["A", "B"], ["1", "2"]]
        block = Block(block_type="table", raw_content=data, page=0)
        assert block.block_type == "table"
        assert block.raw_content == data


class TestPageLayout:
    """Test PageLayout model."""

    def test_create_page(self):
        """Should create a page with blocks."""
        blocks = (
            Block(block_type="title", raw_content="Title", page=0),
            Block(block_type="text", raw_content="Body", page=0),
        )
        page = PageLayout(page_number=0, blocks=blocks)
        assert page.page_number == 0
        assert len(page.blocks) == 2
