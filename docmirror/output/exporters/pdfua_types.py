"""PDF/UA exporter type definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PdfUaVersion(str, Enum):
    PDFUA_1 = "PDF/UA-1"
    PDFUA_2 = "PDF/UA-2"


@dataclass
class ExportResult:
    success: bool = True
    output_path: str = ""
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
