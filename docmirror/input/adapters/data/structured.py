# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Structured Data Adapter — JSON / CSV / XML / TXT → ParseResult
==============================================================

Machine-readable interchange formats via pluggable deserializers.
"""

from __future__ import annotations

import logging
from pathlib import Path

from docmirror.input.adapters.data.deserializers import DESERIALIZERS
from docmirror.framework.base import BaseParser

logger = logging.getLogger(__name__)


class StructuredAdapter(BaseParser):
    """Structured data format adapter — deserializer registry by extension."""

    async def to_parse_result(self, file_path: Path, **kwargs) -> ParseResult:
        from docmirror.models.entities.parse_result import (
            PageContent,
            ParseResult,
            ParserInfo,
        )
        from docmirror.models.errors import build_failure_result

        path = Path(file_path)
        ext = path.suffix.lower()
        deserializer_key = kwargs.get("deserializer")
        if deserializer_key == "xml":
            ext = ".xml"
        elif deserializer_key == "txt":
            ext = ".txt"

        fn = DESERIALIZERS.get(ext)
        if fn is None:
            return build_failure_result(
                "UNSUPPORTED_FORMAT",
                f"StructuredAdapter does not support extension: {ext}",
                file_path=str(path),
                file_type="structured",
            )

        logger.info("[StructuredAdapter] Deserializing %s via %s", path.name, ext)
        texts, tables, key_values = fn(path)

        page = PageContent(page_number=0, texts=texts, tables=tables, key_values=key_values)
        return ParseResult(
            pages=[page],
            parser_info=ParserInfo(
                parser_name="StructuredAdapter",
                page_count=1,
                overall_confidence=1.0,
            ),
        )
