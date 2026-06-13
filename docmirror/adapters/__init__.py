# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Adapters — Format-specific document converters.
================================================

Each adapter is responsible for:
    1. Converting a specific file format into an immutable ``BaseResult``.
    2. Inheriting ``perceive()`` from ``BaseParser`` for unified pipeline → ``ParseResult``.

Adapters contain NO business logic — all domain-specific enhancement
is handled by the middleware pipeline downstream.

Supported formats:
    - PDF      → PDFAdapter
    - Image    → PDFAdapter (CoreExtractor) with ImageAdapter OCR fallback
    - Word     → WordAdapter (.docx via python-docx)
    - Excel    → ExcelAdapter (.xlsx / .csv; .xls via TranscodingGate)
    - PPT      → PPTAdapter (.pptx; .ppt via TranscodingGate)
    - Email    → EmailAdapter (.eml via stdlib email)
    - HTML     → WebAdapter (raw text extraction)
    - JSON/CSV → StructuredAdapter (JSON/XML); CSV also routable via ExcelAdapter
    - OFD      → OFDAdapter (e-invoice / fiscal receipt — ZIP/XML text extraction)
    - Archive  → ArchiveAdapter (.zip/.rar batch — recursive child dispatch)
"""

from .archive import ArchiveAdapter
from .data.structured import StructuredAdapter
from .image.image import ImageAdapter
from .ofd import OFDAdapter
from .office.excel import ExcelAdapter
from .office.ppt import PPTAdapter
from .office.word import WordAdapter
from .pdf.pdf import PDFAdapter
from .web.email import EmailAdapter
from .web.web import WebAdapter

__all__ = [
    "ArchiveAdapter",
    "PDFAdapter",
    "ImageAdapter",
    "EmailAdapter",
    "ExcelAdapter",
    "WordAdapter",
    "PPTAdapter",
    "StructuredAdapter",
    "WebAdapter",
    "OFDAdapter",
]
