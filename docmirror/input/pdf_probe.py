# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PDF Probe — lightweight pre-extraction check for encrypted/damaged/page-count.

Purpose: Open the PDF with PyMuPDF without extraction, classify into:
    - normal (openable, not encrypted, has pages)
    - encrypted (needs password)
    - damaged (structure corruption)

Returns a structured ``PdfProbeResult`` so callers can produce stable error
envelopes before the adapter pipeline runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PdfProbeResult:
    """PDF probe outcome."""

    status: str = "unknown"  # ok | encrypted | damaged | unreadable
    page_count: int = 0
    is_encrypted: bool = False
    needs_password: bool = False
    is_damaged: bool = False
    error_code: str = ""
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def probe_pdf(path: Path) -> PdfProbeResult:
    """Open PDF with PyMuPDF and classify its state."""
    import fitz  # PyMuPDF

    result = PdfProbeResult()

    if not path.is_file():
        result.status = "unreadable"
        result.error_code = "FILE_NOT_FOUND"
        result.error_message = f"File not found: {path}"
        return result

    try:
        doc = fitz.open(str(path))
    except fitz.FileDataError as e:
        result.status = "damaged"
        result.is_damaged = True
        result.error_code = "DAMAGED_PDF"
        result.error_message = str(e)
        logger.warning("[PdfProbe] Damaged PDF: %s — %s", path.name, e)
        return result
    except Exception as e:
        result.status = "damaged"
        result.is_damaged = True
        result.error_code = "DAMAGED_PDF"
        result.error_message = str(e)
        logger.warning("[PdfProbe] Unreadable PDF: %s — %s", path.name, e)
        return result

    try:
        if doc.needs_pass or doc.is_encrypted:
            result.status = "encrypted"
            result.is_encrypted = True
            result.needs_password = True
            result.error_code = "ENCRYPTED_PDF"
            result.error_message = "PDF is password-protected"
            logger.info("[PdfProbe] Encrypted PDF: %s", path.name)
            doc.close()
            return result

        result.page_count = doc.page_count
        if doc.page_count == 0:
            result.status = "damaged"
            result.is_damaged = True
            result.error_code = "DAMAGED_PDF"
            result.error_message = "PDF has zero pages"
            doc.close()
            return result

        result.status = "ok"
        result.metadata = {
            "page_count": doc.page_count,
            "format_version": getattr(doc, "version", ""),
            "is_pdf_a": getattr(doc, "is_pdf_a", False),
        }
    except Exception as e:
        logger.warning("[PdfProbe] PDF metadata error: %s — %s", path.name, e)
        result.status = "damaged"
        result.is_damaged = True
        result.error_code = "DAMAGED_PDF"
        result.error_message = str(e)
    finally:
        doc.close()

    return result
