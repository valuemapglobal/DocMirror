# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Credit-report field schema and domain type validation for field grids."""

from __future__ import annotations

from docmirror.ocr.field_grid.type_gate import types_compatible_with_hint

CREDIT_FIELD_TYPES: dict[str, tuple[str, ...]] = {
    "management_institution": ("text",),
    "account_identifier": ("long_id", "text"),
    "open_date": ("date",),
    "currency": ("currency", "text"),
    "due_date": ("date",),
    "loan_amount": ("amount",),
    "business_type": ("text",),
    "guarantee_type": ("text",),
    "repayment_method": ("text",),
    "co_borrower_flag": ("text", "status_word"),
    "repayment_frequency": ("text",),
    "repayment_periods": ("number", "text"),
    "account_status": ("text", "status_word"),
    "snapshot_date": ("date", "text"),
    "balance": ("amount", "number"),
    "five_tier_class": ("text", "status_word"),
    "remaining_periods": ("number", "text"),
    "scheduled_payment": ("amount", "number"),
    "actual_payment": ("amount", "number"),
    "scheduled_payment_date": ("date", "number", "text"),
    "last_repayment_date": ("date", "text"),
    "current_overdue_periods": ("number", "text"),
    "current_overdue_amount": ("amount", "number"),
    "overdue_principal_31_60": ("amount", "number"),
    "overdue_principal_61_90": ("amount", "number"),
    "overdue_principal_91_180": ("amount", "number"),
    "overdue_principal_over_180": ("amount", "number"),
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
