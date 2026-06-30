# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Parser backend protocol — abstract interface for all parser plugins.

Defines the ``ParserBackend`` protocol (PEP 544) and associated data
types (``RawParseResult``, ``RawPage``, etc.) that form the canonical
intermediate format between a parser backend and DocMirror's bridge layer.

Usage::

    class MyCustomParser:
        \"\"\"Implement the ParserBackend protocol implicitly.\"\"\"

        name = "my_parser"
        supported_formats = {"pdf", "pdf:scanned"}
        capabilities = {"text", "tables", "ocr"}

        async def parse(self, path, *, options=None) -> RawParseResult:
            ...

        @property
        def version(self) -> str:
            return "1.0.0"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# ── Capability enum ──────────────────────────────────────────────────────


class ParserCapability(str, Enum):
    """Well-known capabilities a parser backend may declare."""

    TEXT = "text"  # Text extraction
    TABLES = "tables"  # Table extraction
    READING_ORDER = "reading_order"  # Reading order detection
    OCR = "ocr"  # Optical character recognition (scanned docs)
    FORMULA = "formula"  # LaTeX formula extraction
    ACCESSIBILITY = "accessibility"  # PDF/UA tagged output
    CHART_DESCRIPTION = "chart_description"  # AI chart description


# ── Raw data types (canonical intermediate format) ───────────────────────


@dataclass
class RawText:
    """A single text element extracted from a page."""

    content: str = ""
    bbox: list[float] | None = None
    confidence: float = 1.0
    reading_order: int = 0
    font_size: float | None = None
    font_name: str | None = None
    text_opacity: float | None = None
    rendering_mode: int | None = None


@dataclass
class RawTable:
    """A table extracted from a page."""

    table_id: str = ""
    headers: list[str] = field(default_factory=list)
    data_rows: list[list[str]] = field(default_factory=list)
    bbox: list[float] | None = None
    confidence: float = 1.0
    reading_order: int = 0
    method: str = "auto"  # "grid", "ocr", "ai"


@dataclass
class RawImage:
    """An image embedded in a page."""

    image_id: str = ""
    bbox: list[float] | None = None
    width: int = 0
    height: int = 0
    caption: str | None = None


@dataclass
class RawKeyValue:
    """A key-value pair extracted from a page."""

    key: str = ""
    value: str = ""
    bbox: list[float] | None = None
    confidence: float = 1.0
    reading_order: int = 0


@dataclass
class RawPage:
    """A single page in the canonical intermediate format."""

    page_number: int = 0
    width_pt: float = 0.0
    height_pt: float = 0.0
    texts: list[RawText] = field(default_factory=list)
    tables: list[RawTable] = field(default_factory=list)
    images: list[RawImage] = field(default_factory=list)
    key_values: list[RawKeyValue] = field(default_factory=list)
    reading_order: list[int] = field(default_factory=list)


@dataclass
class RawParseResult:
    """Backend-agnostic parse output that the bridge layer consumes."""

    pages: list[RawPage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


# ── Backend protocol ─────────────────────────────────────────────────────


@runtime_checkable
class ParserBackend(Protocol):
    """Interface for a document parser backend.

    A backend knows how to parse a specific format (or multiple formats)
    and returns data in the canonical ``RawParseResult`` format that
    DocMirror's bridge layer converts to ``ParseResult``.

    The protocol is implicit — any object with the required attributes
    and methods satisfies it (PEP 544 structural subtyping).
    """

    @property
    def name(self) -> str:
        """Unique backend name, e.g. ``'pymupdf'``, ``'opendataloader'``."""
        ...

    @property
    def supported_formats(self) -> set[str]:
        """Formats this backend can parse, e.g. ``{'pdf', 'pdf:scanned'}``."""
        ...

    @property
    def capabilities(self) -> set[str]:
        """What this backend can do (see ``ParserCapability``)."""
        ...

    async def parse(
        self,
        path: str | Path,
        *,
        options: dict[str, Any] | None = None,
    ) -> RawParseResult:
        """Parse a document and return raw structured data.

        Args:
            path: Path to the document file.
            options: Backend-specific options dict.

        Returns:
            ``RawParseResult`` — backend-agnostic structured data.
        """
        ...

    @property
    def version(self) -> str:
        """Backend version string."""
        ...


__all__ = [
    "ParserBackend",
    "ParserCapability",
    "RawImage",
    "RawKeyValue",
    "RawPage",
    "RawParseResult",
    "RawTable",
    "RawText",
]
