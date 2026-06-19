# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for extraction_runner and archive FCR integration."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from docmirror.adapters.archive.archive import ArchiveAdapter
from docmirror.adapters.image.image import ImageAdapter
from docmirror.adapters.pdf.pdf import PDFAdapter
from docmirror.configs.format.resolver import _extension_candidates, resolve_capability
from docmirror.framework.dispatcher import ParserDispatcher
from docmirror.framework.extraction_runner import run_extraction_chain
from docmirror.models.entities.parse_result import (
    PageContent,
    ParseResult,
    ParserInfo,
    ResultStatus,
    TextBlock,
    TextLevel,
)


def test_extension_candidates_longest_first():
    assert _extension_candidates(Path("report.tar.gz")) == [".tar.gz", ".gz"]
    assert _extension_candidates(Path("scan.png")) == [".png"]


@pytest.mark.asyncio
async def test_msg_without_extract_msg_returns_converter_error(tmp_path):
    msg = tmp_path / "sample.msg"
    msg.write_bytes(b"\xd0\xcf\x11\xe0")
    result = await ParserDispatcher().process(msg)
    assert result.status == ResultStatus.FAILURE
    assert result.error is not None
    assert result.error.code == "FORMAT_REQUIRES_CONVERTER"


@pytest.mark.asyncio
async def test_archive_json_child_via_extraction_chain(tmp_path):
    zpath = tmp_path / "batch.zip"
    payload = {"account": "12345", "name": "test"}
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("nested/data.json", json.dumps(payload))

    adapter = ArchiveAdapter()
    result = await adapter.to_parse_result(zpath)
    assert result.success
    assert result.pages
    assert any(p.source_member == "data.json" for p in result.pages)
    assert any(p.key_values for p in result.pages)


@pytest.mark.asyncio
async def test_image_ocr_only_env_uses_fallback(tmp_path, monkeypatch):
    png = tmp_path / "tiny.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\x0d\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    monkeypatch.setenv("DOCMIRROR_IMAGE_OCR_ONLY", "1")
    cap = resolve_capability(png)
    ctx = {"file_type": "image", "content_model": cap.content_model}
    result = await run_extraction_chain(cap, png, ctx, enhance_mode="standard", t0=0.0)
    assert result.parser_info.parser_name in ("ImageAdapter", "DocMirror", "PDFAdapter")


@pytest.mark.asyncio
async def test_image_fallback_when_primary_empty(tmp_path):
    cap = resolve_capability(Path("x.png"))
    empty = ParseResult(
        pages=[PageContent(page_number=0, texts=[])],
        parser_info=ParserInfo(parser_name="PDFAdapter"),
        status=ResultStatus.SUCCESS,
    )
    fb = ParseResult(
        pages=[
            PageContent(
                page_number=0,
                texts=[TextBlock(content="ocr line", level=TextLevel.BODY)],
            )
        ],
        parser_info=ParserInfo(parser_name="ImageAdapter"),
        status=ResultStatus.SUCCESS,
    )

    with (
        patch.object(PDFAdapter, "perceive", AsyncMock(return_value=empty)),
        patch.object(ImageAdapter, "perceive", AsyncMock(return_value=fb)),
    ):
        result = await run_extraction_chain(
            cap,
            tmp_path / "x.png",
            {"file_type": "image", "content_model": cap.content_model},
            enhance_mode="standard",
        )
    assert result.parser_info.parser_name == "ImageAdapter"
    assert "ocr line" in result.full_text


@pytest.mark.asyncio
async def test_image_ocr_force_uses_fallback_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCMIRROR_IMAGE_OCR_ONLY", raising=False)
    cap = resolve_capability(Path("x.png"))
    fb = ParseResult(
        pages=[PageContent(page_number=0, texts=[TextBlock(content="forced ocr", level=TextLevel.BODY)])],
        parser_info=ParserInfo(parser_name="ImageAdapter"),
        status=ResultStatus.SUCCESS,
    )

    with patch.object(ImageAdapter, "perceive", AsyncMock(return_value=fb)) as mock_fb:
        result = await run_extraction_chain(
            cap,
            tmp_path / "x.png",
            {"file_type": "image", "content_model": cap.content_model, "ocr_mode": "force"},
            enhance_mode="standard",
        )

    mock_fb.assert_awaited_once()
    assert "forced ocr" in result.full_text


@pytest.mark.asyncio
async def test_image_ocr_off_disables_fallback(tmp_path):
    cap = resolve_capability(Path("x.png"))
    empty = ParseResult(
        pages=[PageContent(page_number=0, texts=[])],
        parser_info=ParserInfo(parser_name="PDFAdapter"),
        status=ResultStatus.SUCCESS,
    )
    fb = ParseResult(
        pages=[PageContent(page_number=0, texts=[TextBlock(content="ocr line", level=TextLevel.BODY)])],
        parser_info=ParserInfo(parser_name="ImageAdapter"),
        status=ResultStatus.SUCCESS,
    )

    with (
        patch.object(PDFAdapter, "perceive", AsyncMock(return_value=empty)),
        patch.object(ImageAdapter, "perceive", AsyncMock(return_value=fb)) as mock_fb,
    ):
        result = await run_extraction_chain(
            cap,
            tmp_path / "x.png",
            {"file_type": "image", "content_model": cap.content_model, "ocr_mode": "off"},
            enhance_mode="standard",
        )

    mock_fb.assert_not_awaited()
    assert result.parser_info.parser_name == "PDFAdapter"
    assert result.full_text == ""
