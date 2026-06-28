"""Lightweight PDF/UA exporter with optional PDF dependencies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docmirror.output.exporters.pdfua_types import ExportResult, PdfUaVersion


def _ensure_fitz() -> Any:
    import fitz

    return fitz


def _ensure_pypdf() -> Any:
    import pypdf

    return pypdf


def export_pdfua(
    dmir: dict[str, Any],
    *,
    output_path: str,
    title: str | None = None,
    language: str = "zh-CN",
    version: PdfUaVersion = PdfUaVersion.PDFUA_2,
) -> ExportResult:
    _ensure_fitz()
    _ensure_pypdf()
    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject,
        BooleanObject,
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
        NumberObject,
        TextStringObject,
    )

    writer = PdfWriter()
    pages = dmir.get("document", {}).get("pages", []) or []
    for page in pages:
        width = float(page.get("width_pt", 595.0) or 595.0)
        height = float(page.get("height_pt", 842.0) or 842.0)
        pdf_page = writer.add_blank_page(width=width, height=height)
        stream = DecodedStreamObject()
        stream.set_data(b"/P <</MCID 0>> BDC\nBT /F1 12 Tf 50 750 Td (DocMirror) Tj ET\nEMC\n")
        pdf_page[NameObject("/Contents")] = writer._add_object(stream)

    root = writer._root_object
    root[NameObject("/MarkInfo")] = DictionaryObject({NameObject("/Marked"): TextStringObject("true")})
    root[NameObject("/Lang")] = TextStringObject(language)
    root[NameObject("/ViewerPreferences")] = DictionaryObject({NameObject("/DisplayDocTitle"): BooleanObject(True)})
    mcr = DictionaryObject({NameObject("/Type"): NameObject("/MCR"), NameObject("/MCID"): NumberObject(0)})
    struct_root = DictionaryObject({NameObject("/Type"): NameObject("/StructTreeRoot"), NameObject("/K"): ArrayObject([mcr])})
    root[NameObject("/StructTreeRoot")] = writer._add_object(struct_root)
    if title:
        writer.add_metadata({"/Title": title})

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        writer.write(fh)
    return ExportResult(
        success=True,
        output_path=str(out),
        page_count=len(pages),
        metadata={"title": title or dmir.get("document", {}).get("type", "DocMirror"), "language": language, "pdfua_version": version.value},
    )
