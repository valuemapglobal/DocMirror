# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
OFD Adapter — .ofd → ParseResult
==================================

Extracts text from China's Open Fixed-layout Document (OFD) format.

OFD is a ZIP container of XML page descriptors.  This adapter walks page
``Content.xml`` files and collects ``TextCode`` elements — sufficient for
e-invoice, fiscal receipt, and e-license keyword / table downstream pipelines.

Full vector rendering requires dedicated OFD renderers; text extraction uses
stdlib only (zipfile + xml).
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docmirror.framework.base import BaseParser

logger = logging.getLogger(__name__)


def _text_from_content_xml(data: bytes) -> list[str]:
    """Collect visible text lines from an OFD page Content.xml payload."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []

    lines: list[str] = []
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag != "TextCode":
            continue
        parts: list[str] = []
        if elem.text:
            parts.append(elem.text.strip())
        if elem.tail:
            parts.append(elem.tail.strip())
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return lines


def _iter_content_xml_names(members: list[str]) -> list[str]:
    """Return Content.xml paths in stable page order."""
    content_paths = [m for m in members if m.endswith("Content.xml")]
    content_paths.sort(key=lambda p: (p.count("/"), p))
    return content_paths


class OFDAdapter(BaseParser):
    """OFD (.ofd) format adapter — ZIP/XML text extraction for fixed-layout docs."""

    async def to_parse_result(self, file_path: Path, **kwargs) -> ParseResult:
        from docmirror.models.entities.parse_result import (
            PageContent,
            ParseResult,
            ParserInfo,
            ProvenanceInfo,
            ResultStatus,
            TextBlock,
            TextLevel,
        )
        from docmirror.models.errors import build_failure_result

        logger.info(f"[OFDAdapter] Starting extraction for: {file_path}")

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                content_names = _iter_content_xml_names(zf.namelist())
                if not content_names:
                    return build_failure_result(
                        "EXTRACTION_FAILED",
                        "No page Content.xml found in OFD container",
                        file_path=str(file_path),
                        file_type="ofd",
                    )

                pages: list[PageContent] = []
                for idx, name in enumerate(content_names):
                    raw = zf.read(name)
                    lines = _text_from_content_xml(raw)
                    if not lines:
                        continue
                    pages.append(
                        PageContent(
                            page_number=idx,
                            texts=[
                                TextBlock(content=line, level=TextLevel.BODY)
                                for line in lines
                            ],
                        )
                    )
        except zipfile.BadZipFile:
            return build_failure_result(
                "EXTRACTION_FAILED",
                "Invalid OFD container (not a ZIP archive)",
                file_path=str(file_path),
                file_type="ofd",
            )
        except OSError as exc:
            return build_failure_result(
                "EXTRACTION_FAILED",
                f"Cannot read OFD file: {exc}",
                file_path=str(file_path),
                file_type="ofd",
            )

        if not pages:
            return build_failure_result(
                "EXTRACTION_FAILED",
                "OFD container contains no extractable text",
                file_path=str(file_path),
                file_type="ofd",
            )

        try:
            stat = file_path.stat()
            provenance = ProvenanceInfo(file_type="ofd", file_size=stat.st_size)
        except OSError:
            provenance = ProvenanceInfo(file_type="ofd")

        return ParseResult(
            status=ResultStatus.SUCCESS,
            pages=pages,
            parser_info=ParserInfo(
                parser_name="OFDAdapter",
                page_count=len(pages),
                overall_confidence=0.85,
            ),
            provenance=provenance,
        )
