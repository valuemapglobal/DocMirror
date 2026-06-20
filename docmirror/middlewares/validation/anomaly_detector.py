# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Structural anomaly detection middleware — mirror quality signals only.

Scans ``ParseResult`` tables and text blocks for layout irregularities (ragged
columns, repeated headers, orphan rows) and attaches quality hints without
mutating extracted content. Signals feed fidelity scoring and diagnostics.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.middlewares.base import BaseMiddleware
from docmirror.models.entities.parse_result import ParseResult, TableBlock

logger = logging.getLogger(__name__)


class AnomalyDetectorMiddleware(BaseMiddleware):
    """
    Validation middleware for structural extraction anomalies.

    Reports layout collapse signals on Mirror data — not Finance risk conclusions.
    """

    DEPENDS_ON = ["Validator"]
    PROVIDES = ["structural_anomaly_report"]

    CRITICAL_ACCOUNT_KEYS = frozenset({"开立日期", "借款金额", "管理机构"})
    TABLE_COLLAPSE_FAILURE_RATE = 0.3
    TABLE_ROW_EMPTY_RATIO = 0.5
    MIN_TABLE_DATA_ROWS = 3

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.dlq_registry: list[dict[str, Any]] = []

    def process(self, result: ParseResult) -> ParseResult:
        report = self._detect_table_structural_anomalies(result)
        if report is None:
            report = self._detect_credit_account_collapse(result)
        if report is not None:
            if result.entities is None:
                from docmirror.models.entities.parse_result import DocumentEntities

                result.entities = DocumentEntities()
            if result.entities.domain_specific is None:
                result.entities.domain_specific = {}
            result.add_error("REQUIRES_VLM_FALLBACK")
            result.entities.domain_specific["structural_anomaly_report"] = report
            self._route_to_dlq(result, report.get("reason", "structural anomaly"))
        return result

    def _detect_table_structural_anomalies(self, result: ParseResult) -> dict[str, Any] | None:
        """Generic table collapse: sparse rows or column/header misalignment."""
        if not result.pages:
            return None

        collapsed_tables = 0
        checked_tables = 0
        for table in result.all_tables():
            issue = self._table_collapse_issue(table)
            if issue is None:
                continue
            checked_tables += 1
            if issue:
                collapsed_tables += 1

        if checked_tables == 0:
            return None

        failure_rate = collapsed_tables / checked_tables
        if failure_rate <= self.TABLE_COLLAPSE_FAILURE_RATE:
            return None

        logger.error(
            "[AnomalyDetector] %.1f%% tables structurally collapsed",
            failure_rate * 100,
        )
        return {
            "type": "table_structure_collapse",
            "failure_rate": round(failure_rate, 3),
            "tables_checked": checked_tables,
            "tables_collapsed": collapsed_tables,
            "reason": f"Table structure collapse (failure rate {failure_rate:.2f})",
        }

    def _table_collapse_issue(self, table: TableBlock) -> bool | None:
        data_rows = table.data_rows
        if len(data_rows) < self.MIN_TABLE_DATA_ROWS:
            return None

        header_count = len(table.headers)
        sparse_rows = 0
        misaligned_rows = 0

        for row in data_rows:
            cells = row.cells
            if header_count and len(cells) < max(1, header_count // 2):
                misaligned_rows += 1
                continue

            non_empty = sum(1 for cell in cells if (cell.cleaned or cell.text or "").strip())
            denom = header_count or len(cells) or 1
            if non_empty / denom < (1.0 - self.TABLE_ROW_EMPTY_RATIO):
                sparse_rows += 1

        row_count = len(data_rows)
        sparse_rate = sparse_rows / row_count
        misaligned_rate = misaligned_rows / row_count
        if sparse_rate > self.TABLE_COLLAPSE_FAILURE_RATE:
            return True
        if misaligned_rate > self.TABLE_COLLAPSE_FAILURE_RATE:
            return True
        return False

    def _detect_credit_account_collapse(self, result: ParseResult) -> dict[str, Any] | None:
        """Domain-specific fallback for credit report account grids."""
        if not result.entities or not result.entities.domain_specific:
            return None

        credit_cards = result.entities.domain_specific.get("credit_accounts", [])
        if not credit_cards:
            return None

        anomaly_count = 0
        for card in credit_cards:
            missing = [k for k in self.CRITICAL_ACCOUNT_KEYS if not card.get(k)]
            if len(missing) >= 2:
                anomaly_count += 1

        failure_rate = anomaly_count / max(len(credit_cards), 1)
        if failure_rate <= self.TABLE_COLLAPSE_FAILURE_RATE:
            return None

        logger.error(
            "[AnomalyDetector] %.1f%% credit accounts structurally collapsed",
            failure_rate * 100,
        )
        return {
            "type": "credit_account_collapse",
            "failure_rate": round(failure_rate, 3),
            "reason": f"Credit extraction collapse (failure rate {failure_rate:.2f})",
        }

    def _route_to_dlq(self, parse_result: ParseResult, reason: str) -> None:
        self.dlq_registry.append(
            {
                "page_count": len(parse_result.pages),
                "reason": reason,
            }
        )
