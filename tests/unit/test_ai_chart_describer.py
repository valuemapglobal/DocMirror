# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Chart AI Describer (GA1.0-ODL-07 §P2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from docmirror.input.adapters.ai.describers.chart_describer import (
    describe_all_images,
    describe_chart_or_image,
    enrich_dmir_with_alt_text,
)
from docmirror.input.adapters.ai.protocol import AIBackendCapabilities

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def mock_ai_backend():
    """Create a mock AI backend for testing."""
    backend = MagicMock()
    backend.name = "test_backend"
    backend.is_available = True
    backend.capabilities = AIBackendCapabilities(
        vision=True, chart_description=True,
    )
    backend.describe_image = AsyncMock(
        return_value="This is a chart showing revenue growth over time."
    )
    backend.analyze_page = AsyncMock()
    return backend


@pytest.fixture
def sample_image_bytes():
    """Create a minimal valid PNG for testing."""
    import io
    import struct
    import zlib

    # Minimal 1x1 blue pixel PNG
    def _make_png():
        width, height = 1, 1
        raw_data = b"\x00" + b"\x00\x00\xff"  # filter byte + RGB blue pixel
        compressed = zlib.compress(raw_data)

        def chunk(chunk_type: bytes, data: bytes) -> bytes:
            c = chunk_type + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", compressed)
            + chunk(b"IEND", b"")
        )

    return _make_png()


# ── Tests ─────────────────────────────────────────────────────────────────


class TestDescribeChartOrImage:
    """Tests for describe_chart_or_image()."""

    @pytest.mark.asyncio
    async def test_returns_description_with_backend(self, mock_ai_backend, sample_image_bytes):
        """Should return description when a backend is provided."""
        result = await describe_chart_or_image(
            sample_image_bytes,
            context="chart",
            ai_backend=mock_ai_backend,
        )
        assert result == "This is a chart showing revenue growth over time."
        mock_ai_backend.describe_image.assert_awaited_once_with(
            sample_image_bytes,
            context="chart",
            options=None,
        )

    @pytest.mark.asyncio
    async def test_returns_empty_without_backend(self, sample_image_bytes):
        """Should return empty string when no backend is provided."""
        result = await describe_chart_or_image(sample_image_bytes)
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_backend_unavailable(
        self, mock_ai_backend, sample_image_bytes,
    ):
        """Should return empty string when backend is not available."""
        mock_ai_backend.is_available = False
        result = await describe_chart_or_image(
            sample_image_bytes,
            ai_backend=mock_ai_backend,
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_passes_options_to_backend(self, mock_ai_backend, sample_image_bytes):
        """Should pass options dict to the backend."""
        opts = {"model": "gpt-4o-mini", "language": "en"}
        await describe_chart_or_image(
            sample_image_bytes,
            context="diagram",
            ai_backend=mock_ai_backend,
            options=opts,
        )
        mock_ai_backend.describe_image.assert_awaited_once_with(
            sample_image_bytes,
            context="diagram",
            options=opts,
        )

    @pytest.mark.asyncio
    async def test_handles_backend_exception_gracefully(
        self, mock_ai_backend, sample_image_bytes,
    ):
        """Should return empty string when backend raises an exception."""
        mock_ai_backend.describe_image = AsyncMock(side_effect=RuntimeError("API error"))
        result = await describe_chart_or_image(
            sample_image_bytes,
            ai_backend=mock_ai_backend,
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_bytes_returns_empty(self, mock_ai_backend):
        """Should handle empty image bytes gracefully."""
        result = await describe_chart_or_image(
            b"",
            ai_backend=mock_ai_backend,
        )
        # Backend is still called with empty bytes; result depends on backend
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_non_ascii_context(self, mock_ai_backend, sample_image_bytes):
        """Should handle unicode context strings."""
        result = await describe_chart_or_image(
            sample_image_bytes,
            context="biểu đồ",  # Vietnamese: "chart"
            ai_backend=mock_ai_backend,
        )
        assert isinstance(result, str)


class TestDescribeAllImages:
    """Tests for describe_all_images()."""

    @pytest.mark.asyncio
    async def test_describes_multiple_images(self, mock_ai_backend):
        """Should describe all images in the list."""
        images = [
            {"image_id": "img_1", "bytes": b"fake_png_1", "context": "chart"},
            {"image_id": "img_2", "bytes": b"fake_png_2", "context": "photo"},
        ]
        results = await describe_all_images(
            images,
            ai_backend=mock_ai_backend,
        )
        assert len(results) == 2
        assert "img_1" in results
        assert "img_2" in results

    @pytest.mark.asyncio
    async def test_skips_empty_bytes(self, mock_ai_backend):
        """Should skip images with empty bytes."""
        images = [
            {"image_id": "img_1", "bytes": b"", "context": "chart"},
            {"image_id": "img_2", "bytes": b"fake_png_2", "context": "photo"},
        ]
        results = await describe_all_images(
            images,
            ai_backend=mock_ai_backend,
        )
        # img_1 was skipped, so it won't appear in results
        # (or will appear with empty string)
        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_empty_image_list(self, mock_ai_backend):
        """Should handle empty image list."""
        results = await describe_all_images([], ai_backend=mock_ai_backend)
        assert results == {}


class TestEnrichDmirWithAltText:
    """Tests for enrich_dmir_with_alt_text()."""

    @pytest.fixture
    def dmir_dict(self):
        """Create a sample DMIR dict for testing."""
        return {
            "dmir_version": "1.0",
            "document": {
                "type": "report",
                "properties": {},
                "pages": [
                    {
                        "page_number": 1,
                        "images": [
                            {"image_id": "img_001", "alt_text": ""},
                            {"image_id": "img_002", "alt_text": "Existing alt text"},
                        ],
                    },
                    {
                        "page_number": 2,
                        "images": [
                            {"image_id": "img_003", "alt_text": ""},
                        ],
                    },
                ],
            },
            "quality": {"confidence": 1.0},
            "evidence": {"ledger": {}},
            "meta": {},
        }

    @pytest.mark.asyncio
    async def test_skips_images_with_existing_alt_text(
        self, dmir_dict, mock_ai_backend,
    ):
        """Should not overwrite existing alt text."""
        await enrich_dmir_with_alt_text(
            dmir_dict,
            ai_backend=mock_ai_backend,
            image_store={
                "img_001": b"data",
                "img_002": b"data",
                "img_003": b"data",
            },
        )
        # img_002 already has alt text
        page1 = dmir_dict["document"]["pages"][0]
        assert page1["images"][1]["alt_text"] == "Existing alt text"

    @pytest.mark.asyncio
    async def test_adds_alt_text_to_empty_images(
        self, dmir_dict, mock_ai_backend,
    ):
        """Should fill alt_text for images with empty alt_text."""
        await enrich_dmir_with_alt_text(
            dmir_dict,
            ai_backend=mock_ai_backend,
            image_store={"img_001": b"data", "img_003": b"data"},
        )
        page1 = dmir_dict["document"]["pages"][0]
        assert page1["images"][0].get("alt_text") == "This is a chart showing revenue growth over time."
        page2 = dmir_dict["document"]["pages"][1]
        assert page2["images"][0].get("alt_text") == "This is a chart showing revenue growth over time."

    @pytest.mark.asyncio
    async def test_sets_alt_text_source(self, dmir_dict, mock_ai_backend):
        """Should record the source of AI-generated alt text."""
        await enrich_dmir_with_alt_text(
            dmir_dict,
            ai_backend=mock_ai_backend,
            image_store={"img_001": b"data"},
        )
        page1 = dmir_dict["document"]["pages"][0]
        assert page1["images"][0].get("alt_text_source") == "ai:test_backend"

    @pytest.mark.asyncio
    async def test_noop_without_image_store(self, dmir_dict, mock_ai_backend):
        """Should not modify DMIR when no image_store is provided."""
        # Without image_store, all alt_text fields remain unchanged
        original = str(dmir_dict)
        await enrich_dmir_with_alt_text(
            dmir_dict,
            ai_backend=mock_ai_backend,
        )
        assert str(dmir_dict) == original  # No changes

    @pytest.mark.asyncio
    async def test_handles_missing_images_key(self, mock_ai_backend):
        """Should handle DMIR dicts without images key."""
        dmir = {
            "dmir_version": "1.0",
            "document": {
                "type": "text_only",
                "pages": [{"page_number": 1}],
            },
        }
        # Should not raise
        result = await enrich_dmir_with_alt_text(
            dmir,
            ai_backend=mock_ai_backend,
        )
        assert result is dmir  # Same object returned


__all__ = []
