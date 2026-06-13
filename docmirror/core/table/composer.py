# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
TableComposer — Logical table composition (non-destructive)
=============================================================

Produces ``LogicalTable`` views alongside physical per-page tables.
Physical pages are never mutated; composition uses the same merge heuristics
as ``merger.collect_cross_page_merge_groups`` without destructive rebuild.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.models.entities.domain import PageLayout
from docmirror.models.entities.layout_profile import LayoutProfile
from docmirror.models.entities.parse_result import (
    CellValue,
    LogicalTable,
    PageContent,
    RowProvenance,
    RowType,
    TableRow,
)
from docmirror.core.table.merger import collect_cross_page_merge_groups

logger = logging.getLogger(__name__)


def physical_table_id(page_number: int, table_index: int = 0) -> str:
    """Standard physical table ID: ``pt_{page}_{index}``."""
    return f"pt_{page_number}_{table_index}"


def logical_table_id(index: int) -> str:
    """Standard logical table ID: ``lt_{index}``."""
    return f"lt_{index}"


def serialize_logical_tables_for_metadata(logical_tables: list[LogicalTable]) -> list[dict[str, Any]]:
    """Compact JSON-safe payload for BaseResult.metadata transport."""
    payload: list[dict[str, Any]] = []
    for lt in logical_tables:
        payload.append(
            {
                "table_id": lt.table_id,
                "logical_id": lt.logical_id or lt.table_id,
                "headers": lt.headers,
                "rows": [
                    {
                        "cells": [
                            {
                                "text": c.text,
                                "data_type": c.data_type.value if hasattr(c.data_type, "value") else c.data_type,
                            }
                            for c in r.cells
                        ],
                        "source_page": r.source_page,
                        "source_physical_id": r.source_physical_id,
                        "source_row_index": r.source_row_index,
                    }
                    for r in lt.rows
                ],
                "source_physical_ids": lt.source_physical_ids,
                "source_pages": lt.source_pages,
                "page_span": [lt.page_span[0], lt.page_span[1]],
                "row_count": lt.row_count,
                "confidence": lt.confidence,
                "merge_method": lt.merge_method,
                "merge_confidence": lt.merge_confidence,
                "merge_log": lt.merge_log,
                "merge_audit": lt.merge_audit,
            }
        )
    return payload


class TableComposer:
    """Composes logical tables from physical per-page tables."""

    def __init__(self, confidence_threshold: float = 0.7):
        from docmirror.core.table.cross_page_predictor import CrossPageTablePredictor

        self._predictor = CrossPageTablePredictor(confidence_threshold=confidence_threshold)

    def compose(
        self,
        pages: list[PageContent],
        profile: LayoutProfile | None = None,
    ) -> list[LogicalTable]:
        """Compose logical tables from ParseResult physical pages."""
        if profile and profile.mirror_skip_cross_page_merge:
            logger.info(
                "[TableComposer] Composition skipped by profile '%s' — cloning physical",
                profile.profile_id,
            )
            return self.clone_physical_from_page_content(pages)

        if not pages:
            return []

        all_physical: list[tuple[int, int, Any]] = []
        for page in pages:
            for ti, table in enumerate(page.tables):
                all_physical.append((page.page_number, ti, table))

        if not all_physical:
            return []

        logical_tables: list[LogicalTable] = []
        current_group: list[tuple[int, int, Any]] = [all_physical[0]]

        for i in range(1, len(all_physical)):
            pn, ti, table = all_physical[i]
            if self._is_same_logical_table(all_physical[i - 1][2], table):
                current_group.append((pn, ti, table))
            else:
                logical_tables.append(self._compose_group(current_group, len(logical_tables)))
                current_group = [(pn, ti, table)]

        if current_group:
            logical_tables.append(self._compose_group(current_group, len(logical_tables)))

        logger.info(
            "[TableComposer] Composed %d logical tables from %d physical table blocks across %d pages",
            len(logical_tables),
            len(all_physical),
            len(pages),
        )
        return logical_tables

    @classmethod
    def from_page_layouts(
        cls,
        pages: list[PageLayout],
        profile: LayoutProfile | None = None,
    ) -> list[LogicalTable]:
        """Compose logical tables from extractor PageLayout list (pre-destructive-merge)."""
        composer = cls()
        if profile and profile.mirror_skip_cross_page_merge:
            logger.info(
                "[TableComposer] Composition skipped by profile '%s' — cloning physical",
                profile.profile_id,
            )
            return composer.clone_physical_from_layouts(pages)

        groups = collect_cross_page_merge_groups(pages)
        logical: list[LogicalTable] = []

        for gi, group in enumerate(groups):
            lt = composer._logical_from_merge_group(group, gi)
            if lt.rows:
                logical.append(lt)

        if logical:
            logger.info(
                "[TableComposer] from_page_layouts: %d logical tables, %d total rows",
                len(logical),
                sum(lt.row_count for lt in logical),
            )
        return logical

    @classmethod
    def clone_physical_from_layouts(cls, pages: list[PageLayout]) -> list[LogicalTable]:
        """1:1 clone each physical table as an independent logical table (profile skip)."""
        logical: list[LogicalTable] = []
        li = 0
        for page in pages:
            ti = 0
            for block in page.blocks:
                if block.block_type != "table" or not isinstance(block.raw_content, list):
                    continue
                raw = block.raw_content
                if not raw:
                    continue
                pt_id = physical_table_id(page.page_number, ti)
                headers = [str(c) for c in raw[0]]
                data_rows = raw[1:] if len(raw) > 1 else []
                rows_out: list[TableRow] = []
                prov_out: list[RowProvenance] = []
                for ri, row in enumerate(data_rows):
                    cells = [CellValue(text=str(c)) for c in row]
                    rows_out.append(
                        TableRow(
                            cells=cells,
                            row_type=RowType.DATA,
                            source_page=page.page_number,
                            source_physical_id=pt_id,
                            source_row_index=ri,
                        )
                    )
                    prov_out.append(
                        RowProvenance(
                            source_page=page.page_number,
                            source_table_id=pt_id,
                            source_row_index=ri,
                        )
                    )
                lid = logical_table_id(li)
                logical.append(
                    LogicalTable(
                        table_id=lid,
                        logical_id=lid,
                        headers=headers,
                        rows=rows_out,
                        row_count=len(rows_out),
                        source_physical_ids=[pt_id],
                        source_pages=[page.page_number],
                        page_span=(page.page_number, page.page_number),
                        confidence=1.0,
                        merge_method="none",
                        merge_confidence=1.0,
                        provenance=prov_out,
                        merge_log=[{"action": "clone_physical", "page": page.page_number}],
                    )
                )
                li += 1
                ti += 1
        return logical

    @classmethod
    def clone_physical_from_page_content(cls, pages: list[PageContent]) -> list[LogicalTable]:
        """1:1 clone from ParseResult PageContent tables."""
        logical: list[LogicalTable] = []
        li = 0
        for page in pages:
            for ti, table in enumerate(page.tables):
                pt_id = physical_table_id(page.page_number, ti)
                rows_out = []
                prov_out = []
                for ri, row in enumerate(table.rows):
                    rows_out.append(
                        TableRow(
                            cells=list(row.cells),
                            row_type=row.row_type,
                            confidence=row.confidence,
                            source_page=page.page_number,
                            source_physical_id=pt_id,
                            source_row_index=ri,
                        )
                    )
                    prov_out.append(
                        RowProvenance(
                            source_page=page.page_number,
                            source_table_id=pt_id,
                            source_row_index=ri,
                        )
                    )
                lid = logical_table_id(li)
                logical.append(
                    LogicalTable(
                        table_id=lid,
                        logical_id=lid,
                        headers=list(table.headers),
                        rows=rows_out,
                        row_count=len(rows_out),
                        source_physical_ids=[pt_id],
                        source_pages=[page.page_number],
                        page_span=(page.page_number, page.page_number),
                        confidence=table.confidence,
                        merge_method="none",
                        merge_confidence=1.0,
                        provenance=prov_out,
                        merge_log=[{"action": "clone_physical", "page": page.page_number}],
                    )
                )
                li += 1
        return logical

    def _logical_from_merge_group(self, group: dict, group_index: int) -> LogicalTable:
        raw_rows = group.get("rows") or []
        if not raw_rows:
            return LogicalTable()

        headers = [str(c) for c in raw_rows[0]]
        data_rows = raw_rows[1:] if len(raw_rows) > 1 else []
        row_pages = group.get("row_pages") or []
        data_row_pages = row_pages[1 : 1 + len(data_rows)] if len(row_pages) > 1 else row_pages[: len(data_rows)]
        source_pages = list(group.get("pages") or [1])
        source_physical_ids = [physical_table_id(p, 0) for p in source_pages]

        page_row_counters: dict[int, int] = {}
        rows_out: list[TableRow] = []
        prov_out: list[RowProvenance] = []
        for ri, row in enumerate(data_rows):
            src_page = data_row_pages[ri] if ri < len(data_row_pages) else source_pages[-1]
            src_idx = page_row_counters.get(src_page, 0)
            page_row_counters[src_page] = src_idx + 1
            pt_id = physical_table_id(src_page, 0)
            cells = [CellValue(text=str(c)) for c in row]
            rows_out.append(
                TableRow(
                    cells=cells,
                    row_type=RowType.DATA,
                    source_page=src_page,
                    source_physical_id=pt_id,
                    source_row_index=src_idx,
                )
            )
            prov_out.append(
                RowProvenance(
                    source_page=src_page,
                    source_table_id=pt_id,
                    source_row_index=src_idx,
                    is_continuation=src_page > source_pages[0],
                )
            )

        merge_method = "cross_page_continuation" if len(source_pages) > 1 else "none"
        merge_confidence, merge_audit = self._score_group_merge(group, source_pages)

        lid = logical_table_id(group_index)
        return LogicalTable(
            table_id=lid,
            logical_id=lid,
            headers=headers,
            rows=rows_out,
            row_count=len(rows_out),
            source_physical_ids=source_physical_ids,
            source_pages=source_pages,
            page_span=(min(source_pages), max(source_pages)) if source_pages else (1, 1),
            confidence=merge_confidence,
            merge_method=merge_method,
            merge_confidence=merge_confidence,
            provenance=prov_out,
            merge_log=list(group.get("merge_log") or []),
            merge_audit=merge_audit,
        )

    def _score_group_merge(self, group: dict, source_pages: list[int]) -> tuple[float, list[dict]]:
        """Score cross-page merge quality using CrossPageTablePredictor."""
        if len(source_pages) <= 1:
            return 1.0, []

        raw_rows = group.get("rows") or []
        audit: list[dict] = []
        scores: list[float] = []

        # Split rows by contributing page for pairwise validation
        row_pages = group.get("row_pages") or []
        page_to_rows: dict[int, list[list]] = {}
        for i, row in enumerate(raw_rows):
            pn = row_pages[i] if i < len(row_pages) else source_pages[0]
            page_to_rows.setdefault(pn, []).append(row)

        ordered_pages = [p for p in source_pages if p in page_to_rows]
        for i in range(1, len(ordered_pages)):
            prev_p = ordered_pages[i - 1]
            next_p = ordered_pages[i]
            prev_rows = page_to_rows.get(prev_p, [])
            next_rows = page_to_rows.get(next_p, [])
            if not prev_rows or not next_rows:
                continue
            validation = self._predictor.validate_raw_table_merge(
                prev_rows, next_rows, prev_page_no=prev_p, next_page_no=next_p
            )
            scores.append(validation.score)
            audit.append(
                {
                    "from_page": prev_p,
                    "to_page": next_p,
                    "score": validation.score,
                    "is_valid": validation.is_valid,
                    "reasons": validation.reasons,
                    "warnings": validation.warnings,
                }
            )

        if not scores:
            return 1.0, audit
        return sum(scores) / len(scores), audit

    def _is_same_logical_table(self, prev_table: Any, curr_table: Any) -> bool:
        prev_cols = len(prev_table.headers) if prev_table.headers else 8
        curr_cols = len(curr_table.headers) if curr_table.headers else 8
        return abs(prev_cols - curr_cols) <= 1

    def _compose_group(self, group: list[tuple[int, int, Any]], group_index: int) -> LogicalTable:
        if not group:
            return LogicalTable()

        headers = list(group[0][2].headers) if group[0][2].headers else []
        all_rows: list[TableRow] = []
        provenance: list[RowProvenance] = []
        source_pages: list[int] = []
        source_physical_ids: list[str] = []
        merge_log: list[dict] = []
        page_row_counters: dict[int, int] = {}

        for pn, ti, table in group:
            source_pages.append(pn)
            pt_id = physical_table_id(pn, ti)
            source_physical_ids.append(pt_id)
            for ri, row in enumerate(table.rows):
                if pn > group[0][0] and ri == 0 and self._is_header_row(row, headers):
                    merge_log.append({"action": "skip_header", "page": pn, "row_index": ri})
                    continue
                src_idx = page_row_counters.get(pn, 0)
                page_row_counters[pn] = src_idx + 1
                all_rows.append(
                    TableRow(
                        cells=list(row.cells),
                        row_type=row.row_type,
                        confidence=row.confidence,
                        source_page=pn,
                        source_physical_id=pt_id,
                        source_row_index=src_idx,
                    )
                )
                provenance.append(
                    RowProvenance(
                        source_page=pn,
                        source_table_id=pt_id,
                        source_row_index=src_idx,
                        is_continuation=(pn > group[0][0]),
                    )
                )
            merge_log.append({"action": "merge_page", "page": pn, "rows_from_page": len(table.rows)})

        if not headers and all_rows and all_rows[0].cells:
            headers = [c.text for c in all_rows[0].cells]
            all_rows = all_rows[1:]
            provenance = provenance[1:]

        merge_method = "cross_page_continuation" if len(source_pages) > 1 else "none"
        lid = logical_table_id(group_index)
        return LogicalTable(
            table_id=lid,
            logical_id=lid,
            headers=headers,
            rows=all_rows,
            row_count=len(all_rows),
            source_physical_ids=source_physical_ids,
            source_pages=source_pages,
            page_span=(min(source_pages), max(source_pages)),
            confidence=1.0,
            merge_method=merge_method,
            merge_confidence=1.0 if len(source_pages) <= 1 else 0.9,
            provenance=provenance,
            merge_log=merge_log,
        )

    @staticmethod
    def _is_header_row(row: TableRow, headers: list[str]) -> bool:
        if not row.cells or not headers:
            return False
        cell_texts = [c.text.strip() for c in row.cells[: len(headers)]]
        match_count = sum(1 for ct, h in zip(cell_texts, headers) if ct == h)
        return match_count >= len(headers) * 0.5


def build_table_operations(logical_tables: list[LogicalTable]) -> list:
    """Build document-level table_operations audit from logical tables."""
    from docmirror.models.entities.parse_result import TableOperation

    ops: list[TableOperation] = []
    for lt in logical_tables:
        ops.append(
            TableOperation(
                logical_id=lt.logical_id or lt.table_id,
                merge_method=lt.merge_method,
                merge_confidence=lt.merge_confidence,
                source_physical_ids=lt.source_physical_ids,
                source_pages=lt.source_pages,
                row_count=lt.row_count,
                merge_log=lt.merge_log,
                merge_audit=lt.merge_audit,
            )
        )
    return ops
