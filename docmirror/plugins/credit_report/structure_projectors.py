# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Credit-report structure projectors (registered for structure_project)."""

from __future__ import annotations

from typing import Any

from docmirror.core.ocr.structure_project import ProjectionResult, register_structure_projector
from docmirror.plugins.credit_report.account_structure import (
    _account_from_field_grid,
    _account_from_label_value_graph,
)


def _expected_field_keys() -> list[str]:
    from docmirror.plugins.credit_report.account_structure import _FIELD_ALIASES

    return [field_key for field_key, _aliases in _FIELD_ALIASES]


class _CreditFieldGridAccountProjector:
    schema_hints = frozenset({"credit.field_grid.account"})

    def project(self, structure: dict[str, Any], *, page: int, schema_hint: str) -> ProjectionResult:
        record = _account_from_field_grid(structure, page=page)
        if record is None:
            return ProjectionResult(
                record=None,
                rejected=True,
                reject_reason="no_account_signal",
                schema_hint=schema_hint,
            )
        audit = record.get("audit") or {}
        return ProjectionResult(
            record=record,
            field_count=int(audit.get("field_count") or 0),
            missing_fields=list(audit.get("missing_fields") or []),
            completeness=str(audit.get("projection_completeness") or "partial"),
            confidence=float(record.get("confidence") or 0.0),
            schema_hint=schema_hint,
        )


class _CreditLabelValueAccountProjector:
    schema_hints = frozenset({"credit.label_value_graph.account"})

    def project(self, structure: dict[str, Any], *, page: int, schema_hint: str) -> ProjectionResult:
        record = _account_from_label_value_graph(structure, page=page)
        if record is None:
            return ProjectionResult(
                record=None,
                rejected=True,
                reject_reason="no_account_signal",
                schema_hint=schema_hint,
            )
        audit = record.get("audit") or {}
        return ProjectionResult(
            record=record,
            field_count=int(audit.get("field_count") or 0),
            missing_fields=list(audit.get("missing_fields") or []),
            completeness=str(audit.get("projection_completeness") or "partial"),
            confidence=float(record.get("confidence") or 0.0),
            schema_hint=schema_hint,
        )


class _CreditRepaymentGridProjector:
    schema_hints = frozenset({"credit.micro_grid.repayment"})

    def project(self, structure: dict[str, Any], *, page: int, schema_hint: str) -> ProjectionResult:
        from docmirror.plugins.credit_report.repayment_grid import records_from_micro_grid_dict

        records = records_from_micro_grid_dict(structure)
        if not records:
            return ProjectionResult(
                record=None,
                rejected=True,
                reject_reason="no_repayment_records",
                schema_hint=schema_hint,
            )
        payload = {
            "source": "micro_grid_structure",
            "page": page or structure.get("page"),
            "grid_id": structure.get("grid_id") or structure.get("structure_id"),
            "records": records,
            "audit": {
                "record_count": len(records),
                "projection_completeness": "complete" if records else "empty",
            },
        }
        return ProjectionResult(
            record=payload,
            field_count=len(records),
            completeness="complete",
            confidence=float(structure.get("confidence") or 0.85),
            schema_hint=schema_hint,
        )


def ensure_credit_structure_projectors_registered() -> None:
    register_structure_projector(_CreditFieldGridAccountProjector())
    register_structure_projector(_CreditLabelValueAccountProjector())
    register_structure_projector(_CreditRepaymentGridProjector())


ensure_credit_structure_projectors_registered()
