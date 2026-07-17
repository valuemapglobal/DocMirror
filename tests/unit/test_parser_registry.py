# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ParserRegistry and backend protocol (GA1.0-ODL-05)."""

from __future__ import annotations

import pytest

from docmirror.input.adapters.parsers.discovery import (
    discover_backends,
    register_discovered_backends,
)
from docmirror.input.adapters.parsers.protocol import (
    ParserBackend,
    ParserCapability,
    RawImage,
    RawKeyValue,
    RawPage,
    RawParseResult,
    RawTable,
    RawText,
)
from docmirror.input.adapters.parsers.registry import (
    ParserRegistry,
    get_registry,
    register_backend,
)

pytestmark = [pytest.mark.tier_unit]


@pytest.fixture(autouse=True)
def isolate_global_registry():
    """Prevent backend registrations in this module from leaking to later tests."""
    registry = get_registry()
    original = dict(registry._backends)
    yield
    registry._backends.clear()
    registry._backends.update(original)


@pytest.fixture
def fresh_registry():
    """Return a clean ParserRegistry with no backends."""
    return ParserRegistry()


class MockPdfBackend:
    """Minimal mock PDF backend for testing registry."""
    name = "mock_pdf"
    supported_formats = {"pdf", "pdf:digital"}
    capabilities = {"text", "tables"}
    version = "1.0.0"

    async def parse(self, path, *, options=None):
        return RawParseResult(
            pages=[],
            metadata={"backend": "mock_pdf"},
            confidence=1.0,
        )


class MockImageBackend:
    """Minimal mock image backend for testing registry."""
    name = "mock_image"
    supported_formats = {"image", "png", "jpeg"}
    capabilities = {"text", "ocr"}
    version = "1.0.0"

    async def parse(self, path, *, options=None):
        return RawParseResult(
            pages=[],
            metadata={"backend": "mock_image"},
            confidence=1.0,
        )


class MockScannedPdfBackend:
    """Mock backend specialising in scanned PDFs."""
    name = "mock_scanned"
    supported_formats = {"pdf", "pdf:scanned"}
    capabilities = {"text", "ocr", "tables"}
    version = "1.1.0"

    async def parse(self, path, *, options=None):
        return RawParseResult(
            pages=[],
            metadata={"backend": "mock_scanned"},
            confidence=0.95,
        )


class IncompleteBackend:
    """A class that does NOT implement ParserBackend protocol."""
    pass


class TestParserRegistry:
    """Suite of tests for the ParserRegistry class."""

    def test_empty_registry(self, fresh_registry):
        assert fresh_registry.count == 0
        assert fresh_registry.names == []
        assert fresh_registry.available == {}

    def test_register_backend(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        assert fresh_registry.count == 1
        assert "mock_pdf" in fresh_registry

    def test_register_multiple_backends(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        fresh_registry.register(MockImageBackend())
        assert fresh_registry.count == 2

    def test_register_duplicate_raises(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        with pytest.raises(ValueError, match="already registered"):
            fresh_registry.register(MockPdfBackend())

    def test_register_invalid_backend_raises(self, fresh_registry):
        with pytest.raises(TypeError):
            fresh_registry.register(IncompleteBackend())

    def test_select_by_format(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        backend = fresh_registry.select("pdf")
        assert backend.name == "mock_pdf"

    def test_select_with_preference(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        fresh_registry.register(MockScannedPdfBackend())
        backend = fresh_registry.select("pdf", preference="mock_scanned")
        assert backend.name == "mock_scanned"

    def test_select_preference_not_found_falls_back(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        backend = fresh_registry.select("pdf", preference="nonexistent")
        assert backend.name == "mock_pdf"

    def test_select_no_backend_raises(self, fresh_registry):
        with pytest.raises(ValueError, match="No parser backend"):
            fresh_registry.select("pdf")

    def test_select_from_multiple_formats(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        fresh_registry.register(MockScannedPdfBackend())
        backends = fresh_registry.list_for_format("pdf")
        assert len(backends) == 2

    def test_list_for_format_empty(self, fresh_registry):
        assert fresh_registry.list_for_format("pdf") == []

    def test_list_for_format_returns_only_matching(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        fresh_registry.register(MockImageBackend())
        pdf_backends = fresh_registry.list_for_format("pdf")
        assert len(pdf_backends) == 1
        assert pdf_backends[0].name == "mock_pdf"
        image_backends = fresh_registry.list_for_format("png")
        assert len(image_backends) == 1
        assert image_backends[0].name == "mock_image"

    def test_available_returns_dict(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        avail = fresh_registry.available
        assert avail == {"mock_pdf": "1.0.0"}

    def test_names_list(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        fresh_registry.register(MockImageBackend())
        assert sorted(fresh_registry.names) == ["mock_image", "mock_pdf"]

    def test_repr(self, fresh_registry):
        fresh_registry.register(MockPdfBackend())
        r = repr(fresh_registry)
        assert "ParserRegistry" in r
        assert "mock_pdf" in r


class TestGlobalRegistry:
    """Tests for the global registry singleton."""

    def test_get_registry_returns_singleton(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_register_backend_global(self):
        register_backend(MockPdfBackend())
        assert "mock_pdf" in get_registry()


class TestRawTypes:
    """Verify RawParseResult and related data classes work correctly."""

    def test_raw_parse_result_defaults(self):
        result = RawParseResult()
        assert result.pages == []
        assert result.metadata == {}
        assert result.confidence == 0.0

    def test_raw_page_defaults(self):
        page = RawPage()
        assert page.page_number == 0
        assert page.texts == []
        assert page.tables == []

    def test_raw_text_defaults(self):
        text = RawText()
        assert text.content == ""
        assert text.confidence == 1.0
        assert text.reading_order == 0

    def test_raw_table_defaults(self):
        table = RawTable()
        assert table.table_id == ""
        assert table.headers == []
        assert table.data_rows == []
        assert table.method == "auto"

    def test_raw_image_defaults(self):
        img = RawImage()
        assert img.image_id == ""
        assert img.width == 0
        assert img.height == 0

    def test_raw_key_value_defaults(self):
        kv = RawKeyValue()
        assert kv.key == ""
        assert kv.value == ""

    def test_parser_capability_enum(self):
        assert ParserCapability.TEXT.value == "text"
        assert ParserCapability.OCR.value == "ocr"
        assert ParserCapability.ACCESSIBILITY.value == "accessibility"


class TestParserBackendProtocol:
    """Verify that mock backends satisfy the ParserBackend protocol."""

    def test_mock_pdf_is_backend(self):
        assert isinstance(MockPdfBackend(), ParserBackend)

    def test_mock_image_is_backend(self):
        assert isinstance(MockImageBackend(), ParserBackend)

    def test_mock_scanned_is_backend(self):
        assert isinstance(MockScannedPdfBackend(), ParserBackend)

    def test_incomplete_is_not_backend(self):
        assert not isinstance(IncompleteBackend(), ParserBackend)


class TestDiscovery:
    """Tests for entry-point based backend discovery."""

    def test_discover_backends_returns_dict(self):
        backends = discover_backends()
        assert isinstance(backends, dict)

    def test_register_discovered_backends_returns_int(self):
        count = register_discovered_backends()
        assert isinstance(count, int)
        assert count >= 0


class TestBuiltinBackend:
    """Tests for the built-in PyMuPDF backend."""

    def test_backend_module_exists(self):
        try:
            from docmirror.input.adapters.parsers.backends.pymupdf import PyMuPDFBackend
            assert PyMuPDFBackend.name == "pymupdf"
        except ImportError:
            pytest.skip("PyMuPDF not installed")

    def test_register_builtin_backends(self):
        from docmirror.input.adapters.parsers.backends import register_builtin_backends
        count = register_builtin_backends()
        assert isinstance(count, int)

    def test_pymupdf_protocol_satisfied(self):
        try:
            from docmirror.input.adapters.parsers.backends.pymupdf import PyMuPDFBackend
            assert isinstance(PyMuPDFBackend(), ParserBackend)
        except ImportError:
            pytest.skip("PyMuPDF not installed")
