# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pure structure → domain record projection (Design 19 axiom C — P3).

Parse-time materialization owns ``structure``; enrich/projectors read structure only
and may emit partial records with confidence + missing-field audit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

StructureDict = dict[str, Any]
ProjectorFn = Callable[[StructureDict, int], "ProjectionResult | None"]

# Schema Hint Taxonomy (SHT) — Design 20 §2.3
SCHEMA_CORE_FIELD_GRID = "core.field_grid.kv_block"
SCHEMA_CORE_MICRO_GRID = "core.micro_grid.matrix"
SCHEMA_CORE_PHYSICAL_TABLE = "core.physical_table.ledger"
SCHEMA_CORE_KEY_VALUE = "core.key_value.header"
SCHEMA_CREDIT_FIELD_GRID = "credit.field_grid.account"
SCHEMA_CREDIT_MICRO_GRID = "credit.micro_grid.repayment"


@dataclass
class ProjectionResult:
    record: dict[str, Any] | None
    field_count: int = 0
    missing_fields: list[str] = field(default_factory=list)
    completeness: str = "empty"
    confidence: float = 0.0
    schema_hint: str = ""
    rejected: bool = False
    reject_reason: str | None = None

    def records(self) -> list[dict[str, Any]]:
        if self.rejected or self.record is None:
            return []
        return [self.record]


class StructureProjector(Protocol):
    schema_hints: frozenset[str]

    def project(self, structure: StructureDict, *, page: int, schema_hint: str) -> ProjectionResult: ...


_REGISTRY: dict[str, StructureProjector] = {}


def register_structure_projector(projector: StructureProjector) -> StructureProjector:
    for hint in projector.schema_hints:
        _REGISTRY[hint] = projector
    return projector


def register_projector_fn(schema_hint: str, fn: ProjectorFn) -> ProjectorFn:
    class _FnProjector:
        schema_hints = frozenset({schema_hint})

        def project(self, structure: StructureDict, *, page: int, schema_hint: str) -> ProjectionResult:
            result = fn(structure, page)
            if result is None:
                return ProjectionResult(
                    record=None, rejected=True, reject_reason="projector_returned_none", schema_hint=schema_hint
                )
            if isinstance(result, ProjectionResult):
                return result
            return ProjectionResult(record=result, schema_hint=schema_hint)

    register_structure_projector(_FnProjector())
    return fn


def project_structure(
    structure: StructureDict,
    *,
    page: int,
    schema_hint: str,
) -> ProjectionResult:
    projector = _REGISTRY.get(schema_hint)
    if projector is None:
        return ProjectionResult(
            record=None,
            rejected=True,
            reject_reason=f"unknown_schema_hint:{schema_hint}",
            schema_hint=schema_hint,
        )
    return projector.project(structure, page=page, schema_hint=schema_hint)


def infer_schema_hint(structure: StructureDict) -> str | None:
    """Infer a schema hint when document type is unknown."""
    kind = str(structure.get("structure_kind") or "")
    if kind == "field_grid":
        return SCHEMA_CREDIT_FIELD_GRID
    if kind == "label_value_graph":
        return "credit.label_value_graph.account"
    grid_kind = str(structure.get("grid_kind") or structure.get("kind") or "")
    if grid_kind in {"micro_grid", "repayment_grid"}:
        return SCHEMA_CREDIT_MICRO_GRID
    if structure.get("cells") and structure.get("row_bands"):
        grid_hint = str(structure.get("grid_type_hint") or "")
        if grid_hint == "credit_repayment_record":
            return SCHEMA_CREDIT_MICRO_GRID
    return infer_schema_hint_v2(structure)


def infer_schema_hint_v2(
    structure: StructureDict,
    *,
    document_type: str | None = None,
    region_kind: str | None = None,
) -> str | None:
    """Infer schema_hint with domain override priority (Design 20 §2.3)."""
    doc = str(document_type or "").lower()
    kind = str(structure.get("structure_kind") or region_kind or "")
    grid_hint = str(structure.get("grid_type_hint") or "")

    if "credit" in doc or doc == "credit_report":
        if kind == "field_grid" or region_kind == "field_grid":
            return SCHEMA_CREDIT_FIELD_GRID
        if kind == "label_value_graph":
            return "credit.label_value_graph.account"
        if grid_hint == "credit_repayment_record" or structure.get("row_bands"):
            return SCHEMA_CREDIT_MICRO_GRID

    if kind == "field_grid" or region_kind == "field_grid":
        return SCHEMA_CORE_FIELD_GRID
    if kind == "label_value_graph" or region_kind == "label_value_graph":
        return SCHEMA_CORE_FIELD_GRID
    grid_kind = str(structure.get("grid_kind") or structure.get("kind") or "")
    if grid_kind in {"micro_grid", "repayment_grid"}:
        return SCHEMA_CORE_MICRO_GRID
    if structure.get("cells") and structure.get("row_bands"):
        return SCHEMA_CORE_MICRO_GRID
    return None


def assign_schema_hints_to_regions(
    regions: list[Any],
    *,
    document_type: str | None = None,
) -> None:
    for region in regions:
        structure = getattr(region, "structure", None) or {}
        if not isinstance(structure, dict):
            continue
        hint = infer_schema_hint_v2(
            structure,
            document_type=document_type,
            region_kind=getattr(region, "kind", None),
        )
        if hint:
            region.schema_hint = hint


def completeness_level(field_count: int, *, expected: int) -> str:
    if field_count <= 0:
        return "empty"
    if field_count >= max(3, int(expected * 0.6)):
        return "complete"
    return "partial"


def projection_confidence(*, base_confidence: float, field_count: int, expected: int) -> float:
    ratio = field_count / max(expected, 1)
    blended = (float(base_confidence) * 0.35) + (ratio * 0.65)
    return round(max(0.0, min(1.0, blended)), 4)


def finalize_partial_record(
    record: dict[str, Any],
    *,
    field_count: int,
    expected_fields: list[str],
    mapped_fields: list[str],
    base_confidence: float,
    anchor_present: bool,
) -> dict[str, Any] | None:
    """Attach P3 audit metadata and apply partial-OK emit rules."""
    missing = [key for key in expected_fields if key not in mapped_fields]
    completeness = completeness_level(field_count, expected=len(expected_fields))
    audit = dict(record.get("audit") or {})
    audit["field_count"] = field_count
    audit["missing_fields"] = missing
    audit["projection_completeness"] = completeness
    record["audit"] = audit
    record["confidence"] = projection_confidence(
        base_confidence=base_confidence,
        field_count=field_count,
        expected=len(expected_fields),
    )
    if not anchor_present and field_count <= 0:
        return None
    return record


def project_many(
    structures: list[StructureDict],
    *,
    page: int,
    schema_hint: str | None = None,
) -> list[ProjectionResult]:
    out: list[ProjectionResult] = []
    for structure in structures:
        if not isinstance(structure, dict):
            continue
        hint = schema_hint or infer_schema_hint(structure)
        if not hint:
            continue
        out.append(project_structure(structure, page=page, schema_hint=hint))
    return out
