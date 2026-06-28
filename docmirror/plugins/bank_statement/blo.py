# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Bank Ledger Orchestrator (BLO) — Plugin multi-table export SSOT (ADR-BS-05).

Iterates passed ``LogicalTable`` instances, runs style parser chain per table,
merges and dedupes canonical records. Single-table / pipe LTRO paths preserve
legacy behaviour via one synthetic block from ``ctx.tables``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

from docmirror.structure.tables.access import get_logical_tables
from docmirror.models.entities.parse_result import LogicalTable
from docmirror.plugins.bank_statement.canonical import dedupe_transaction_rows
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector, StyleDetectionResult

logger = logging.getLogger(__name__)

_INHERIT_CONFIDENCE = 0.55


@dataclass
class BLOMeta:
    tables_parsed: int = 0
    tables_skipped: int = 0
    logical_table_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "tables_parsed": self.tables_parsed,
            "tables_skipped": self.tables_skipped,
            "logical_table_count": self.logical_table_count,
        }


def logical_table_to_matrices(lt: LogicalTable) -> list[list[list[str]]]:
    """Convert one logical table to plugin matrix form."""
    matrix: list[list[str]] = []
    headers = list(lt.headers or [])
    if headers:
        matrix.append([str(h or "") for h in headers])
    for row in lt.rows or []:
        cells = [str(getattr(cell, "cleaned", None) or getattr(cell, "text", "") or "") for cell in (row.cells or [])]
        if any(c.strip() for c in cells):
            matrix.append(cells)
    return [matrix] if matrix else []


def _iter_parse_blocks(ctx: StyleContext) -> list[tuple[LogicalTable | None, list[list[list[str]]]]]:
    logical_tables = get_logical_tables(ctx.parse_result) if ctx.parse_result else []
    if logical_tables:
        return [(lt, logical_table_to_matrices(lt)) for lt in logical_tables]
    if ctx.tables:
        return [(None, ctx.tables)]
    return []


class BankLedgerOrchestrator:
    """Multi logical-table bank export orchestrator."""

    def __init__(self, registry: Any) -> None:
        self._registry = registry
        self._detector = BankStyleDetector()

    def run(
        self,
        detection: StyleDetectionResult,
        ctx: StyleContext,
        plugin: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, dict], BLOMeta]:
        blocks = _iter_parse_blocks(ctx)
        meta = BLOMeta(logical_table_count=len(blocks))

        if len(blocks) <= 1:
            sub_ctx = ctx
            sub_detection = detection
            if blocks:
                lt, sub_tables = blocks[0]
                if lt is not None and not getattr(lt, "quality_passed", True):
                    meta.tables_skipped = 1
                    if ctx.tables:
                        sub_ctx = ctx
                        sub_detection = detection
                    else:
                        return [], plugin._extract_identity(ctx.parse_result), meta
                elif sub_tables:
                    sub_ctx = replace(ctx, tables=sub_tables)
                    sub_detection = self._resolve_detection(detection, sub_ctx)
            records, identity = self._registry.run_parser_chain(sub_detection, sub_ctx, plugin)
            if blocks and blocks[0][0] is not None and getattr(blocks[0][0], "quality_passed", True):
                meta.tables_parsed = 1
            elif records:
                meta.tables_parsed = 1
            records = dedupe_transaction_rows(records)
            return records, identity, meta

        records: list[dict[str, Any]] = []
        identity_fields = plugin._extract_identity(ctx.parse_result)

        for lt, sub_tables in blocks:
            if lt is not None and not getattr(lt, "quality_passed", True):
                meta.tables_skipped += 1
                logger.info(
                    "[BLO] skip logical_table=%s reason=%s",
                    getattr(lt, "logical_id", None) or getattr(lt, "table_id", ""),
                    getattr(lt, "quality_skip_reason", "ltqg_failed"),
                )
                continue
            if not sub_tables:
                meta.tables_skipped += 1
                continue

            sub_ctx = replace(ctx, tables=sub_tables)
            sub_detection = self._resolve_detection(detection, sub_ctx)
            batch, batch_identity = self._registry.run_parser_chain(sub_detection, sub_ctx, plugin)
            if batch_identity:
                identity_fields = batch_identity
            records.extend(batch)
            meta.tables_parsed += 1

        if not records and ctx.tables:
            logger.info("[BLO] no records from logical tables — fallback to ctx.tables")
            batch, batch_identity = self._registry.run_parser_chain(detection, ctx, plugin)
            if batch_identity:
                identity_fields = batch_identity
            records.extend(batch)
            if batch:
                meta.tables_parsed = max(meta.tables_parsed, 1)

        records = dedupe_transaction_rows(records)
        logger.info(
            "[BLO] parsed=%d skipped=%d records=%d",
            meta.tables_parsed,
            meta.tables_skipped,
            len(records),
        )
        return records, identity_fields, meta

    def _resolve_detection(
        self,
        document_detection: StyleDetectionResult,
        sub_ctx: StyleContext,
    ) -> StyleDetectionResult:
        sub_detection = self._detector.detect(sub_ctx)
        if sub_detection.confidence >= _INHERIT_CONFIDENCE:
            return sub_detection
        return document_detection


__all__ = [
    "BLOMeta",
    "BankLedgerOrchestrator",
    "logical_table_to_matrices",
]
