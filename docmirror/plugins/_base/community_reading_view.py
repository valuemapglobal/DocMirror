# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared builders for the optional Community document reading view.

The reading view is intentionally an index over canonical business data.  It
orders sections, tables, and notes while keeping table rows and field values in
their existing ``/data`` locations.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

_CASHFLOW_PROFILES: dict[str, dict[str, Any]] = {
    "bank_statement": {
        "table_title": "交易明细",
        "field_keys": ["account_holder", "account_number", "bank_name", "query_period", "currency"],
        "headers": ["交易日期", "摘要", "收入", "支出", "余额", "交易对方"],
    },
    "wechat_payment": {
        "table_title": "微信支付交易明细",
        "field_keys": [
            "certificate_number",
            "account_holder",
            "id_number",
            "account_number",
            "query_period",
            "currency",
            "unit",
        ],
        "headers": ["交易单号", "交易时间", "交易类型", "收支方向", "交易方式", "金额", "交易对方"],
    },
    "alipay_payment": {
        "table_title": "支付宝交易明细",
        "field_keys": [
            "certificate_number",
            "account_holder",
            "id_number",
            "account_number",
            "query_period",
            "transaction_scope",
            "currency",
            "unit",
        ],
        "headers": ["交易时间", "收支方向", "交易对方", "商品说明", "收付款方式", "金额", "交易订单号"],
    },
}

_NOTE_PREFIX = re.compile(r"^(?:注|备注|说明|声明|温馨提示|重要提示|特别说明)(?:\s*[:：]|\s*$)")
_REPORT_NOTICE = re.compile(r"^(?:本报告仅供|本报告中的信息|本报告中所展示|本机构郑重声明)")


def _as_positive_int(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


def _stable_id(prefix: str, *parts: Any) -> str:
    identity = "|".join(re.sub(r"\s+", " ", str(part or "")).strip() for part in parts)
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def page_coordinates(parse_result: Any) -> tuple[dict[int, int], dict[int, int]]:
    """Return logical-to-source and source-to-first-logical page maps."""
    logical_to_source: dict[int, int] = {}
    source_to_logical: dict[int, int] = {}
    for index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        logical = _as_positive_int(getattr(page, "page_number", None), index)
        source = _as_positive_int(getattr(page, "source_page_number", None), logical)
        logical_to_source[logical] = source
        source_to_logical.setdefault(source, logical)
    return logical_to_source, source_to_logical


def normalize_sections(parse_result: Any, sections: list[Any]) -> list[dict[str, Any]]:
    """Add stable ordering and dual page coordinates to existing sections."""
    logical_to_source, source_to_logical = page_coordinates(parse_result)
    max_logical = max(logical_to_source, default=max(len(getattr(parse_result, "pages", []) or []), 1))
    max_source = max(logical_to_source.values(), default=max_logical)
    prepared: list[tuple[int, int, dict[str, Any]]] = []
    for index, item in enumerate(sections or [], start=1):
        if isinstance(item, dict):
            section = dict(item)
        else:
            section = {
                "id": getattr(item, "id", None),
                "title": getattr(item, "title", None) or getattr(item, "name", None),
                "page_start": getattr(item, "page_start", None),
            }
        title = str(section.get("title") or section.get("name") or "").strip()
        if not title:
            continue
        logical_start = _as_positive_int(
            section.get("logical_page_start") or section.get("page_start"),
            source_to_logical.get(_as_positive_int(section.get("source_page_start"), 1), 1),
        )
        section["id"] = str(section.get("id") or _stable_id("section", title, logical_start))
        section["title"] = title
        section.setdefault("name", title)
        section.setdefault("page_start", logical_start)
        section["logical_page_start"] = logical_start
        section["source_page_start"] = _as_positive_int(
            section.get("source_page_start"), logical_to_source.get(logical_start, logical_start)
        )
        prepared.append((logical_start, index, section))

    prepared.sort(key=lambda item: (item[0], item[1]))
    seen_ids: dict[str, int] = {}
    normalized: list[dict[str, Any]] = []
    for position, (logical_start, _, section) in enumerate(prepared, start=1):
        section_id = str(section["id"])
        seen_ids[section_id] = seen_ids.get(section_id, 0) + 1
        if seen_ids[section_id] > 1:
            section["id"] = f"{section_id}:{seen_ids[section_id]}"
        next_start = prepared[position][0] if position < len(prepared) else max_logical + 1
        logical_end = _as_positive_int(
            section.get("logical_page_end"), max(logical_start, min(max_logical, next_start - 1))
        )
        source_start = int(section["source_page_start"])
        source_end = _as_positive_int(
            section.get("source_page_end"), logical_to_source.get(logical_end, min(max_source, source_start))
        )
        section["order"] = position
        section["logical_page_end"] = max(logical_start, logical_end)
        section["source_page_end"] = max(source_start, source_end)
        normalized.append(section)
    return normalized


def section_for_page(sections: list[dict[str, Any]], logical_page: int) -> str | None:
    """Return the nearest enclosing section id for a logical page."""
    candidates = [
        section
        for section in sections
        if _as_positive_int(section.get("logical_page_start"), 1)
        <= logical_page
        <= _as_positive_int(section.get("logical_page_end"), logical_page)
    ]
    if not candidates:
        candidates = [
            section for section in sections if _as_positive_int(section.get("logical_page_start"), 1) <= logical_page
        ]
    if not candidates:
        return None
    return str(max(candidates, key=lambda item: _as_positive_int(item.get("logical_page_start"), 1))["id"])


def _normalize_referenced_items(items: list[Any], prefix: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items or [], start=1):
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        item_id = str(normalized.get("id") or normalized.get(f"{prefix}_id") or "")
        if not item_id:
            identity = normalized.get("title") or normalized.get("content") or normalized.get("data_ref") or index
            item_id = _stable_id(prefix, identity, index)
        if item_id in seen:
            continue
        seen.add(item_id)
        normalized["id"] = item_id
        normalized.setdefault("order", len(out) + 1)
        out.append(normalized)
    return out


def build_document_flow(
    *,
    fields: dict[str, Any],
    field_keys: list[str],
    sections: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a deterministic top-to-bottom flow containing references only."""
    flow: list[dict[str, Any]] = []
    grouped_fields = {
        str(key)
        for section in sections
        for key in (section.get("field_keys") or [])
        if isinstance(section.get("field_keys"), list)
    }
    selected_fields = [
        key for key in field_keys if key not in grouped_fields and fields.get(key) not in (None, "", [], {})
    ]
    attached_tables: set[str] = set()
    attached_notes: set[str] = set()

    def append(kind: str, **payload: Any) -> None:
        flow.append({"order": len(flow) + 1, "kind": kind, **payload})

    if not sections and selected_fields:
        append("field_group", field_keys=selected_fields)

    for section_index, section in enumerate(sections):
        section_id = str(section["id"])
        append("section", ref_id=section_id)
        section_fields = [
            str(key) for key in (section.get("field_keys") or []) if fields.get(str(key)) not in (None, "", [], {})
        ]
        if section_fields:
            append("field_group", field_keys=section_fields)
        if section_index == 0 and selected_fields:
            append("field_group", field_keys=selected_fields)
        members: list[tuple[int, int, str, dict[str, Any]]] = []
        for table in tables:
            if str(table.get("section_id") or "") != section_id:
                continue
            members.append(
                (
                    _as_positive_int(table.get("logical_page_start"), int(section.get("logical_page_start") or 1)),
                    _as_positive_int(table.get("order"), len(members) + 1),
                    "table",
                    table,
                )
            )
        for note in notes:
            if str(note.get("section_id") or "") != section_id:
                continue
            source_refs = note.get("source_refs") if isinstance(note.get("source_refs"), list) else []
            first_ref = source_refs[0] if source_refs and isinstance(source_refs[0], dict) else {}
            members.append(
                (
                    _as_positive_int(first_ref.get("logical_page"), int(section.get("logical_page_start") or 1)),
                    _as_positive_int(note.get("order"), len(members) + 1),
                    "note",
                    note,
                )
            )
        for _, _, kind, member in sorted(
            members,
            key=lambda item: (item[0], item[1], 0 if item[2] == "table" else 1),
        ):
            member_id = str(member["id"])
            append(kind, ref_id=member_id)
            (attached_tables if kind == "table" else attached_notes).add(member_id)

    for table in tables:
        table_id = str(table["id"])
        if table_id not in attached_tables:
            append("table", ref_id=table_id)
    for note in notes:
        note_id = str(note["id"])
        if note_id not in attached_notes:
            append("note", ref_id=note_id)
    return flow


def assemble_reading_view(
    parse_result: Any,
    *,
    fields: dict[str, Any],
    field_keys: list[str],
    sections: list[Any],
    tables: list[Any],
    notes: list[Any],
) -> dict[str, list[dict[str, Any]]]:
    """Normalize the common structures and return an additive reading view."""
    normalized_sections = normalize_sections(parse_result, sections)
    normalized_tables = _normalize_referenced_items(tables, "table")
    normalized_notes: list[dict[str, Any]] = []
    for note in _normalize_referenced_items(notes, "note"):
        content = str(note.get("content") or "").strip()
        content_ref = str(note.get("content_ref") or "").strip()
        if not content and not content_ref:
            continue
        if content:
            note["content"] = content
        if content_ref:
            note["content_ref"] = content_ref
        note["source_refs"] = list(note.get("source_refs") or [])
        normalized_notes.append(note)
    for note in normalized_notes:
        refs = note.get("source_refs") if isinstance(note.get("source_refs"), list) else []
        first_ref = refs[0] if refs and isinstance(refs[0], dict) else {}
        if not note.get("section_id") and first_ref.get("logical_page"):
            note["section_id"] = section_for_page(normalized_sections, int(first_ref["logical_page"]))
    flow = build_document_flow(
        fields=fields,
        field_keys=field_keys,
        sections=normalized_sections,
        tables=normalized_tables,
        notes=normalized_notes,
    )
    return {
        "sections": normalized_sections,
        "tables": normalized_tables,
        "notes": normalized_notes,
        "document_flow": flow,
    }


def extract_labeled_notes(parse_result: Any, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract explicit source notes without promoting ordinary body text."""
    notes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        logical_page = _as_positive_int(getattr(page, "page_number", None), index)
        source_page = _as_positive_int(getattr(page, "source_page_number", None), logical_page)
        for block in getattr(page, "texts", []) or []:
            content = re.sub(r"\s+", " ", str(getattr(block, "content", "") or "")).strip()
            if len(content) < 4 or not (_NOTE_PREFIX.match(content) or _REPORT_NOTICE.match(content)):
                continue
            marker = re.sub(r"\s+", "", content)
            if marker in seen:
                continue
            seen.add(marker)
            source_ref: dict[str, Any] = {"logical_page": logical_page, "source_page": source_page}
            evidence_ids = list(getattr(block, "evidence_ids", []) or [])
            if evidence_ids:
                source_ref["evidence_ids"] = evidence_ids
            bbox = getattr(block, "bbox", None)
            if bbox:
                source_ref["bbox"] = list(bbox)
            notes.append(
                {
                    "id": _stable_id("note", content),
                    "section_id": section_for_page(sections, logical_page),
                    "content": content,
                    "source_refs": [source_ref],
                    "order": len(notes) + 1,
                }
            )
    return notes


def _present_fields(fields: dict[str, Any], keys: list[str]) -> list[str]:
    return [key for key in keys if fields.get(key) not in (None, "", [], {})]


def _remaining_fields(fields: dict[str, Any], used: set[str]) -> list[str]:
    return [key for key, value in fields.items() if key not in used and value not in (None, "", [], {})]


def _record_page(record: dict[str, Any]) -> int | None:
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    candidates = [
        source.get("page"),
        source.get("logical_page"),
        record.get("page"),
    ]
    page_id = str(source.get("page_id") or "")
    if page_id:
        match = re.search(r"(\d+)$", page_id)
        if match:
            candidates.append(match.group(1))
    for candidate in candidates:
        try:
            page = int(candidate)
        except (TypeError, ValueError):
            continue
        if page > 0:
            return page
    return None


def _ensure_record_ids(records: list[Any]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(records, start=1):
        if not isinstance(item, dict):
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        record_id = str(item.get("id") or "") or _stable_id(
            "record",
            source.get("table_id") or source.get("source") or "records",
            item.get("row_index") or index,
        )
        if record_id in seen:
            record_id = f"{record_id}:{index}"
        seen.add(record_id)
        item["id"] = record_id
        ids.append(record_id)
    return ids


def _merge_items(existing: list[Any], generated: list[dict[str, Any]], *, prefix: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate([*existing, *generated], start=1):
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        item_id = str(normalized.get("id") or normalized.get(f"{prefix}_id") or "")
        if not item_id:
            item_id = _stable_id(prefix, normalized.get("title") or normalized.get("content") or index)
        if item_id in seen:
            continue
        seen.add(item_id)
        normalized["id"] = item_id
        out.append(normalized)
    return out


def _cashflow_reading_view(parse_result: Any, data: dict[str, Any], domain: str) -> dict[str, Any]:
    profile = _CASHFLOW_PROFILES[domain]
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    records = data.get("records") if isinstance(data.get("records"), list) else []
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    sections = list(data.get("sections") or [])
    account_fields = _present_fields(fields, list(profile["field_keys"]))
    if account_fields:
        sections.append(
            {
                "id": "section:account_information",
                "title": "账户及证明信息",
                "page_start": 1,
                "field_keys": account_fields,
            }
        )
    transaction_section_id: str | None = None
    if records:
        transaction_section_id = "section:transaction_details"
        first_page = min((_record_page(record) or 1 for record in records if isinstance(record, dict)), default=1)
        sections.append(
            {
                "id": transaction_section_id,
                "title": profile["table_title"],
                "page_start": first_page,
            }
        )
    remaining_fields = _remaining_fields(fields, set(account_fields))
    summary_section_id: str | None = None
    if remaining_fields or summary:
        summary_section_id = "section:transaction_summary"
        summary_page = max((_record_page(record) or 1 for record in records if isinstance(record, dict)), default=1)
        sections.append(
            {
                "id": summary_section_id,
                "title": "汇总及其他信息",
                "page_start": summary_page,
                "field_keys": remaining_fields,
            }
        )
    sections = normalize_sections(parse_result, _merge_items([], sections, prefix="section"))
    tables = list(data.get("tables") or [])
    if records:
        logical_pages = [_record_page(record) for record in records if isinstance(record, dict)]
        logical_pages = [page for page in logical_pages if page]
        table: dict[str, Any] = {
            "id": "table:transactions",
            "section_id": transaction_section_id,
            "title": profile["table_title"],
            "headers": list(profile["headers"]),
            "data_ref": {"type": "collection", "path": "/data/records"},
            "row_count": len(records),
        }
        if logical_pages:
            table["logical_page_start"] = min(logical_pages)
            table["logical_page_end"] = max(logical_pages)
        tables.append(table)
    if summary:
        tables.append(
            {
                "id": "table:transaction_summary",
                "section_id": summary_section_id,
                "title": "交易汇总",
                "headers": ["交易笔数", "总收入", "总支出", "净流入", "统计期间"],
                "data_ref": {"type": "object", "path": "/data/summary"},
                "row_count": 1,
            }
        )
    notes = _merge_items(
        list(data.get("notes") or []),
        extract_labeled_notes(parse_result, sections),
        prefix="note",
    )
    return assemble_reading_view(
        parse_result,
        fields=fields,
        field_keys=[],
        sections=sections,
        tables=_merge_items([], tables, prefix="table"),
        notes=notes,
    )


def _vat_reading_view(parse_result: Any, data: dict[str, Any]) -> dict[str, Any]:
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    line_items = data.get("line_items") if isinstance(data.get("line_items"), list) else []
    section_specs = (
        (
            "section:invoice_information",
            "发票信息",
            ["invoice_code", "invoice_number", "invoice_date", "machine_number", "check_code"],
        ),
        (
            "section:buyer_information",
            "购买方信息",
            ["buyer_name", "buyer_tax_id", "buyer_address_phone", "buyer_bank_account"],
        ),
        (
            "section:seller_information",
            "销售方信息",
            ["seller_name", "seller_tax_id", "seller_address_phone", "seller_bank_account"],
        ),
    )
    sections: list[dict[str, Any]] = []
    used_fields: set[str] = set()
    for section_id, title, keys in section_specs:
        present = _present_fields(fields, keys)
        if present:
            sections.append({"id": section_id, "title": title, "page_start": 1, "field_keys": present})
            used_fields.update(present)
    line_section_id: str | None = None
    if line_items:
        line_section_id = "section:invoice_line_items"
        sections.append({"id": line_section_id, "title": "商品或服务明细", "page_start": 1})
    total_keys = _present_fields(
        fields,
        ["amount_excluding_tax", "tax_amount", "total_amount", "total_amount_uppercase", "remarks"],
    )
    if total_keys:
        sections.append(
            {"id": "section:invoice_totals", "title": "价税合计及备注", "page_start": 1, "field_keys": total_keys}
        )
        used_fields.update(total_keys)
    remaining_fields = _remaining_fields(fields, used_fields)
    if remaining_fields:
        sections.append(
            {
                "id": "section:invoice_other",
                "title": "其他发票信息",
                "page_start": 1,
                "field_keys": remaining_fields,
            }
        )
    sections = normalize_sections(parse_result, sections)

    tables = list(data.get("tables") or [])
    if line_items:
        enhanced = False
        for table in tables:
            if not isinstance(table, dict):
                continue
            if str(table.get("table_id") or table.get("id") or "") == "vat_invoice_line_items":
                table.update(
                    {
                        "id": "table:line_items",
                        "section_id": line_section_id,
                        "headers": ["货物或服务名称", "规格型号", "单位", "数量", "单价", "金额", "税率", "税额"],
                        "data_ref": {"type": "collection", "path": "/data/line_items"},
                    }
                )
                enhanced = True
        if not enhanced:
            tables.append(
                {
                    "id": "table:line_items",
                    "section_id": line_section_id,
                    "title": "发票明细",
                    "headers": ["货物或服务名称", "规格型号", "单位", "数量", "单价", "金额", "税率", "税额"],
                    "data_ref": {"type": "collection", "path": "/data/line_items"},
                    "row_count": len(line_items),
                }
            )
    notes = _merge_items(list(data.get("notes") or []), extract_labeled_notes(parse_result, sections), prefix="note")
    return assemble_reading_view(
        parse_result,
        fields=fields,
        field_keys=[],
        sections=sections,
        tables=_merge_items([], tables, prefix="table"),
        notes=notes,
    )


def _business_license_reading_view(parse_result: Any, data: dict[str, Any]) -> dict[str, Any]:
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    sections: list[dict[str, Any]] = []
    existing_sections = {
        str(section.get("id") or ""): dict(section)
        for section in (data.get("sections") or [])
        if isinstance(section, dict) and section.get("id")
    }
    profile = (
        (
            "section:license_identity",
            "主体信息",
            ["company_name", "company_type", "unified_social_credit_code", "legal_representative"],
        ),
        (
            "section:license_registration",
            "登记信息",
            [
                "registered_capital",
                "date_of_establishment",
                "business_term",
                "address",
                "registration_authority",
                "registration_date",
            ],
        ),
        ("business_scope", "经营范围", ["business_scope"]),
    )
    used_fields: set[str] = set()
    for section_id, title, keys in profile:
        present = _present_fields(fields, keys)
        if present:
            sections.append(
                {
                    **existing_sections.get(section_id, {}),
                    "id": section_id,
                    "title": title,
                    "page_start": 1,
                    "field_keys": present,
                }
            )
            used_fields.update(present)
    other_fields = _remaining_fields(fields, {*used_fields, "important_notice"})
    if other_fields:
        sections.append(
            {
                "id": "section:license_other",
                "title": "其他登记信息",
                "page_start": 1,
                "field_keys": other_fields,
            }
        )
    notes = list(data.get("notes") or [])
    if fields.get("important_notice") not in (None, ""):
        sections.append(
            {
                **existing_sections.get("important_notice", {}),
                "id": "important_notice",
                "title": "重要提示",
                "page_start": 1,
            }
        )
        notes.append(
            {
                "id": "note:important_notice",
                "section_id": "important_notice",
                "content_ref": "/data/fields/important_notice",
                "source_refs": [],
            }
        )
    known_ids = {str(section["id"]) for section in sections}
    for section in data.get("sections") or []:
        if not isinstance(section, dict) or str(section.get("id") or "") in known_ids:
            continue
        sections.append(dict(section))
    return assemble_reading_view(
        parse_result,
        fields=fields,
        field_keys=[],
        sections=sections,
        tables=list(data.get("tables") or []),
        notes=_merge_items([], notes, prefix="note"),
    )


def _generic_reading_view(parse_result: Any, data: dict[str, Any]) -> dict[str, Any]:
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    records = data.get("records") if isinstance(data.get("records"), list) else []
    record_ids = _ensure_record_ids(records)
    sections = normalize_sections(parse_result, list(data.get("sections") or []))
    if fields and (not sections or int(sections[0].get("logical_page_start") or 1) > 1):
        sections = normalize_sections(
            parse_result,
            [
                {"id": "section:document_fields", "title": "文档信息", "page_start": 1},
                *sections,
            ],
        )
    tables: list[dict[str, Any]] = []
    _, source_to_logical = page_coordinates(parse_result)
    existing_tables = [item for item in (data.get("tables") or []) if isinstance(item, dict)]
    for index, item in enumerate(existing_tables, start=1):
        table = dict(item)
        table_id = str(table.get("id") or table.get("table_id") or f"table:{index}")
        table["id"] = table_id
        table["data_ref"] = {"type": "collection", "path": "/data/records"}
        source_pages = [int(page) for page in table.get("source_pages") or [] if str(page).isdigit()]
        logical_pages = [source_to_logical.get(page, page) for page in source_pages]
        if logical_pages:
            table["logical_page_start"] = min(logical_pages)
            table["logical_page_end"] = max(logical_pages)
            table["source_page_start"] = min(source_pages)
            table["source_page_end"] = max(source_pages)
            table.setdefault("section_id", section_for_page(sections, min(logical_pages)))
        matching_ids = [
            str(record.get("id"))
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("source"), dict)
            and str(record["source"].get("table_id") or "") in {table_id, str(table.get("table_id") or "")}
        ]
        if not matching_ids and len(existing_tables) == 1:
            matching_ids = record_ids
        if matching_ids:
            table["record_ids"] = matching_ids
        tables.append(table)
    if records and not tables:
        headers_source = next(
            (
                record.get("normalized") or record.get("raw")
                for record in records
                if isinstance(record, dict) and (record.get("normalized") or record.get("raw"))
            ),
            {},
        )
        if not sections:
            sections = normalize_sections(
                parse_result,
                [{"id": "section:document_records", "title": "明细数据", "page_start": 1}],
            )
        tables.append(
            {
                "id": "table:records",
                "section_id": str(sections[-1]["id"]),
                "title": "明细数据",
                "headers": [str(key) for key in headers_source],
                "data_ref": {"type": "collection", "path": "/data/records"},
                "record_ids": record_ids,
                "row_count": len(records),
            }
        )
    notes = _merge_items(list(data.get("notes") or []), extract_labeled_notes(parse_result, sections), prefix="note")
    return assemble_reading_view(
        parse_result,
        fields=fields,
        field_keys=list(fields),
        sections=sections,
        tables=tables,
        notes=notes,
    )


def finalize_community_reading_view(parse_result: Any, data: dict[str, Any], domain: str) -> None:
    """Populate the same optional reading structures for every Community route."""
    if domain == "credit_report":
        from docmirror.plugins.credit_report.reading_view import build_credit_report_reading_view

        view = build_credit_report_reading_view(parse_result, data)
    elif domain in _CASHFLOW_PROFILES:
        view = _cashflow_reading_view(parse_result, data, domain)
    elif domain == "vat_invoice":
        view = _vat_reading_view(parse_result, data)
    elif domain == "business_license":
        view = _business_license_reading_view(parse_result, data)
    else:
        view = _generic_reading_view(parse_result, data)
    data.update(view)
    data.setdefault("notes", [])
    data.setdefault("document_flow", [])


__all__ = [
    "assemble_reading_view",
    "build_document_flow",
    "extract_labeled_notes",
    "finalize_community_reading_view",
    "normalize_sections",
    "page_coordinates",
    "section_for_page",
]
