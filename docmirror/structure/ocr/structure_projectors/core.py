# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Core (domain-agnostic) structure projectors — Design 20 Phase 2."""

from __future__ import annotations

from typing import Any

from docmirror.structure.ocr.structure_project import ProjectionResult, register_structure_projector


def _cells_as_label_value_map(structure: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for cell in structure.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        label = str(cell.get("label_text") or cell.get("label") or "").strip()
        value = str(cell.get("text") or cell.get("value") or "").strip()
        if label and value:
            out[label] = value
    return out


def _micro_grid_as_rows(structure: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in structure.get("cells") or []:
        if not isinstance(row, list):
            continue
        row_dict: dict[str, str] = {}
        for col_idx, cell in enumerate(row):
            if not isinstance(cell, dict):
                continue
            text = str(cell.get("text") or "").strip()
            if text:
                role = str(cell.get("role") or f"col_{col_idx}")
                row_dict[role] = text
        if row_dict:
            rows.append(row_dict)
    return rows


class CoreFieldGridProjector:
    schema_hints = frozenset({"core.field_grid.kv_block"})

    def project(self, structure: dict[str, Any], *, page: int, schema_hint: str) -> ProjectionResult:
        fields = _cells_as_label_value_map(structure)
        if not fields:
            return ProjectionResult(
                record=None,
                rejected=True,
                reject_reason="empty_field_grid",
                schema_hint=schema_hint,
            )
        record = {
            "page": page,
            "fields": fields,
            "schema_hint": schema_hint,
            "audit": {
                "projection_completeness": "partial" if len(fields) < 3 else "complete",
                "field_count": len(fields),
                "missing_fields": [],
            },
        }
        return ProjectionResult(
            record=record,
            field_count=len(fields),
            completeness=str(record["audit"]["projection_completeness"]),
            confidence=float(structure.get("confidence") or 0.5),
            schema_hint=schema_hint,
        )


class CoreMicroGridProjector:
    schema_hints = frozenset({"core.micro_grid.matrix"})

    def project(self, structure: dict[str, Any], *, page: int, schema_hint: str) -> ProjectionResult:
        rows = _micro_grid_as_rows(structure)
        if not rows:
            return ProjectionResult(
                record=None,
                rejected=True,
                reject_reason="empty_micro_grid",
                schema_hint=schema_hint,
            )
        record = {
            "page": page,
            "rows": rows,
            "schema_hint": schema_hint,
            "audit": {
                "projection_completeness": "partial",
                "field_count": len(rows),
            },
        }
        return ProjectionResult(
            record=record,
            field_count=len(rows),
            completeness="partial",
            confidence=float(structure.get("confidence") or 0.5),
            schema_hint=schema_hint,
        )


class CorePhysicalTableProjector:
    schema_hints = frozenset({"core.physical_table.ledger"})

    def project(self, structure: dict[str, Any], *, page: int, schema_hint: str) -> ProjectionResult:
        headers = list(structure.get("headers") or [])
        row_count = int(structure.get("row_count") or 0)
        record = {
            "page": page,
            "table_id": structure.get("table_id"),
            "headers": headers,
            "row_count": row_count,
            "schema_hint": schema_hint,
            "audit": {"projection_completeness": "metadata_only"},
        }
        return ProjectionResult(
            record=record,
            field_count=len(headers),
            completeness="metadata_only",
            confidence=1.0,
            schema_hint=schema_hint,
        )


def register_core_structure_projectors() -> None:
    register_structure_projector(CoreFieldGridProjector())
    register_structure_projector(CoreMicroGridProjector())
    register_structure_projector(CorePhysicalTableProjector())


# Eager registration on import
register_core_structure_projectors()
