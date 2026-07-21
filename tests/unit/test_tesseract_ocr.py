# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Tesseract OCR Backend (GA1.0-ODL-07 §P2)."""

from __future__ import annotations

import os
import shutil
from unittest.mock import MagicMock, patch

import pytest

from docmirror.ocr.backends.tesseract import (
    ALL_TESSERACT_LANGUAGES,
    LANGUAGE_GROUPS,
    TesseractBackend,
    TesseractOCRResult,
    TesseractPageResult,
    get_installed_languages,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _create_test_image(text: str = "Hello World", width: int = 400, height: int = 100) -> bytes:
    """Create a simple test image with text rendered on it."""
    try:
        import io

        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (width, height), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 40), text, fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # Return a minimal valid PNG if PIL not available
        import io
        import struct
        import zlib

        raw_data = b"\x00" + b"\xff\xff\xff" * width  # white pixel row
        compressed = zlib.compress(raw_data)

        def chunk(chunk_type: bytes, data: bytes) -> bytes:
            c = chunk_type + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", compressed)
            + chunk(b"IEND", b"")
        )


# ── Tests ──────────────────────────────────────────────────────────────────


class TestTesseractBackendBasic:
    """Basic tests for TesseractBackend (no tesseract binary required)."""

    def test_name(self):
        backend = TesseractBackend()
        assert backend.name == "tesseract"

    def test_supported_languages_contains_english(self):
        backend = TesseractBackend()
        langs = backend.supported_languages
        assert "eng" in langs
        assert "chi_sim" in langs
        assert "jpn" in langs

    def test_language_groups_completeness(self):
        """All language groups combined should equal ALL_TESSERACT_LANGUAGES."""
        all_grouped = set().union(*LANGUAGE_GROUPS.values())
        assert all_grouped == set(ALL_TESSERACT_LANGUAGES)

    def test_get_installed_languages_returns_list(self):
        langs = get_installed_languages()
        assert isinstance(langs, list)

    def test_backend_not_available_without_pytesseract(self):
        backend = TesseractBackend()
        with patch.object(backend, "have_pytesseract", False):
            assert not backend.is_available

    def test_backend_not_available_without_tesseract_binary(self):
        with patch("shutil.which", return_value=None):
            backend = TesseractBackend()
            backend.have_pytesseract = True
            assert not backend.is_available

    def test_tesseract_ocr_result_defaults(self):
        result = TesseractOCRResult()
        assert result.text == ""
        assert result.confidence == 0.0
        assert result.bbox is None
        assert result.block_num == 0

    def test_tesseract_page_result_defaults(self):
        result = TesseractPageResult()
        assert result.text == ""
        assert result.words == []
        assert result.confidence == 0.0
        assert result.language == "eng"


class TestTesseractOCRIntegration:
    """Integration tests that require the Tesseract binary."""

    @pytest.fixture(autouse=True)
    def _check_tesseract(self):
        """Skip all tests if Tesseract is not installed."""
        if not shutil.which("tesseract"):
            pytest.skip("Tesseract binary not found on this system")
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            pytest.skip("pytesseract not installed")

    def test_initialize_backend(self):
        """Should initialize successfully when tesseract is available."""
        backend = TesseractBackend()
        assert backend.is_available
        assert backend.name == "tesseract"

    def test_initialized_languages(self):
        """Should return a list of installed languages."""
        backend = TesseractBackend()
        langs = backend.installed_languages
        assert isinstance(langs, list)
        assert "eng" in langs

    def test_ocr_simple_text(self):
        """Should extract text from a simple image."""
        backend = TesseractBackend()
        image = _create_test_image("Hello World")
        result = backend.ocr(image, lang="eng")
        assert isinstance(result, TesseractPageResult)
        assert isinstance(result.text, str)
        assert len(result.text) > 0
        assert "Hello" in result.text or "hello" in result.text.lower()

    def test_ocr_returns_metadata(self):
        """OCR result should include metadata like confidence and duration."""
        backend = TesseractBackend()
        image = _create_test_image("Test 123")
        result = backend.ocr(image, lang="eng")
        assert result.confidence >= 0.0
        assert result.duration_ms > 0
        assert result.language == "eng"

    def test_ocr_returns_word_level_data(self):
        """OCR result should include per-word data with bounding boxes."""
        backend = TesseractBackend()
        image = _create_test_image("Hello World")
        result = backend.ocr(image, lang="eng")
        assert len(result.words) > 0
        word = result.words[0]
        assert hasattr(word, "text")
        assert hasattr(word, "confidence")
        assert result.lines is not None

    def test_ocr_to_dict_serialization(self):
        """ocr_to_dict should return serializable dict."""
        backend = TesseractBackend()
        image = _create_test_image("Test")
        d = backend.ocr_to_dict(image, lang="eng")
        assert isinstance(d, dict)
        assert "text" in d
        assert "confidence" in d
        assert "language" in d
        assert "duration_ms" in d
        assert "word_count" in d
        assert d["language"] == "eng"

    def test_ocr_with_custom_language(self):
        """Should handle multi-language OCR."""
        backend = TesseractBackend()
        image = _create_test_image("Hello")
        result = backend.ocr(image, lang="eng+fra")
        assert isinstance(result, TesseractPageResult)
        assert "+" in result.language

    def test_ocr_with_empty_image(self):
        """Should handle empty/dark images without crashing."""
        backend = TesseractBackend()
        image = _create_test_image("", width=50, height=50)
        result = backend.ocr(image, lang="eng")
        assert isinstance(result, TesseractPageResult)

    def test_ocr_timeout(self):
        """Should handle timeout parameter."""
        backend = TesseractBackend()
        image = _create_test_image("Test")
        result = backend.ocr(image, lang="eng", timeout=30)
        assert isinstance(result, TesseractPageResult)

    def test_psm_modes(self):
        """Should accept different PSM values."""
        backend = TesseractBackend()
        image = _create_test_image("Test")
        for psm in [3, 6, 7]:
            result = backend.ocr(image, lang="eng", psm=psm)
            assert isinstance(result, TesseractPageResult)


class TestLanguageSupport:
    """Tests for language support data structures."""

    def test_european_languages(self):
        assert "eng" in LANGUAGE_GROUPS["european"]
        assert "fra" in LANGUAGE_GROUPS["european"]
        assert "deu" in LANGUAGE_GROUPS["european"]

    def test_asian_languages(self):
        assert "chi_sim" in LANGUAGE_GROUPS["asian"]
        assert "jpn" in LANGUAGE_GROUPS["asian"]

    def test_middle_east_languages(self):
        assert "ara" in LANGUAGE_GROUPS["middle_east"]
        assert "heb" in LANGUAGE_GROUPS["middle_east"]

    def test_all_languages_group_coverage(self):
        """Every language in ALL_TESSERACT_LANGUAGES should be in a group."""
        all_grouped = set()
        for group_langs in LANGUAGE_GROUPS.values():
            all_grouped.update(group_langs)
        assert all_grouped == set(ALL_TESSERACT_LANGUAGES), (
            f"Unaccounted languages: {set(ALL_TESSERACT_LANGUAGES) - all_grouped}"
        )

    def test_no_duplicates_in_groups(self):
        """No language should appear in multiple groups."""
        seen = set()
        for group_name, group_langs in LANGUAGE_GROUPS.items():
            for lang in group_langs:
                assert lang not in seen, f"Duplicate language '{lang}' in group '{group_name}'"
                seen.add(lang)

    def test_all_tesseract_languages_sorted(self):
        """ALL_TESSERACT_LANGUAGES should be sorted."""
        assert ALL_TESSERACT_LANGUAGES == sorted(ALL_TESSERACT_LANGUAGES)


__all__ = []
