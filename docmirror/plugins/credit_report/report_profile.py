# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Credit-report subtype, content-mode, and cover-header recovery.

The public credit-report domain covers three materially different layouts:
personal brief reports, personal detail reports, and enterprise reports.  The
first and third normally expose native PDF text while personal detail reports
are commonly scanned and OCRed.  This module keeps that routing knowledge in
the domain package instead of spreading layout-specific regexes through the
shared KV extractor.
"""

from __future__ import annotations

import re
from typing import Any

REPORT_SUBTYPES = frozenset({"personal_brief", "personal_detail", "enterprise"})

_PERSON_ID_RE = re.compile(r"^(?:\d{15}|\d{17}[\dX]|[\dX*]{15,18})$")
_USCC_RE = re.compile(r"^[0-9A-HJ-NPQRTUWXY]{18}$")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _linear(text: str) -> str:
    text = str(text or "").replace("**", "").replace("|", " ")
    return re.sub(r"\s+", " ", text).strip()


def detect_credit_report_subtype(parse_result: Any, full_text: str = "") -> str:
    """Return ``personal_brief``, ``personal_detail``, ``enterprise``, or ``unknown``."""
    text = str(full_text or getattr(parse_result, "full_text", "") or "")
    compact = _compact(text)

    enterprise_markers = (
        "企业信用报告",
        "企业征信报告",
        "统一社会信用代码",
        "中征码",
    )
    if (
        any(marker in compact for marker in enterprise_markers[:2])
        or sum(marker in compact for marker in enterprise_markers[2:]) >= 2
    ):
        return "enterprise"

    detail_markers = (
        "信贷交易信息明细",
        "信贷交易授信及负债信息概要",
        "个人基本信息",
        "非信贷交易信息明细",
        "本人版",
    )
    brief_markers = (
        "信贷记录",
        "这部分包含您的信用卡",
        "发生过逾期的账户明细如下",
    )
    if any(marker in compact for marker in detail_markers):
        return "personal_detail"
    if any(marker in compact for marker in brief_markers):
        return "personal_brief"
    if "个人信用报告" in compact:
        return (
            "personal_detail" if detect_credit_report_content_mode(parse_result) == "scanned_ocr" else "personal_brief"
        )
    if detect_credit_report_content_mode(parse_result) == "scanned_ocr":
        return "personal_detail"
    return "unknown"


def detect_credit_report_content_mode(parse_result: Any) -> str:
    """Collapse page extraction modes to the public Mirror content-mode vocabulary."""
    modes = [
        str(getattr(page, "page_mode", "") or "").strip().lower() for page in getattr(parse_result, "pages", []) or []
    ]
    modes = [mode for mode in modes if mode]
    if not modes:
        return "native_text" if getattr(parse_result, "pages", None) else "unknown"
    scanned = sum(mode in {"scanned", "scanned_ocr", "ocr", "image"} for mode in modes)
    native = sum(mode in {"native", "native_text", "digital_text"} for mode in modes)
    if scanned == len(modes):
        return "scanned_ocr"
    if native == len(modes):
        return "native_text"
    if scanned:
        return "mixed"
    return "native_text"


def _search(text: str, pattern: str, *, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip(" \t:：,，;；") if match else ""


def _normalize_person_id(value: str) -> str:
    value = re.sub(r"[^0-9Xx*]", "", value or "").upper()
    return value if _PERSON_ID_RE.fullmatch(value) else ""


def _normalize_uscc(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z]", "", value or "").upper()
    return value if _USCC_RE.fullmatch(value) else ""


def _table_matrix(table: Any) -> list[list[str]]:
    matrix: list[list[str]] = []
    headers = [str(value or "").strip() for value in getattr(table, "headers", []) or []]
    if any(headers):
        matrix.append(headers)
    for row in getattr(table, "rows", []) or []:
        cells = [str(getattr(cell, "text", "") or "").strip() for cell in getattr(row, "cells", []) or []]
        if any(cells):
            matrix.append(cells)
    return matrix


def _next_column_value(matrix: list[list[str]], row_index: int, col_index: int) -> str:
    for row in matrix[row_index + 1 : row_index + 4]:
        if col_index < len(row) and row[col_index].strip():
            return row[col_index].strip()
    return ""


def _recover_personal_query_table_fields(parse_result: Any) -> dict[str, str]:
    """Recover the personal detail header from the standard two-row query table."""
    fields: dict[str, str] = {}
    for page in list(getattr(parse_result, "pages", []) or [])[:4]:
        for table in getattr(page, "tables", []) or []:
            matrix = _table_matrix(table)
            flat = " ".join(cell for row in matrix for cell in row)
            if "被查询者姓名" not in flat or "被查询者证件号码" not in flat:
                continue
            for row_index, row in enumerate(matrix):
                for col_index, cell in enumerate(row):
                    compact_cell = _compact(cell)
                    if compact_cell == "被查询者姓名":
                        name = re.sub(r"\s+", "", _next_column_value(matrix, row_index, col_index))
                        if re.fullmatch(r"[\u3400-\u9fff·]{2,12}", name):
                            fields["subject_name"] = name
                    if "被查询者证件号码" in compact_cell:
                        suffix = compact_cell.split("被查询者证件号码", 1)[-1]
                        id_number = _normalize_person_id(suffix)
                        if not id_number:
                            id_number = _normalize_person_id(_next_column_value(matrix, row_index, col_index))
                        if id_number:
                            fields["id_number"] = id_number
                    if compact_cell == "查询机构":
                        institution = re.sub(r"\s+", "", _next_column_value(matrix, row_index, col_index))
                        if institution:
                            fields["query_institution"] = institution
                    if "报告编号" in compact_cell:
                        report_number = re.sub(r"\D", "", compact_cell.split("报告编号", 1)[-1])
                        if 18 <= len(report_number) <= 30:
                            fields["report_number"] = report_number
                    if "报告时间" in compact_cell:
                        report_time = _normalize_date_time(compact_cell.split("报告时间", 1)[-1])
                        if report_time:
                            fields["report_time"] = report_time
            if fields.get("subject_name") and fields.get("id_number"):
                return fields
    return fields


def _normalize_date_time(value: str) -> str:
    datetime_match = re.search(
        r"(20\d{2})\s*[-年/.]\s*(\d{1,2})\s*[-月/.]\s*(\d{1,2})\s*日?"
        r"(?:T|\s*)(\d{1,2})\s*[:：]\s*(\d{2})(?:\s*[:：]\s*(\d{2}))?",
        value,
    )
    if datetime_match:
        date = (
            f"{int(datetime_match.group(1)):04d}-{int(datetime_match.group(2)):02d}-{int(datetime_match.group(3)):02d}"
        )
        return (
            f"{date}T{int(datetime_match.group(4)):02d}:{int(datetime_match.group(5)):02d}:"
            f"{int(datetime_match.group(6) or 0):02d}"
        )
    match = re.search(
        r"(20\d{2})\s*[-年/.]\s*(\d{1,2})\s*[-月/.]\s*(\d{1,2})\s*日?",
        value,
    )
    if not match:
        return ""
    date = f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return date


def recover_credit_report_header_fields(
    parse_result: Any,
    full_text: str = "",
    *,
    report_subtype: str = "",
) -> dict[str, str]:
    """Recover high-confidence cover/header facts from native text or OCR text."""
    text = _linear(full_text or getattr(parse_result, "full_text", "") or "")
    if not text:
        return {}
    # Header fields occur at the beginning.  Limiting the search avoids picking
    # up guarantors, spouses, and queried parties later in long reports.
    header = text[:12_000]
    subtype = report_subtype or detect_credit_report_subtype(parse_result, text)
    fields: dict[str, str] = {}

    if subtype == "enterprise":
        subject_name = _search(
            header,
            r"企业名称\s*[:：]?\s*(.{2,100}?)(?=\s+(?:中征码|统一社会信用代码|组织机构代码|查询机构|报告时间)\s*[:：]?)",
        )
        subject_name = re.sub(r"\s+", "", subject_name)
        if subject_name and not any(marker in subject_name for marker in ("自主查询版", "企业信用报告")):
            fields["subject_name"] = subject_name
            fields["company_name"] = subject_name

        uscc = _normalize_uscc(_search(header, r"统一社会信用代码\s*[:：]?\s*((?:[0-9A-Za-z]\s*){18})"))
        if uscc:
            fields["unified_social_credit_code"] = uscc

        zhongzheng_code = re.sub(
            r"\D",
            "",
            _search(header, r"(?:中征码|贷款卡(?:编码|号))\s*[:：]?\s*((?:\d\s*){12,20})"),
        )
        if 12 <= len(zhongzheng_code) <= 20:
            fields["zhongzheng_code"] = zhongzheng_code
    else:
        subject_name = _search(
            header,
            r"(?:被查询者姓名|(?<!配偶)(?<!法定代表人)姓名)\s*[:：]?\s*([\u3400-\u9fff·]{2,12})"
            r"(?=\s*(?:被查询者证件类型|被查询者证件号码|证件类型|证件号码|身份证号|婚姻状况|已婚|未婚|$))",
        )
        if subject_name:
            fields["subject_name"] = subject_name

        id_number = _normalize_person_id(
            _search(
                header,
                r"(?:被查询者证件号码|证件号码|身份证号)\s*[:：]?\s*((?:[0-9Xx*]\s*){15,18})",
            )
        )
        if id_number:
            fields["id_number"] = id_number

        id_type = _search(
            header,
            r"(?:被查询者证件类型|证件类型)\s*[:：]?\s*(身份证|居民身份证|护照|军官证|港澳居民来往内地通行证)",
        )
        if id_type:
            fields["id_type"] = id_type

    report_number = re.sub(
        r"\D",
        "",
        _search(header, r"(?:报告编号\s*[:：]?|\bNO\.?\s*)((?:\d\s*){18,30})", flags=re.IGNORECASE),
    )
    if 18 <= len(report_number) <= 30:
        fields["report_number"] = report_number

    raw_time = _search(
        header,
        r"报告时间\s*[:：]?\s*((?:20\d{2})[0-9T年月日./:\s-]{5,31})",
    )
    report_time = _normalize_date_time(raw_time)
    if report_time:
        fields["report_time"] = report_time

    query_institution = _search(
        header,
        r"查询机构\s*[:：]?\s*(.{2,100}?)(?=\s+(?:查询原因|报告时间|查询时间|第\s*\d+\s*页)\s*[:：]?)",
    )
    query_institution = re.sub(r"\s+", "", query_institution)
    if query_institution:
        fields["query_institution"] = query_institution

    if subtype == "personal_detail":
        fields.update(_recover_personal_query_table_fields(parse_result))

    fields["report_subtype"] = subtype
    fields["content_mode"] = detect_credit_report_content_mode(parse_result)
    return {key: value for key, value in fields.items() if value and value != "unknown"}


__all__ = [
    "REPORT_SUBTYPES",
    "detect_credit_report_content_mode",
    "detect_credit_report_subtype",
    "recover_credit_report_header_fields",
]
