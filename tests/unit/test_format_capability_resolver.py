# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Format Capability Registry."""

from pathlib import Path

import pytest

from docmirror.configs.format.enhancement import resolve_enhancement_profile, transport_to_content_model
from docmirror.configs.format.resolver import resolve_capability
from docmirror.framework.dispatcher import ParserDispatcher


def test_resolve_pdf_capability():
    cap = resolve_capability(Path("invoice.pdf"))
    assert cap.id == "pdf_native"
    assert cap.transport == "pdf"
    assert cap.status == "supported"
    assert cap.content_model == "fixed_layout_rasterizable"


def test_resolve_image_capability():
    cap = resolve_capability(Path("scan.png"))
    assert cap.transport == "image"
    assert cap.binding is not None
    assert cap.binding.fallback is not None


def test_wps_unsupported():
    cap = resolve_capability(Path("doc.wps"))
    assert cap.status == "unsupported"
    assert cap.id == "wps_word"


def test_xml_supported_via_fcr():
    cap = resolve_capability(Path("data.xml"))
    assert cap.status == "supported"
    assert cap.binding is not None
    assert cap.binding.deserializer == "xml"


def test_enhancement_profile_fixed_layout():
    mws = resolve_enhancement_profile("fixed_layout_rasterizable", "standard")
    assert "EvidenceEngine" in mws
    assert "EntityExtractor" in mws


def test_enhancement_profile_container_empty():
    mws = resolve_enhancement_profile("container", "standard")
    assert mws == []


def test_transport_to_content_model_ofd():
    assert transport_to_content_model("ofd") == "fixed_layout_rasterizable"


@pytest.mark.asyncio
async def test_dispatcher_rejects_wps(tmp_path):
    wps = tmp_path / "file.wps"
    wps.write_bytes(b"\x00\x01")
    result = await ParserDispatcher().process(wps)
    assert result.status.value == "failure"
    assert result.error is not None
    assert result.error.code == "UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_dispatcher_doc_without_soffice_returns_converter_error(tmp_path):
    doc = tmp_path / "legacy.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0")
    from unittest.mock import patch

    with patch("shutil.which", return_value=None):
        result = await ParserDispatcher().process(doc)
    assert result.status.value == "failure"
    assert result.error is not None
    assert result.error.code == "FORMAT_REQUIRES_CONVERTER"
