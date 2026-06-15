# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Post-extract hook: attach credit report sections for DocGraph.

When community/enterprise credit extract did not populate ``ParseResult.sections``,
attempts lightweight section splitting from full document text using enterprise or
legacy section splitter implementations.

Pipeline role: DocGraph and graph export paths expect section boundaries on Mirror;
runs only for ``document_type == "credit_report"``.

Key exports: ``CreditReportSectionsHook``.

Dependencies: optional ``docmirror_enterprise.plugins.credit_report.extractors.section_splitter``.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins.post_extract.base import PostExtractHook

logger = logging.getLogger(__name__)


class CreditReportSectionsHook(PostExtractHook):
    hook_id = "credit_report_sections"

    def apply(
        self,
        result: ParseResult,
        *,
        extracted: dict[str, Any],
        edition: str,
        document_type: str,
        plugin: Any | None = None,
    ) -> None:
        if document_type != "credit_report" or result.sections:
            return
        text = getattr(result, "extractor_full_text", "") or getattr(result, "full_text", "") or ""
        if not text.strip():
            return

        splitter_cls = None
        for mod_path, cls_name in (
            ("docmirror_enterprise.plugins.credit_report.extractors.section_splitter", "SectionSplitter"),
            ("docmirror.plugins.credit_report.extractors.section_splitter", "SectionSplitter"),
        ):
            try:
                mod = __import__(mod_path, fromlist=[cls_name])
                splitter_cls = getattr(mod, cls_name)
                break
            except (ImportError, AttributeError):
                continue
        if splitter_cls is None:
            return

        try:
            splitter = splitter_cls()
            report_type = (result.entities.domain_specific or {}).get("report_subtype")
            if not report_type and hasattr(splitter, "detect_report_type"):
                report_type = splitter.detect_report_type(text)
            sections_dict = splitter.split(text, report_type)
            result.sections = [
                {
                    "id": f"sec_{i}",
                    "title": title,
                    "name": title,
                    "page_start": 1,
                }
                for i, (title, content) in enumerate(sections_dict.items())
                if title.strip() or (content or "").strip()
            ]
            if result.sections:
                logger.debug(
                    "[PostExtract] Attached %d credit report sections",
                    len(result.sections),
                )
        except Exception as exc:
            logger.debug("[PostExtract] credit sections skip: %s", exc)
