# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Field enrichment and validation helpers for premium L2 KV community plugins.

Post-processes plugin extract output with domain-specific normalization: VAT invoice
OCR digit correction, unified social credit code (USCC) checksum validation,
business license field cleanup, and credit report section heuristics.

Pipeline role: invoked at the end of ``extract_from_mirror`` in
``vat_invoice``, ``business_license``, and ``credit_report`` community plugins
after ``extract_kv_community_output`` builds the base envelope.

Key exports: ``normalize_vat_fields``, ``validate_uscc``,
``enrich_business_license_output``, ``enrich_credit_report_output``,
``enrich_vat_invoice_output``.
"""

from __future__ import annotations

import re
from typing import Any

from docmirror.ocr.correction.validators import validate_uscc

_CREDIT_SECTION_MARKERS = (
    "个人基本信息",
    "信息概要",
    "信贷交易信息",
    "信贷交易",
    "公共信息",
    "查询记录",
    "异议信息",
)


def _ocr_fix_digits(value: str) -> str:
    """Normalize common OCR confusions in numeric invoice fields."""
    out: list[str] = []
    for ch in value:
        if ch in "Oo":
            out.append("0")
        elif ch in "Il|":
            out.append("1")
        elif ch in "Zz":
            out.append("2")
        elif ch in "Ss":
            out.append("5")
        elif ch in "Bb":
            out.append("8")
        elif ch.isdigit():
            out.append(ch)
    return "".join(out)


def normalize_vat_fields(fields: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """OCR-correct invoice code/number and strip whitespace from amount fields."""
    out = dict(fields)
    warnings: list[str] = []
    for key in ("invoice_number", "invoice_code"):
        raw = str(out.get(key) or "")
        if not raw:
            continue
        cleaned = re.sub(r"\s+", "", raw)
        fixed = _ocr_fix_digits(cleaned)
        if fixed != cleaned:
            warnings.append(f"vat_ocr_corrected:{key}")
        out[key] = fixed
    amount = str(out.get("total_amount") or "")
    if amount:
        compact = re.sub(r"\s+", "", amount)
        if compact != amount:
            out["total_amount"] = compact
    return out, warnings


def enrich_business_license_output(
    output: dict[str, Any],
    *,
    parse_result: Any,
    full_text: str = "",
) -> dict[str, Any]:
    """USCC checksum + business_scope section block."""
    data = output.setdefault("data", {})
    fields = data.setdefault("fields", {})
    warnings = output.setdefault("status", {}).setdefault("warnings", [])

    uscc = str(fields.get("unified_social_credit_code") or "")
    if uscc:
        uscc_clean = re.sub(r"\s+", "", uscc).upper()
        fields["unified_social_credit_code"] = uscc_clean
        if validate_uscc(uscc_clean):
            fields["uscc_valid"] = True
        else:
            fields["uscc_valid"] = False
            warnings.append("uscc_checksum_invalid")

    scope = str(fields.get("business_scope") or "").strip()
    if scope:
        sections = list(data.get("sections") or [])
        sections.append(
            {
                "id": "business_scope",
                "title": "经营范围",
                "name": "经营范围",
                "content": scope,
            }
        )
        data["sections"] = sections

    return output


def enrich_vat_invoice_output(output: dict[str, Any]) -> dict[str, Any]:
    """Apply VAT OCR normalization to community output."""
    data = output.setdefault("data", {})
    fields, extra_warnings = normalize_vat_fields(dict(data.get("fields") or {}))
    data["fields"] = fields
    if extra_warnings:
        warnings = output.setdefault("status", {}).setdefault("warnings", [])
        for w in extra_warnings:
            if w not in warnings:
                warnings.append(w)
    tables = []
    records = data.get("records") or []
    if records:
        tables.append(
            {
                "table_id": "mirror_logical_0",
                "title": "line_items",
                "row_count": len(records),
            }
        )
        data["tables"] = tables
    return output


def build_credit_sections_light(parse_result: Any, full_text: str = "") -> list[dict[str, Any]]:
    """Lightweight section skeleton from headings / known credit report markers."""
    sections: list[dict[str, Any]] = []
    seen: set[str] = set()

    mirror_sections = getattr(parse_result, "sections", None) or []
    for i, sec in enumerate(mirror_sections):
        if isinstance(sec, dict):
            title = (sec.get("title") or sec.get("name") or "").strip()
            page_start = sec.get("page_start", 1)
            sec_id = sec.get("id")
        else:
            title = (getattr(sec, "title", None) or getattr(sec, "name", None) or "").strip()
            page_start = getattr(sec, "page_start", 1)
            sec_id = getattr(sec, "id", None)
        if not title or title in seen:
            continue
        seen.add(title)
        sections.append(
            {
                "id": sec_id or f"sec_{i}",
                "title": title,
                "name": title,
                "page_start": page_start,
            }
        )

    text = full_text or getattr(parse_result, "full_text", "") or ""
    for i, marker in enumerate(_CREDIT_SECTION_MARKERS):
        if marker in text and marker not in seen:
            seen.add(marker)
            sections.append(
                {
                    "id": f"sec_marker_{i}",
                    "title": marker,
                    "name": marker,
                    "page_start": 1,
                }
            )

    for page in getattr(parse_result, "pages", []) or []:
        for block in getattr(page, "texts", []) or []:
            content = (getattr(block, "content", None) or "").strip()
            level = getattr(block, "level", None)
            level_name = getattr(level, "name", str(level)) if level is not None else ""
            if level_name in ("TITLE", "HEADING") and content and content not in seen:
                if len(content) <= 40:
                    seen.add(content)
                    sections.append(
                        {
                            "id": f"sec_h_{len(sections)}",
                            "title": content,
                            "name": content,
                            "page_start": getattr(page, "page_number", 1),
                        }
                    )
    return sections


def enrich_credit_report_output(
    output: dict[str, Any],
    *,
    parse_result: Any,
    full_text: str = "",
) -> dict[str, Any]:
    """Attach section skeleton to credit report community output."""
    sections = build_credit_sections_light(parse_result, full_text)
    if sections:
        output.setdefault("data", {})["sections"] = sections
        output.setdefault("document", {})["archetype"] = "report_document"
    domain_specific = _domain_specific(parse_result)
    records = domain_specific.get("credit_repayment_records")
    if not records:
        records = _ensure_credit_repayment_records(parse_result)
    if records:
        output.setdefault("data", {})["repayment_records"] = records
        output["repayment_records"] = records
    accounts = domain_specific.get("credit_accounts")
    if not accounts:
        accounts = _extract_credit_accounts_from_local_structure_evidence(parse_result)
    if accounts:
        output.setdefault("data", {})["credit_accounts"] = accounts
    return output


def _domain_specific(parse_result: Any) -> dict[str, Any]:
    return getattr(getattr(parse_result, "entities", None), "domain_specific", {}) or {}


def _merge_unique_dicts(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]], *, id_key: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for item in [*existing, *incoming]:
        if not isinstance(item, dict):
            continue
        item_id = item.get(id_key)
        if item_id is not None:
            if item_id in seen:
                continue
            seen.add(item_id)
        out.append(item)
    return out


def _extract_credit_accounts_from_local_structure_evidence(parse_result: Any) -> list[dict[str, Any]]:
    domain_specific = _domain_specific(parse_result)
    from docmirror.models.mirror.domain_access import local_structure_evidence_pages_from_domain_specific

    evidence_pages = local_structure_evidence_pages_from_domain_specific(domain_specific)
    if not evidence_pages:
        return []
    try:
        from docmirror.plugins.credit_report.account_structure import (
            extract_credit_accounts_from_local_structure_evidence,
        )
    except Exception:
        return []

    out = extract_credit_accounts_from_local_structure_evidence(evidence_pages)
    accounts = out.get("credit_accounts") or []
    if accounts:
        domain_specific["credit_accounts"] = accounts
        if out.get("local_structures"):
            domain_specific["_local_structures"] = _merge_unique_dicts(
                list(domain_specific.get("_local_structures") or []),
                list(out.get("local_structures") or []),
                id_key="structure_id",
            )
    return accounts


def _ensure_credit_repayment_records(parse_result: Any) -> list[dict[str, Any]]:
    """Project repayment records from vNext/bundle micro-grid structures."""
    domain_specific = _domain_specific(parse_result)
    existing = domain_specific.get("credit_repayment_records")
    if existing:
        return list(existing)

    from docmirror.models.mirror.domain_access import micro_grid_structures_from_domain_specific
    from docmirror.models.mirror.vnext_access import iter_structures
    from docmirror.plugins.credit_report.repayment_grid import (
        dedupe_repayment_records,
        records_from_micro_grid_dict,
    )

    records: list[dict[str, Any]] = []
    for grid in micro_grid_structures_from_domain_specific(domain_specific):
        projected = records_from_micro_grid_dict(grid)
        if projected:
            records.extend(projected)

    if not records and hasattr(parse_result, "to_mirror_json_vnext"):
        mirror = parse_result.to_mirror_json_vnext()
        for grid in iter_structures(mirror if isinstance(mirror, dict) else {}, kind="micro_grid"):
            projected = records_from_micro_grid_dict(grid)
            if projected:
                records.extend(projected)

    if records:
        records = dedupe_repayment_records(records)
        domain_specific["credit_repayment_records"] = records
    return records
