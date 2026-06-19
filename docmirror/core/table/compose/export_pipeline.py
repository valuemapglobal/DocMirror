# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Logical table export pipeline — shared SSOT for extractor and bridge fallback.

Uses merger planning (quarantine skip), LTQG, and export partition so
``document_profile.compose_logical_tables`` and ``parse_result_bridge`` fallback
produce identical logical export contracts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from docmirror.core.physical.models import Block, PageLayout
from docmirror.core.profile.registry import get_profile, match_layout_profile
from docmirror.core.table.compose.composer import TableComposer, serialize_logical_tables_for_metadata
from docmirror.core.table.compose.ledger_quality import LTQGSummary, finalize_logical_tables_for_export
from docmirror.core.table.merge.merger import collect_quarantined_tables
from docmirror.models.entities.parse_result import LogicalTable, PageContent

logger = logging.getLogger(__name__)


@dataclass
class LogicalExportResult:
    export_logical: list[LogicalTable]
    skipped_logical: list[LogicalTable]
    ltqg_summary: LTQGSummary | None
    quarantined_physical: list[dict[str, Any]]
    export_payload: list[dict[str, Any]] | None
    skipped_payload: list[dict[str, Any]] | None


def resolve_compose_profile(
    *,
    profile: Any | None = None,
    layout_profile_id: str | None = None,
    full_text: str = "",
    num_pages: int = 0,
    scene_hint: str | None = None,
    content_type: str | None = None,
) -> Any:
    """Resolve layout profile for logical compose (extractor host or bridge metadata)."""
    if profile is not None:
        return profile
    if layout_profile_id:
        try:
            return get_profile(str(layout_profile_id))
        except Exception:
            pass
    if full_text or num_pages:
        return match_layout_profile(
            text_sample=full_text,
            num_pages=num_pages,
            scene_hint=scene_hint,
            content_type=content_type,
        )
    return None


def page_content_to_layouts(pages: list[PageContent]) -> list[PageLayout]:
    """Rebuild PageLayout blocks from ParseResult pages (bridge fallback when layouts lost)."""
    layouts: list[PageLayout] = []
    for page in pages:
        blocks: list[Block] = []
        for ti, table in enumerate(page.tables):
            raw: list[list[str]] = []
            if table.headers:
                raw.append([str(h) for h in table.headers])
            for row in table.rows:
                raw.append([str(c.text or "") for c in row.cells])
            blocks.append(
                Block(
                    block_id=f"pt_{page.page_number}_{ti}",
                    block_type="table",
                    bbox=(0.0, 0.0, 0.0, 0.0),
                    reading_order=ti,
                    page=page.page_number,
                    raw_content=raw,
                )
            )
        layouts.append(
            PageLayout(
                page_number=page.page_number,
                blocks=tuple(blocks),
                is_scanned=getattr(page, "is_scanned", False),
            )
        )
    return layouts


def compose_logical_export_from_layouts(
    pages: list[PageLayout],
    *,
    profile: Any | None = None,
    layout_profile_id: str | None = None,
    full_text: str = "",
    scene_hint: str | None = None,
    content_type: str | None = None,
) -> LogicalExportResult:
    """Compose export logical tables with merger quarantine + LTQG (Mirror SSOT)."""
    profile = resolve_compose_profile(
        profile=profile,
        layout_profile_id=layout_profile_id,
        full_text=full_text,
        num_pages=len(pages),
        scene_hint=scene_hint,
        content_type=content_type,
    )

    if profile and profile.mirror_skip_cross_page_merge:
        logical = TableComposer.clone_physical_from_layouts(pages)
    else:
        logical = TableComposer.from_page_layouts(pages, profile=profile)

    quarantined = collect_quarantined_tables(pages, profile=profile)
    if quarantined:
        logger.info(
            "[DocMirror] Quarantined %d standalone physical table(s) (col/fragment mismatch)",
            len(quarantined),
        )

    export_logical: list[LogicalTable] = []
    skipped_logical: list[LogicalTable] = []
    ltqg_summary: LTQGSummary | None = None
    export_payload: list[dict[str, Any]] | None = None
    skipped_payload: list[dict[str, Any]] | None = None

    if logical:
        q_pages = {int(q["page"]) for q in quarantined if q.get("page") is not None}
        export_logical, skipped_logical, ltqg_summary = finalize_logical_tables_for_export(
            logical,
            profile=profile,
            quarantined_pages=q_pages,
            quarantined_tables=quarantined,
        )
        if ltqg_summary.enabled:
            logger.info(
                "[DocMirror] LTQG: passed=%d skipped=%d expected_data_rows=%d export=%d",
                ltqg_summary.passed_tables,
                ltqg_summary.skipped_tables,
                ltqg_summary.expected_data_rows,
                len(export_logical),
            )
        if skipped_logical:
            skipped_payload = serialize_logical_tables_for_metadata(skipped_logical)
            logger.info(
                "[DocMirror] LTQG quarantined %d logical table(s) from export",
                len(skipped_logical),
            )
        if export_logical:
            export_payload = serialize_logical_tables_for_metadata(export_logical)
            logger.info(
                "[DocMirror] Logical table composition: %d export logical tables from %d pages",
                len(export_logical),
                len(pages),
            )

    return LogicalExportResult(
        export_logical=export_logical,
        skipped_logical=skipped_logical,
        ltqg_summary=ltqg_summary,
        quarantined_physical=quarantined,
        export_payload=export_payload,
        skipped_payload=skipped_payload,
    )


__all__ = [
    "LogicalExportResult",
    "compose_logical_export_from_layouts",
    "page_content_to_layouts",
    "resolve_compose_profile",
]
