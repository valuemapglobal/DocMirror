# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Structured data deserializers for JSON, CSV, XML, and plain text.

Pluggable readers that convert machine-readable interchange files into
``TextBlock``, ``TableBlock``, and ``KeyValuePair`` structures consumed by
``StructuredAdapter``. Keeps format-specific parsing out of the adapter class.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from docmirror.models.entities.parse_result import (
    CellValue,
    DataType,
    KeyValuePair,
    TableBlock,
    TableRow,
    TextBlock,
    TextLevel,
)

_CURRENCY_RE = re.compile(r"^[¥$€£₹]?\s*-?\d{1,3}(,\d{3})*(\.\d+)?$")


def _classify_csv_cell(value: str) -> CellValue:
    text = value.strip()
    if not text:
        return CellValue(text="", data_type=DataType.EMPTY)
    try:
        numeric = float(text)
        return CellValue(text=text, cleaned=text, numeric=numeric, data_type=DataType.NUMBER)
    except ValueError:
        pass
    if _CURRENCY_RE.match(text):
        cleaned = re.sub(r"[¥$€£₹,\s]", "", text)
        try:
            numeric = float(cleaned)
            return CellValue(text=text, cleaned=cleaned, numeric=numeric, data_type=DataType.CURRENCY)
        except ValueError:
            pass
    return CellValue(text=text, data_type=DataType.TEXT)


def deserialize_json(path: Path) -> tuple[list[TextBlock], list[TableBlock], list[KeyValuePair]]:
    texts: list[TextBlock] = []
    tables: list[TableBlock] = []
    key_values: list[KeyValuePair] = []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        for k, v in data.items():
            key_values.append(KeyValuePair(key=str(k), value=str(v)))
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        headers = list(data[0].keys())
        rows = []
        for record in data:
            cells = [CellValue(text=str(record.get(h, "")), data_type=DataType.TEXT) for h in headers]
            rows.append(TableRow(cells=cells))
        tables.append(TableBlock(table_id="json_records", headers=headers, rows=rows, page=0))

    return texts, tables, key_values


def deserialize_csv(path: Path) -> tuple[list[TextBlock], list[TableBlock], list[KeyValuePair]]:
    texts: list[TextBlock] = []
    tables: list[TableBlock] = []
    key_values: list[KeyValuePair] = []

    with open(path, encoding="utf-8") as f:
        csv_rows = list(csv.reader(f))

    if csv_rows:
        headers = csv_rows[0]
        data_rows = []
        for row_data in csv_rows[1:]:
            cells = [_classify_csv_cell(v) for v in row_data]
            if any(c.text for c in cells):
                data_rows.append(TableRow(cells=cells))
        tables.append(TableBlock(table_id="csv_data", headers=headers, rows=data_rows, page=0))

    return texts, tables, key_values


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def deserialize_xml(path: Path) -> tuple[list[TextBlock], list[TableBlock], list[KeyValuePair]]:
    texts: list[TextBlock] = []
    tables: list[TableBlock] = []
    key_values: list[KeyValuePair] = []

    root = ET.parse(path).getroot()
    for attr, val in (root.attrib or {}).items():
        key_values.append(KeyValuePair(key=attr, value=str(val)))

    rows: list[list[CellValue]] = []
    headers: list[str] = []

    for child in root:
        tag = _local_tag(child.tag)
        text = (child.text or "").strip()
        tail_parts = [((t.text or "").strip()) for t in child.iter() if t is not child and (t.text or "").strip()]
        full = " ".join(p for p in [text, *tail_parts] if p)
        if full:
            key_values.append(KeyValuePair(key=tag, value=full))
        row_cells = [CellValue(text=tag, data_type=DataType.TEXT)]
        if child.attrib:
            for ak, av in child.attrib.items():
                row_cells.append(CellValue(text=str(av), data_type=DataType.TEXT))
        elif full:
            row_cells.append(CellValue(text=full, data_type=DataType.TEXT))
        if len(row_cells) > 1:
            if not headers:
                headers = ["element", "value"]
            rows.append(row_cells[:2] if len(row_cells) >= 2 else row_cells)

    if rows:
        tables.append(TableBlock(table_id="xml_elements", headers=headers or ["element", "value"], rows=[TableRow(cells=r) for r in rows], page=0))
    elif not key_values:
        texts.append(TextBlock(content=ET.tostring(root, encoding="unicode")[:8000], level=TextLevel.BODY))

    return texts, tables, key_values


def deserialize_txt(path: Path) -> tuple[list[TextBlock], list[TableBlock], list[KeyValuePair]]:
    texts: list[TextBlock] = []
    tables: list[TableBlock] = []
    key_values: list[KeyValuePair] = []

    content = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln.rstrip("\n\r") for ln in content.splitlines()]
    non_empty = [ln for ln in lines if ln.strip()]

    if not non_empty:
        return texts, tables, key_values

    # Tab-separated or multi-space columns → table
    delim = "\t" if any("\t" in ln for ln in non_empty[:20]) else None
    if delim:
        parsed = [ln.split("\t") for ln in non_empty]
        width = max(len(r) for r in parsed)
        if width >= 2:
            headers = parsed[0]
            data_rows = []
            for row in parsed[1:]:
                cells = [_classify_csv_cell(c) for c in row]
                while len(cells) < len(headers):
                    cells.append(CellValue(text="", data_type=DataType.EMPTY))
                data_rows.append(TableRow(cells=cells[: len(headers)]))
            tables.append(TableBlock(table_id="txt_tsv", headers=headers, rows=data_rows, page=0))
            return texts, tables, key_values

    for ln in non_empty:
        texts.append(TextBlock(content=ln, level=TextLevel.BODY))

    return texts, tables, key_values


DESERIALIZERS = {
    ".json": deserialize_json,
    ".csv": deserialize_csv,
    ".xml": deserialize_xml,
    ".txt": deserialize_txt,
}
