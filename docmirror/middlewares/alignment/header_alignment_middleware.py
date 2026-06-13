# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Header alignment middleware — wraps verify_header_data_alignment for MEP."""

from __future__ import annotations

import logging

from docmirror.middlewares.alignment.header_alignment import verify_header_data_alignment
from docmirror.middlewares.base import BaseMiddleware
from docmirror.models.entities.parse_result import ParseResult, RowType

logger = logging.getLogger(__name__)

_DEFAULT_TYPE_EXPECTATIONS = {
    "日期": "date",
    "交易日期": "date",
    "时间": "date",
    "金额": "amount",
    "交易金额": "amount",
    "余额": "amount",
    "序号": "seq",
    "编号": "seq",
}


class HeaderAlignmentMiddleware(BaseMiddleware):
    """Detect and repair systematic header/data column offsets on table blocks."""

    DEPENDS_ON = ["HeaderInferrerMiddleware"]
    PROVIDES = ["header_alignment"]

    def process(self, result: ParseResult) -> ParseResult:
        expectations = dict(_DEFAULT_TYPE_EXPECTATIONS)
        expectations.update(self.config.get("header_type_expectations") or {})

        for p_idx, page in enumerate(result.pages):
            for t_idx, table in enumerate(page.tables):
                headers = list(table.headers or [])
                if not headers and table.rows:
                    for row in table.rows:
                        if row.row_type == RowType.HEADER:
                            headers = [c.cleaned or c.text for c in row.cells]
                            break
                if not headers:
                    continue

                data_rows: list[list[str]] = []
                for row in table.rows:
                    if row.row_type == RowType.DATA:
                        data_rows.append([c.cleaned or c.text for c in row.cells])

                if len(data_rows) < 5:
                    continue

                new_headers = verify_header_data_alignment(
                    headers,
                    data_rows,
                    expectations,
                    mutation_recorder=result,
                    middleware_name=self.name,
                )
                if new_headers != headers:
                    table.headers = new_headers
                    for row in table.rows:
                        if row.row_type == RowType.HEADER:
                            for ci, cell in enumerate(row.cells):
                                if ci < len(new_headers):
                                    cell.text = new_headers[ci]
                                    cell.cleaned = new_headers[ci]
                            break
                    result.record_mutation(
                        middleware_name=self.name,
                        target_block_id=table.table_id or f"table_{t_idx}",
                        field_changed=f"pages[{p_idx}].tables[{t_idx}].headers",
                        old_value=str(headers[:6]),
                        new_value=str(new_headers[:6]),
                        reason="systematic header/data alignment fix",
                    )

        return result
