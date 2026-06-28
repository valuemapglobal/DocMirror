"""
Tests for LlmDocumentRestorer middleware.

Unit tests cover:
  - should_skip logic (LLM disabled / tables exist / entities enough / no text)
  - Injection helpers (_inject_tables, _inject_fields)
  - Edge cases (empty input, malformed data, non-dict responses)
"""

from __future__ import annotations

import pytest

from docmirror.framework.middlewares.extraction.llm_document_restorer import (
    LlmDocumentRestorer,
    _inject_tables,
    _inject_fields,
)
from docmirror.models.entities.parse_result import (
    CellValue,
    KeyValuePair,
    ParseResult,
    PageContent,
    TableBlock,
    TableRow,
    TextBlock,
)


pytestmark = [pytest.mark.tier_unit]


# ── Helpers ──

def _page_with_text(text: str) -> PageContent:
    """Create a PageContent with a single TextBlock."""
    return PageContent(
        page_number=1,
        texts=[TextBlock(content=text)],
    )


def _make_result(*, pages=None, text: str = "") -> ParseResult:
    """Factory for ParseResult with optional text content."""
    pgs = pages or [_page_with_text(text)]
    return ParseResult(pages=pgs)


# ── should_skip tests ──


class TestShouldSkip:
    """Verify should_skip logic under all conditions."""

    def test_skip_when_disabled(self, monkeypatch):
        """LLM disabled → always skip."""
        monkeypatch.setenv("DOCMIRROR_LLM_ENABLED", "false")
        restorer = LlmDocumentRestorer()
        result = _make_result(text="A" * 200)
        assert restorer.should_skip(result) is True

    def test_skip_when_tables_exist(self, monkeypatch):
        """Tables already in result → skip."""
        monkeypatch.setenv("DOCMIRROR_LLM_ENABLED", "true")
        restorer = LlmDocumentRestorer()
        page = PageContent(
            page_number=1,
            tables=[TableBlock(table_id="t1", headers=["h"], rows=[TableRow(cells=[CellValue(text="v")])])],
        )
        result = ParseResult(pages=[page])
        assert restorer.should_skip(result) is True

    def test_skip_when_entities_sufficient(self, monkeypatch):
        """Enough entities + short text → skip."""
        monkeypatch.setenv("DOCMIRROR_LLM_ENABLED", "true")
        restorer = LlmDocumentRestorer()
        page = PageContent(
            page_number=1,
            texts=[TextBlock(content="short")],
            key_values=[
                KeyValuePair(key="a", value="1"),
                KeyValuePair(key="b", value="2"),
                KeyValuePair(key="c", value="3"),
            ],
        )
        result = ParseResult(pages=[page])
        assert restorer.should_skip(result) is True

    def test_skip_when_no_text(self, monkeypatch):
        """Very little text → skip."""
        monkeypatch.setenv("DOCMIRROR_LLM_ENABLED", "true")
        restorer = LlmDocumentRestorer()
        result = _make_result(text="hi")
        assert restorer.should_skip(result) is True

    def test_not_skip_when_tables_missing_and_text_present(self, monkeypatch):
        """No tables + plenty of text → do NOT skip."""
        monkeypatch.setenv("DOCMIRROR_LLM_ENABLED", "true")
        restorer = LlmDocumentRestorer()
        result = _make_result(text="A" * 200)
        assert restorer.should_skip(result) is False


# ── Injection tests ──


class TestInjectTables:
    """Verify _inject_tables handles LLM output correctly."""

    def test_single_table(self):
        """Single valid table → injected."""
        result = ParseResult(pages=[PageContent(page_number=1)])
        tables = [[["日期", "金额"], ["2024-01-01", "100.00"]]]
        count = _inject_tables(result, tables)
        assert count == 1
        assert len(result.pages[0].tables) == 1
        tb = result.pages[0].tables[0]
        assert tb.headers == ["日期", "金额"]
        assert tb.table_id == "llm_table_0"
        assert tb.extraction_layer == "llm_restorer"

    def test_multiple_tables(self):
        """Multiple tables → all injected."""
        result = ParseResult(pages=[PageContent(page_number=1)])
        tables = [
            [["A"], ["1"]],
            [["B"], ["2"]],
        ]
        count = _inject_tables(result, tables)
        assert count == 2

    def test_empty_tables(self):
        """Empty table list → nothing injected."""
        result = ParseResult(pages=[PageContent(page_number=1)])
        count = _inject_tables(result, [])
        assert count == 0

    def test_table_with_only_header(self):
        """Header-only table → skipped."""
        result = ParseResult(pages=[PageContent(page_number=1)])
        tables = [[["Date"]]]  # Only header, no data rows
        count = _inject_tables(result, tables)
        assert count == 0

    def test_non_list_table(self):
        """Non-list entry → skipped."""
        result = ParseResult(pages=[PageContent(page_number=1)])
        tables = ["not a table"]
        count = _inject_tables(result, tables)
        assert count == 0


class TestInjectFields:
    """Verify _inject_fields handles LLM output correctly."""

    def test_simple_fields(self):
        """Simple fields → injected."""
        result = ParseResult(pages=[PageContent(page_number=1)])
        fields = {"户名": "张三", "卡号": "1234"}
        count = _inject_fields(result, fields)
        assert count == 2
        assert len(result.pages[0].key_values) == 2
        keys = {kv.key for kv in result.pages[0].key_values}
        assert keys == {"户名", "卡号"}

    def test_empty_fields(self):
        """Empty dict → nothing injected."""
        result = ParseResult(pages=[PageContent(page_number=1)])
        count = _inject_fields(result, {})
        assert count == 0

    def test_skip_empty_key(self):
        """Empty key → skipped."""
        result = ParseResult(pages=[PageContent(page_number=1)])
        fields = {"": "value"}
        count = _inject_fields(result, fields)
        assert count == 0

    def test_skip_empty_value(self):
        """Empty value → skipped."""
        result = ParseResult(pages=[PageContent(page_number=1)])
        fields = {"key": ""}
        count = _inject_fields(result, fields)
        assert count == 0


# ── Integration: end-to-end with mock LLM ──


class TestLlmDocumentRestorerProcess:
    """Verify process() orchestrates LLM call + injection correctly."""

    def test_process_skips_when_disabled(self, monkeypatch):
        """With LLM disabled → no mutation."""
        monkeypatch.setenv("DOCMIRROR_LLM_ENABLED", "false")
        restorer = LlmDocumentRestorer()
        result = _make_result(text="A" * 500)
        output = restorer.process(result)
        assert len(output.pages[0].tables) == 0
        assert len(output.pages[0].key_values) == 0

    def test_process_handles_llm_failure_gracefully(self, monkeypatch):
        """LLM call fails → result passes through unchanged."""
        monkeypatch.setenv("DOCMIRROR_LLM_ENABLED", "true")

        restorer = LlmDocumentRestorer()
        restorer.should_skip = lambda r: False
        from unittest.mock import patch
        with patch("docmirror.framework.middlewares.extraction.llm_document_restorer._call_llm", return_value=None):
            result = _make_result(text="A" * 200)
            output = restorer.process(result)
            assert len(output.pages[0].tables) == 0


class TestLlmResponseParsing:
    """Verify LLM JSON responses are parsed and injected correctly."""

    def test_mock_llm_response_injected(self, monkeypatch):
        """A valid LLM response → tables and fields injected."""
        monkeypatch.setenv("DOCMIRROR_LLM_ENABLED", "true")

        mock_response = {
            "document_type": "bank_statement",
            "confidence": 0.95,
            "tables": [[["日期", "金额"], ["2024-01-01", "100.00"]]],
            "fields": {"户名": "测试"},
        }

        restorer = LlmDocumentRestorer()
        restorer.should_skip = lambda r: False
        from unittest.mock import patch
        with patch("docmirror.framework.middlewares.extraction.llm_document_restorer._call_llm", return_value=mock_response):
            result = _make_result(text="A" * 200)
            output = restorer.process(result)

            assert len(output.pages[0].tables) == 1
            assert output.pages[0].tables[0].headers == ["日期", "金额"]
            assert len(output.pages[0].key_values) == 1
            assert output.pages[0].key_values[0].key == "户名"
