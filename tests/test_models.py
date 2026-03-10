"""
Data model tests — verify frozen models and serialization.
"""

import pytest
from docmirror.models.entities.domain import BaseResult, Block, PageLayout


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


class TestBaseResult:
    """Test BaseResult model."""

    def test_create_empty_result(self):
        """Should create an empty result."""
        result = BaseResult(pages=(), full_text="", metadata={})
        assert len(result.pages) == 0
        assert result.full_text == ""

    def test_create_result_with_pages(self):
        """Should create a result with pages."""
        block = Block(block_type="text", raw_content="content", page=0)
        page = PageLayout(page_number=0, blocks=(block,))
        result = BaseResult(
            pages=(page,),
            full_text="content",
            metadata={"source_format": "pdf"},
        )
        assert len(result.pages) == 1
        assert result.metadata["source_format"] == "pdf"
