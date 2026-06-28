# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Region crop OCR repair for field cells."""

from __future__ import annotations

from typing import Any

from docmirror.ocr.field_grid.models import FieldCell
from docmirror.ocr.local_structure.repair import recognize_structure_region_from_image


def maybe_repair_cell(
    cell: FieldCell,
    *,
    page_image: Any,
    page_width: float,
    page_height: float,
    min_confidence: float = 0.75,
    min_assignment_confidence: float = 0.6,
) -> FieldCell:
    if cell.geometry_status == "quarantined":
        return cell
    if cell.confidence >= min_confidence and cell.assignment_confidence >= min_assignment_confidence:
        return cell
    if page_image is None:
        return cell

    rec = recognize_structure_region_from_image(
        page_image,
        cell.bbox,
        page_width=page_width,
        page_height=page_height,
    )
    audit = dict(cell.audit)
    audit["region_crop_ocr"] = rec.to_dict()

    if rec.text and rec.confidence > cell.confidence:
        from docmirror.ocr.field_grid.type_gate import apply_type_gate

        repaired = FieldCell(
            cell_id=cell.cell_id,
            row_index=cell.row_index,
            col_index=cell.col_index,
            label_text=cell.label_text,
            text=rec.text,
            raw_text=cell.raw_text,
            bbox=cell.bbox,
            token_ids=cell.token_ids,
            line_ids=cell.line_ids,
            confidence=rec.confidence,
            assignment_confidence=cell.assignment_confidence,
            assignment_method="repair:crop_ocr_adopt",
            geometry_status=cell.geometry_status,
            inferred_types=cell.inferred_types,
            quarantine_reason=cell.quarantine_reason,
            continuation_cell_ids=cell.continuation_cell_ids,
            audit={**audit, "repair_mode": "repair_adopt", "repaired_from": cell.text},
        )
        return apply_type_gate(repaired)

    audit["repair_mode"] = "repair_audit_only"
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
        inferred_types=cell.inferred_types,
        quarantine_reason=cell.quarantine_reason,
        continuation_cell_ids=cell.continuation_cell_ids,
        audit=audit,
    )


def repair_field_cells(
    cells: list[FieldCell],
    *,
    page_image: Any,
    page_width: float,
    page_height: float,
    max_repairs: int = 24,
) -> list[FieldCell]:
    out: list[FieldCell] = []
    repairs = 0
    for cell in cells:
        if repairs >= max_repairs:
            out.append(cell)
            continue
        repairs += 1
        out.append(
            maybe_repair_cell(
                cell,
                page_image=page_image,
                page_width=page_width,
                page_height=page_height,
            )
        )
    return out
