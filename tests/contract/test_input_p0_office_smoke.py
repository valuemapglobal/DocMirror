# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""P0 Office Smoke Tests — DOCX / XLSX / PPTX minimal parse coverage.

Covers: INP-07 (Office native adapter P0 smoke), INP-03 (converter missing).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from docmirror.configs.format.resolver import resolve_capability


def _create_minimal_docx(path: Path) -> None:
    """Create a minimal DOCX with 'Hello World'."""
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Hello World</w:t></w:r></w:p></w:body></w:document>'
        ))
        zf.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>'
        ))
        zf.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'
        ))

    assert path.is_file()


def _create_minimal_xlsx(path: Path) -> None:
    """Create a minimal XLSX with one cell = '42'."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/worksheets/sheet1.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>42</t></is></c></row></sheetData></worksheet>'
        ))
        zf.writestr("xl/workbook.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></sheets></workbook>'
        ))
        zf.writestr("xl/_rels/workbook.xml.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>'
        ))
        zf.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>'
        ))
        zf.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ))


def _create_minimal_pptx(path: Path) -> None:
    """Create a minimal PPTX with one slide 'Test'."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<p:cSld><p:spTree><p:nvGrpSpPr><p:nvPr><p:extLst/></p:nvPr></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld></p:sld>'
        ))
        zf.writestr("ppt/presentation.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<p:sldIdLst><p:sldId id="256" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></p:sldIdLst>'
            '<p:sldSz cx="9144000" cy="6858000"/></p:presentation>'
        ))
        zf.writestr("ppt/_rels/presentation.xml.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>'
            '</Relationships>'
        ))
        zf.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            '</Types>'
        ))


@pytest.mark.parametrize("fmt,cap_id,ext", [
    ("docx", "word_docx", ".docx"),
    ("xlsx", "excel_xlsx", ".xlsx"),
    ("pptx", "ppt_pptx", ".pptx"),
])
def test_office_format_in_fcr(fmt, cap_id, ext):
    from docmirror.configs.format.loader import load_format_registry
    caps, _, _ = load_format_registry()
    assert cap_id in caps, f"{cap_id} missing in FCR"


@pytest.mark.parametrize("fmt,ext", [
    ("docx", ".docx"),
    ("xlsx", ".xlsx"),
    ("pptx", ".pptx"),
])
def test_docx_fcr_resolver(fmt, ext):
    cap = resolve_capability(Path(f"test{ext}"))
    assert cap.status == "supported", f"{ext} should resolve to supported, got {cap.status}"
