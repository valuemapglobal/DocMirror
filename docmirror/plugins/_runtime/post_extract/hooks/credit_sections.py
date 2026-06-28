# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Post-extract hook: attach credit report sections to edition JSON.

When community/enterprise credit extract did not populate ``data.sections``,
attempts lightweight section splitting from full document text using enterprise or
legacy section splitter implementations.

Pipeline role: DocGraph and graph export paths read sections from edition output;
Core ``ParseResult`` / ``001_mirror.json`` are not mutated (Architecture A).

Key exports: ``CreditReportSectionsHook``.

Dependencies: optional ``docmirror_enterprise.plugins.credit_report.extractors.section_splitter``.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins._runtime.post_extract.base import PostExtractHook

logger = logging.getLogger(__name__)


def _sections_from_splitter(result: ParseResult, text: str) -> list[dict[str, Any]]:
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
        return []

    splitter = splitter_cls()
    report_type = (result.entities.domain_specific or {}).get("report_subtype")
    if not report_type and hasattr(splitter, "detect_report_type"):
        report_type = splitter.detect_report_type(text)
    sections_dict = splitter.split(text, report_type)
    return [
        {
            "id": f"sec_{i}",
            "title": title,
            "name": title,
            "page_start": 1,
        }
        for i, (title, content) in enumerate(sections_dict.items())
        if title.strip() or (content or "").strip()
    ]


class CreditReportSectionsHook(PostExtractHook):
    hook_id = "credit_report_sections"

    def apply(
        self,
        result: ParseResult,
        *,
        extracted: dict[str, Any],
        _edition: str,
        document_type: str,
        _plugin: Any | None = None,
    ) -> None:
        if document_type != "credit_report":
            return

        data = extracted.setdefault("data", {})
        if data.get("sections"):
            return

        if result.sections:
            data["sections"] = list(result.sections)
            return

        text = getattr(result, "extractor_full_text", "") or getattr(result, "full_text", "") or ""
        if not text.strip():
            return

        try:
            sections = _sections_from_splitter(result, text)
            if sections:
                data["sections"] = sections
                logger.debug(
                    "[PostExtract] Attached %d credit report sections to edition",
                    len(sections),
                )
        except Exception as exc:
            logger.debug("[PostExtract] credit sections skip: %s", exc)
