"""CSV and optional Parquet exporters for table data."""

from __future__ import annotations

import csv
import io
from typing import Any


def _tables(result: Any) -> list[Any]:
    tables: list[Any] = []
    for page in getattr(result, "pages", []) or []:
        tables.extend(getattr(page, "tables", []) or [])
    tables.extend(getattr(result, "logical_tables", []) or [])
    return tables


def export_tables_to_csv(result: Any) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    for index, table in enumerate(_tables(result), start=1):
        out.write(f"# table_{index}\n")
        headers = list(getattr(table, "headers", []) or [])
        if headers:
            writer.writerow(headers)
        for row in getattr(table, "rows", []) or []:
            writer.writerow([getattr(cell, "text", "") for cell in getattr(row, "cells", []) or []])
    return out.getvalue()


def export_parse_result(result: Any, format_name: str = "csv") -> tuple[Any, str, str]:
    if format_name == "csv":
        return export_tables_to_csv(result), "text/csv", ".csv"
    if format_name == "parquet":
        import pyarrow as pa
        import pyarrow.parquet as pq

        rows = []
        for table in _tables(result):
            headers = list(getattr(table, "headers", []) or [])
            for row in getattr(table, "rows", []) or []:
                values = [getattr(cell, "text", "") for cell in getattr(row, "cells", []) or []]
                rows.append({headers[i] if i < len(headers) else f"col_{i}": value for i, value in enumerate(values)})
        sink = pa.BufferOutputStream()
        pq.write_table(pa.Table.from_pylist(rows or [{}]), sink)
        return sink.getvalue().to_pybytes(), "application/octet-stream", ".parquet"
    raise ValueError(f"Unsupported tabular format: {format_name}")
