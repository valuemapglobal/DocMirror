# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Institution Authority Stack (IAS) for bank statement plugin.

Resolves issuing-bank hints from Mirror entities, header text, and layout profile
variants — never from transaction-body counterparty names alone.

Pipeline role: ``style_detector`` and ``build_style_context`` call
``resolve_institution_hint`` / ``resolve_institution_from_context``.

Key exports: ``resolve_institution_hint``, ``extract_identity_from_header``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from docmirror.plugins.bank_statement.institution import match_institution

if TYPE_CHECKING:
    from docmirror.plugins.bank_statement.context import StyleContext

_HEADER_LIMIT = 2000
_HEADER_BANK_PATTERNS = (
    re.compile(r"开户行\s+([\u4e00-\u9fa5A-Za-z（）()·\s]{4,40}?)(?:\s{2,}|起始日期|From\(|\n)"),
    re.compile(r"Bank Name\s+([\u4e00-\u9fa5A-Za-z（）()·\s]{4,60}?)(?:\s{2,}|From\(|\n)", re.I),
)


def _header_text(full_text: str) -> str:
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
    header = _header_text(full_text)
    for pat in _HEADER_BANK_PATTERNS:
        m = pat.search(header)
        if m:
            name = m.group(1).strip()
            if name and "银行" in name:
                return name
    return None


def resolve_institution_from_context(parse_result: Any, full_text: str) -> tuple[str | None, str]:
    """Resolve institution for StyleContext (before StyleDetector)."""
    entities = getattr(parse_result, "entities", None)
    if entities is not None:
        org = getattr(entities, "organization", None)
        if org:
            return str(org), "entities.organization"
        domain = getattr(entities, "domain_specific", None) or {}
        inst = domain.get("institution")
        if inst:
            return str(inst), "domain_specific.institution"

    header_bank = _header_bank_name(full_text)
    if header_bank:
        return header_bank, "header.kv"

    variant = match_institution(full_text, None)
    if variant and _header_text(full_text):
        header_only = _header_text(full_text)
        if any(kw in header_only for kw in variant.keywords):
            return variant.display_name, "layout_profile.variant"

    return None, ""


def resolve_institution_hint(
    ctx: StyleContext,
    keyword_map: dict[str, list[str]],
) -> tuple[str | None, str]:
    """Resolve institution hint for style metadata (IAS full stack)."""
    if ctx.institution:
        return ctx.institution, "entities.organization"

    header = _header_text(ctx.full_text)
    header_bank = _header_bank_name(ctx.full_text)
    if header_bank:
        return header_bank, "header.kv"

    variant = match_institution(header, None)
    if variant:
        return variant.display_name, "layout_profile.variant"

    if header and keyword_map:
        sorted_banks = sorted(
            keyword_map.items(),
            key=lambda kv: max(len(k) for k in kv[1]),
            reverse=True,
        )
        for name, keywords in sorted_banks:
            if any(kw in header for kw in keywords):
                return name, "institution_keywords.header"

    return None, ""


def extract_identity_from_header(full_text: str) -> dict[str, str]:
    """Extract account holder / number / period from document header region."""
    header = _header_text(full_text)
    out: dict[str, str] = {}

    m = re.search(
        r"账户名称\s+([\u4e00-\u9fa5A-Za-z（）()·\s]{2,60}?)(?:\s{2,}|开户行|Bank Name)",
        header,
    )
    if m:
        out["account_holder"] = m.group(1).strip()

    if not out.get("account_holder"):
        m = re.search(r"Account Name\s+([\u4e00-\u9fa5A-Za-z（）()·\s]{2,60}?)(?:\s{2,}|Bank Name)", header, re.I)
        if m:
            out["account_holder"] = m.group(1).strip()

    m = re.search(r"账号\s+(\d{8,20})", header)
    if m:
        out["account_number"] = m.group(1).strip()
    else:
        m = re.search(r"Account No\.\s+(\d{8,20})", header, re.I)
        if m:
            out["account_number"] = m.group(1).strip()

    start_m = re.search(r"起始日期\s*(\d{8})", header)
    end_m = re.search(r"截止日期\s*(\d{8})", header)
    if start_m and end_m:
        s, e = start_m.group(1), end_m.group(1)
        out["query_period"] = f"{s[:4]}-{s[4:6]}-{s[6:8]} ~ {e[:4]}-{e[4:6]}-{e[6:8]}"

    if "currency" not in out and "人民币" in header:
        out["currency"] = "CNY"

    bank = _header_bank_name(full_text)
    if bank:
        out["bank_name"] = bank

    return out
