# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for StructuredAdapter XML/TXT deserializers."""

from pathlib import Path

import pytest

from docmirror.input.adapters.data.structured import StructuredAdapter


@pytest.mark.asyncio
async def test_structured_xml(tmp_path: Path):
    xml = tmp_path / "sample.xml"
    xml.write_text(
        '<?xml version="1.0"?><root id="1"><item>hello</item></root>',
        encoding="utf-8",
    )
    result = await StructuredAdapter().to_parse_result(xml, deserializer="xml")
    assert result.pages
    assert result.pages[0].key_values or result.pages[0].tables


@pytest.mark.asyncio
async def test_structured_txt_lines(tmp_path: Path):
    txt = tmp_path / "ledger.txt"
    txt.write_text("line one\nline two\n", encoding="utf-8")
    result = await StructuredAdapter().to_parse_result(txt, deserializer="txt")
    assert len(result.pages[0].texts) == 2


@pytest.mark.asyncio
async def test_structured_txt_tsv(tmp_path: Path):
    txt = tmp_path / "data.txt"
    txt.write_text("a\tb\n1\t2\n", encoding="utf-8")
    result = await StructuredAdapter().to_parse_result(txt, deserializer="txt")
    assert result.pages[0].tables
    assert result.pages[0].tables[0].headers == ["a", "b"]
