# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Credit-report field schema and domain type validation for field grids."""

from __future__ import annotations

from docmirror.structure.ocr.field_grid.type_gate import types_compatible_with_hint

CREDIT_FIELD_TYPES: dict[str, tuple[str, ...]] = {
    "management_institution": ("text",),
    "account_identifier": ("long_id", "text"),
    "open_date": ("date",),
    "currency": ("currency", "text"),
    "due_date": ("date",),
    "loan_amount": ("amount",),
    "business_type": ("text",),
    "guarantee_type": ("text",),
    "account_status": ("text", "status_word"),
    "close_date": ("date", "text"),
}


def domain_type_ok(field_key: str, cell: dict) -> bool:
    allowed = CREDIT_FIELD_TYPES.get(field_key)
    if not allowed:
        return True
    inferred = tuple(cell.get("inferred_types") or ())
    if cell.get("geometry_status") == "quarantined":
        return False
    return types_compatible_with_hint(inferred, allowed)
