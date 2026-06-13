# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Tabular exporters — CSV and optional Parquet (EFPA L8 / Phase 4)."""

from __future__ import annotations

import csv
import io
from typing import Any

from docmirror.models.entities.parse_result import ParseResult, TableBlock, TableRow


def _table_rows(table: TableBlock) -> list[list[str]]:
    rows: list[list[str]] = []
    if table.headers:
        rows.append([str(h or "") for h in table.headers])
    for row in table.rows or []:
        rows.append([str(c.cleaned or c.text or "") for c in row.cells])
    if not rows and hasattr(table, "raw_content") and table.raw_content:
        for row in table.raw_content:
            rows.append([str(c or "") for c in row])
    return rows


def export_tables_to_csv(result: ParseResult) -> str:
    """Serialize all tables to CSV with section markers."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    tables = result.all_tables()
    if not tables:
        writer.writerow(["message", "no_tables"])
        return buf.getvalue()

    for idx, table in enumerate(tables):
        writer.writerow([f"# table_{idx + 1}"])
        for row in _table_rows(table):
            writer.writerow(row)
        writer.writerow([])
    return buf.getvalue()


def export_tables_to_parquet(result: ParseResult) -> bytes:
    """Serialize tables to Parquet (requires pyarrow)."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Parquet export requires pyarrow: pip install pyarrow") from exc

    tables = result.all_tables()
    if not tables:
        table = pa.table({"message": ["no_tables"]})
        sink = io.BytesIO()
        pq.write_table(table, sink)
        return sink.getvalue()

    # Flatten first table for single-sheet Parquet; multi-table via table_index column
    records: list[dict[str, Any]] = []
    for t_idx, table in enumerate(tables):
        rows = _table_rows(table)
        if not rows:
            continue
        headers = rows[0]
        for row in rows[1:]:
            padded = row + [""] * max(0, len(headers) - len(row))
            rec = {"table_index": t_idx + 1}
            for col_idx, header in enumerate(headers):
                key = str(header or f"col_{col_idx + 1}").strip() or f"col_{col_idx + 1}"
                rec[key] = padded[col_idx] if col_idx < len(padded) else ""
            records.append(rec)

    if not records:
        table = pa.table({"message": ["empty_tables"]})
    else:
        table = pa.Table.from_pylist(records)
    sink = io.BytesIO()
    pq.write_table(table, sink)
    return sink.getvalue()


def export_parse_result(result: ParseResult, fmt: str) -> tuple[bytes | str, str, str]:
    """Export ParseResult in requested tabular format.

    Returns:
        ``(payload, media_type, filename_suffix)``
    """
    normalized = fmt.lower().strip()
    if normalized == "csv":
        return export_tables_to_csv(result), "text/csv", ".csv"
    if normalized == "parquet":
        return export_tables_to_parquet(result), "application/octet-stream", ".parquet"
    raise ValueError(f"unsupported tabular format: {fmt}")
