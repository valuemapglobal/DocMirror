# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Optional bank_statement DEC entity validation (design 09 Phase 3 example)."""

from __future__ import annotations

from typing import Any

from docmirror.models.entities.domain_result import DomainExtractionResult


def validate_dec(dec: DomainExtractionResult) -> list[str]:
    """Lightweight checks — full typing deferred to plugin."""
    issues: list[str] = []
    entities = dec.entities or {}
    if dec.document_type == "bank_statement" and not entities:
        records = dec.structured_data
        if isinstance(records, list) and len(records) == 0:
            issues.append("bank_statement: no entities or structured_data records")
    return issues
