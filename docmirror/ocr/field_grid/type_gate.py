# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic field-type inference and quarantine for field cells."""

from __future__ import annotations

import re

from docmirror.ocr.field_grid.models import FieldCell

FIELD_TYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "date": re.compile(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}"),
    "amount": re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"),
    "currency": re.compile(r"人民币|美元|欧元|日元|港币"),
    "page_footer": re.compile(r"第\d+页，共\d+页"),
    "status_date": re.compile(r"截至\d{4}年\d{1,2}月\d{1,2}日"),
    "long_id": re.compile(r"[A-Z]?\d{10,}"),
    "status_word": re.compile(r"结清|结消|逾期|正常|关闭"),
}


def infer_types(text: str) -> tuple[str, ...]:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return ("empty",)
    if FIELD_TYPE_PATTERNS["page_footer"].search(compact):
        return ("page_footer",)
    found: list[str] = []
    for name, pattern in FIELD_TYPE_PATTERNS.items():
        if name == "page_footer":
            continue
        if pattern.search(compact):
            found.append(name)
    if not found:
        found.append("text")
    return tuple(found)


def quarantine_reason_for_types(inferred: tuple[str, ...]) -> str | None:
    if inferred == ("empty",):
        return None
    if inferred == ("page_footer",):
        return "page_footer_leak"
    if len(inferred) == 1 and inferred[0] == "status_date":
        return "status_date_leak"
    return None


def apply_type_gate(cell: FieldCell) -> FieldCell:
    inferred = infer_types(cell.text)
    reason = quarantine_reason_for_types(inferred)
    if reason:
        return FieldCell(
            cell_id=cell.cell_id,
            row_index=cell.row_index,
            col_index=cell.col_index,
            label_text=cell.label_text,
            text=cell.text,
            raw_text=cell.raw_text,
            bbox=cell.bbox,
            token_ids=cell.token_ids,
            line_ids=cell.line_ids,
            confidence=cell.confidence,
            assignment_confidence=cell.assignment_confidence,
            assignment_method=cell.assignment_method,
            geometry_status="quarantined",
            inferred_types=inferred,
            quarantine_reason=reason,
            continuation_cell_ids=cell.continuation_cell_ids,
            audit={**cell.audit, "type_gate": reason},
        )
    return FieldCell(
        cell_id=cell.cell_id,
        row_index=cell.row_index,
        col_index=cell.col_index,
        label_text=cell.label_text,
        text=cell.text,
        raw_text=cell.raw_text,
        bbox=cell.bbox,
        token_ids=cell.token_ids,
        line_ids=cell.line_ids,
        confidence=cell.confidence,
        assignment_confidence=cell.assignment_confidence,
        assignment_method=cell.assignment_method,
        geometry_status=cell.geometry_status,
        inferred_types=inferred,
        quarantine_reason=None,
        continuation_cell_ids=cell.continuation_cell_ids,
        audit=cell.audit,
    )


def types_compatible_with_hint(inferred: tuple[str, ...], allowed: tuple[str, ...]) -> bool:
    if not inferred or inferred == ("empty",):
        return True
    if "page_footer" in inferred or "status_date" in inferred:
        return False
    if "text" in allowed:
        return True
    return any(t in allowed for t in inferred)
