# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Community reading-view adapter for credit reports."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from docmirror.plugins._base.community_reading_view import (
    assemble_reading_view,
    extract_labeled_notes,
    normalize_sections,
    page_coordinates,
)

_HEADER_FIELDS = [
    "subject_name",
    "company_name",
    "id_type",
    "id_number",
    "unified_social_credit_code",
    "zhongzheng_code",
    "report_number",
    "report_time",
    "query_institution",
]

_TABLE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "collection": "credit_summary",
        "title": "信贷交易信息概要",
        "kind": "object",
        "headers": ["业务类型", "账户数", "余额", "逾期情况"],
        "section_aliases": ("信息概要",),
    },
    {
        "collection": "credit_accounts",
        "title": "信贷账户明细",
        "kind": "collection",
        "headers": ["账户编号", "账户类型", "发放机构", "授信或贷款金额", "账户状态"],
        "section_aliases": ("信贷交易信息明细", "信贷记录明细", "信贷记录"),
    },
    {
        "collection": "credit_lines",
        "title": "授信额度明细",
        "kind": "collection",
        "headers": ["授信编号", "账户编号", "额度类型", "总额度", "已用额度", "状态"],
        "section_aliases": ("信贷交易信息明细", "信贷记录明细", "信贷记录", "信息概要"),
    },
    {
        "collection": "repayment_records",
        "title": "还款记录",
        "kind": "collection",
        "headers": ["账户编号", "年份", "月份", "还款状态", "逾期金额"],
        "section_aliases": ("信贷交易信息明细", "信贷记录明细", "信贷记录"),
    },
    {
        "collection": "overdue_records",
        "title": "逾期记录",
        "kind": "collection",
        "headers": ["账户编号", "期间", "逾期等级", "逾期金额", "逾期月数"],
        "section_aliases": ("信贷交易信息明细", "信贷记录明细", "信贷记录", "信息概要"),
    },
    {
        "collection": "public_records",
        "title": "公共信息记录",
        "kind": "collection",
        "headers": ["记录类型", "主管机关", "分类", "起止日期", "内容"],
        "section_aliases": ("公共信息明细", "公共记录明细", "公共记录", "公共信息"),
    },
    {
        "collection": "inquiry_records",
        "title": "查询记录",
        "kind": "collection",
        "headers": ["查询日期", "查询机构", "查询原因", "查询类型"],
        "section_aliases": ("查询记录",),
    },
)


def _page_number(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _section_id(sections: list[dict[str, Any]], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        for section in sections:
            title = re.sub(r"\s+", "", str(section.get("title") or section.get("name") or ""))
            if alias in title:
                return str(section["id"])
    return None


def _record_pages(value: Any) -> tuple[list[int], list[int]]:
    logical_pages: list[int] = []
    source_pages: list[int] = []
    records = value if isinstance(value, list) else [value]
    for record in records:
        if not isinstance(record, dict):
            continue
        direct_page = _page_number(record.get("page"))
        if direct_page:
            logical_pages.append(direct_page)
        refs = record.get("source_refs") if isinstance(record.get("source_refs"), list) else []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            logical = _page_number(ref.get("logical_page") or ref.get("page"))
            source = _page_number(ref.get("source_page") or ref.get("source_page_number"))
            if logical:
                logical_pages.append(logical)
            if source:
                source_pages.append(source)
    return logical_pages, source_pages


def _build_tables(
    parse_result: Any,
    data: dict[str, Any],
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    logical_to_source, source_to_logical = page_coordinates(parse_result)
    tables: list[dict[str, Any]] = []
    for order, spec in enumerate(_TABLE_SPECS, start=1):
        collection = str(spec["collection"])
        value = data.get(collection)
        if value in (None, "", [], {}):
            continue
        logical_pages, source_pages = _record_pages(value)
        if not logical_pages and source_pages:
            logical_pages = [source_to_logical[page] for page in source_pages if page in source_to_logical]
        if not source_pages and logical_pages:
            source_pages = [logical_to_source.get(page, page) for page in logical_pages]
        section_id = _section_id(sections, tuple(spec["section_aliases"]))
        table: dict[str, Any] = {
            "id": f"table:{collection}",
            "section_id": section_id,
            "title": spec["title"],
            "headers": list(spec["headers"]),
            "data_ref": {"type": spec["kind"], "path": f"/data/{collection}"},
            "row_count": len(value) if isinstance(value, list) else 1,
            "order": order,
        }
        if logical_pages:
            table["logical_page_start"] = min(logical_pages)
            table["logical_page_end"] = max(logical_pages)
        if source_pages:
            table["source_page_start"] = min(source_pages)
            table["source_page_end"] = max(source_pages)
        tables.append(table)
    return tables


def _merge_by_id(existing: list[Any], generated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*existing, *generated]:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("table_id") or "")
        if not item_id:
            item_id = (
                "item:"
                + hashlib.sha1(
                    json.dumps(item, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()[:12]
            )
        if item_id in seen:
            continue
        seen.add(item_id)
        merged.append({"id": item_id, **item})
    return merged


def build_credit_report_reading_view(parse_result: Any, data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Build the shared Community reading structures for a credit report."""
    sections = normalize_sections(parse_result, list(data.get("sections") or []))
    tables = _merge_by_id(list(data.get("tables") or []), _build_tables(parse_result, data, sections))
    notes = _merge_by_id(list(data.get("notes") or []), extract_labeled_notes(parse_result, sections))
    return assemble_reading_view(
        parse_result,
        fields=dict(data.get("fields") or {}),
        field_keys=_HEADER_FIELDS,
        sections=sections,
        tables=tables,
        notes=notes,
    )


__all__ = ["build_credit_report_reading_view"]
