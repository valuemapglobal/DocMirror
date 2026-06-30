# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
PyMuPDF Parser Backend — Built-in PDF parser using PyMuPDF (fitz).

This backend wraps PyMuPDF (fitz) calls into the ParserBackend
protocol and produces RawParseResult output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docmirror.input.adapters.parsers.protocol import (
    ParserCapability,
    RawImage,
    RawKeyValue,
    RawPage,
    RawParseResult,
    RawTable,
    RawText,
)


class PyMuPDFBackend:
    """Built-in PyMuPDF parser backend (implements ParserBackend protocol).

    Extracts text, tables, images, and metadata from PDFs using PyMuPDF.
    This is the default backend when no other PDF parser is installed.
    """

    name = "pymupdf"
    supported_formats = {"pdf", "pdf:digital"}
    capabilities = {
        ParserCapability.TEXT,
        ParserCapability.TABLES,
        ParserCapability.READING_ORDER,
    }

    @property
    def version(self) -> str:
        try:
            import fitz

            return fitz.version[0] if hasattr(fitz, "version") else "unknown"
        except ImportError:
            return "not_installed"

    async def parse(
        self,
        path: str | Path,
        *,
        options: dict[str, Any] | None = None,
    ) -> RawParseResult:
        """Parse a PDF document using PyMuPDF.

        Args:
            path: Path to the PDF file.
            options: Optional dict with backend-specific options.

        Returns:
            RawParseResult with pages, texts, tables, images, and metadata.

        Raises:
            FileNotFoundError: If path does not exist.
            ImportError: If PyMuPDF is not installed.
        """
        import fitz

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")

        opts = options or {}
        skip_images = opts.get("skip_images", False)
        skip_tables = opts.get("skip_tables", False)

        doc = fitz.open(str(path))
        pages: list[RawPage] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            rect = page.rect

            # Text extraction
            text_dict = page.get_text("dict")
            raw_texts = self._extract_texts(text_dict)

            # Table extraction
            raw_tables: list[RawTable] = []
            if not skip_tables:
                raw_tables = self._extract_tables(text_dict, page_num)

            # Image extraction
            raw_images: list[RawImage] = []
            if not skip_images:
                raw_images = self._extract_images(page, page_num)

            # Key-value pairs
            raw_kvs = self._extract_key_values(text_dict)

            # Reading order
            reading_order = list(range(len(raw_texts) + len(raw_tables)))

            raw_page = RawPage(
                page_number=page_num + 1,
                width_pt=rect.width,
                height_pt=rect.height,
                texts=raw_texts,
                tables=raw_tables,
                images=raw_images,
                key_values=raw_kvs,
                reading_order=reading_order,
            )
            pages.append(raw_page)

        doc.close()

        return RawParseResult(
            pages=pages,
            metadata={
                "format": "PDF",
                "page_count": len(doc),
                "backend": self.name,
                "backend_version": self.version,
            },
            confidence=1.0,
        )

    # -- Internal helpers -------------------------------------------------

    def _extract_texts(self, text_dict: dict[str, Any]) -> list[RawText]:
        """Extract text elements from PyMuPDF's text dict."""
        texts: list[RawText] = []
        order = 0
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_text = ""
                font_size = None
                font_name = None
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    line_text += span_text
                    if font_size is None:
                        font_size = span.get("size")
                        font_name = span.get("font")
                if line_text.strip():
                    texts.append(
                        RawText(
                            content=line_text,
                            bbox=line.get("bbox"),
                            reading_order=order,
                            font_size=font_size,
                            font_name=font_name,
                            text_opacity=span.get("opacity", 1.0) if span else 1.0,
                        )
                    )
                    order += 1
        return texts

    def _extract_tables(self, text_dict: dict[str, Any], page_num: int) -> list[RawTable]:
        """Attempt to extract tables (placeholder — full extraction via RapidTable)."""
        return []

    def _extract_images(self, page: Any, page_num: int) -> list[RawImage]:
        """Extract image references from a PyMuPDF page."""
        images: list[RawImage] = []
        for img_index, img_info in enumerate(page.get_images(full=True)):
            try:
                xref = img_info[0]
                pix = page.parent.extract_image(xref)
                images.append(
                    RawImage(
                        image_id=f"img_{page_num + 1}_{img_index}",
                        width=pix.get("width", 0),
                        height=pix.get("height", 0),
                    )
                )
            except (IndexError, RuntimeError):
                pass
        return images

    def _extract_key_values(self, text_dict: dict[str, Any]) -> list[RawKeyValue]:
        """Extract key-value pairs from text (simple detection)."""
        kvs: list[RawKeyValue] = []
        separators = {":", "：", "=", "＝"}
        order = 0
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_text = ""
                for span in line.get("spans", []):
                    line_text += span.get("text", "")
                for sep in separators:
                    if sep in line_text:
                        parts = line_text.split(sep, 1)
                        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                            kvs.append(
                                RawKeyValue(
                                    key=parts[0].strip(),
                                    value=parts[1].strip(),
                                    bbox=line.get("bbox"),
                                    reading_order=order,
                                )
                            )
                            order += 1
                            break
        return kvs


__all__ = [
    "PyMuPDFBackend",
]
