# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror-side institution hint — header-first resolution (ADR-BS-04)."""

from __future__ import annotations

import re
from typing import Any

_HEADER_LIMIT = 2000
_HEADER_BANK_PATTERNS = (
    re.compile(r"开户行\s+([\u4e00-\u9fa5A-Za-z（）()·\s]{4,40}?)(?:\s{2,}|起始日期|From\(|\n)"),
    re.compile(r"Bank Name\s+([\u4e00-\u9fa5A-Za-z（）()·\s]{4,60}?)(?:\s{2,}|From\(|\n)", re.I),
)


def _header_region(full_text: str) -> str:
    text = full_text or ""
    if not text:
        return ""
    ledger_start = text.find("|序号|")
    if ledger_start < 0:
        ledger_start = text.find("|No.")
    if ledger_start > 0:
        return text[:ledger_start]
    return text[:_HEADER_LIMIT]


def _header_bank_name(full_text: str) -> str | None:
    header = _header_region(full_text)
    for pat in _HEADER_BANK_PATTERNS:
        match = pat.search(header)
        if match:
            name = match.group(1).strip()
            if name and "银行" in name:
                return name
    return None


def resolve_document_institution(
    parse_result: Any,
    full_text: str = "",
) -> tuple[str | None, str]:
    """Resolve issuing institution with header-first priority (Mirror Core)."""
    text = full_text or getattr(parse_result, "full_text", "") or ""
    entities = getattr(parse_result, "entities", None)
    if entities is not None:
        org = getattr(entities, "organization", None)
        if org and str(org).strip():
            return str(org).strip(), "entities.organization"

    header_bank = _header_bank_name(text)
    if header_bank:
        return header_bank, "header.kv"

    if entities is not None:
        domain = getattr(entities, "domain_specific", None) or {}
        inst = domain.get("institution")
        if inst:
            return str(inst), "domain_specific.institution"

    return None, ""


__all__ = ["resolve_document_institution"]
