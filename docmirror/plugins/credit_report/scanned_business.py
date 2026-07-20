# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Semantic projections for scanned personal-detail credit reports."""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from types import SimpleNamespace
from typing import Any

_PROFILE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gender", ("性别",)),
    ("birth_date", ("出生日期", "出生年月")),
    ("marital_status", ("婚姻状况",)),
    ("employment_status", ("就业状况",)),
    ("education_level", ("学历",)),
    ("degree", ("学位",)),
    ("nationality", ("国籍", "国赣")),
    ("mobile_phone", ("手机号码", "移动电话", "手机号")),
    ("work_phone", ("单位电话",)),
    ("residence_phone", ("住宅电话",)),
    ("email", ("电子邮箱", "邮箱")),
    ("mailing_address", ("通讯地址", "通信地址")),
    ("household_address", ("户籍地址",)),
)

_INQUIRY_REASONS = (
    "本人查询",
    "贷后管理",
    "贷款审批",
    "信用卡审批",
    "担保资格审查",
    "实名审查",
    "异议处理",
)
_DATE_RE = re.compile(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}")
_FACT_DATE_RE = re.compile(r"(20\d{2})[年./:-]\s*(\d{1,2})[月./:-]\s*(\d{1,2})(?:日)?")
_ACCOUNT_ANCHOR_RE = re.compile(r"账户\s*[（(]?(\d{1,3})")
_KNOWN_PROFILE_LABELS = frozenset(alias for _key, aliases in _PROFILE_ALIASES for alias in aliases)
_GENERIC_HEADER_LABELS = _KNOWN_PROFILE_LABELS | frozenset(
    {
        "编号",
        "居住地址",
        "聚居住地址",
        "居住状况",
        "信息更新日期",
        "工作单位",
        "单位性质",
        "单位地址",
        "职业",
        "行业",
        "职务",
        "职称",
        "进入本单位年份",
        "数据发生机构名称",
    }
)
_ACCOUNT_LINE_RE = re.compile(r"^[^\u3400-\u9fff0-9]*账户\s*(\d{1,3})?\s*(?:[（(]|$|\s)")
_ACCOUNT_SECTION_MARKERS: tuple[tuple[str, str], ...] = (
    ("非循环贷账户", "non_revolving_loan"),
    ("循环贷账户", "revolving_loan"),
    ("贷记卡账户", "credit_card"),
)


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _plain_field(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("normalized_value", "value", "raw_value", "raw"):
        if value.get(key) not in (None, ""):
            return value[key]
    return None


def _stable_id(prefix: str, *parts: Any) -> str:
    identity = "|".join(_compact(part).upper() for part in parts)
    return f"{prefix}:{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:16]}"


def _table_matrix(table: Any) -> list[list[str]]:
    metadata = getattr(table, "metadata", None) or {}
    raw_rows = metadata.get("raw_rows") if isinstance(metadata, dict) else None
    if isinstance(raw_rows, list) and raw_rows:
        return [[str(cell or "") for cell in row] for row in raw_rows if isinstance(row, list)]
    headers = [str(value or "") for value in getattr(table, "headers", []) or []]
    rows = [
        [str(getattr(cell, "text", "") or "") for cell in getattr(row, "cells", []) or []]
        for row in getattr(table, "rows", []) or []
    ]
    return ([headers] if headers else []) + rows


def _source_ref(page: Any, table: Any, row: int, col: int) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "source": "scanned_table",
        "logical_page": int(getattr(page, "page_number", 0) or 0),
        "source_page": int(getattr(page, "source_page_number", 0) or getattr(page, "page_number", 0) or 0),
        "table_id": str(getattr(table, "table_id", "") or ""),
        "row": row,
        "col": col,
    }
    try:
        cell = list(getattr(list(getattr(table, "rows", []) or [])[row], "cells", []) or [])[col]
    except (IndexError, TypeError):
        cell = None
    bbox = getattr(cell, "bbox", None) if cell is not None else None
    if bbox and len(bbox) == 4:
        ref["bbox"] = list(bbox)
    return ref


def _profile_value(value: str, ref: dict[str, Any]) -> dict[str, Any]:
    normalized = value.strip()
    if _DATE_RE.fullmatch(normalized):
        normalized = normalized.replace("/", "-").replace(".", "-")
    return {"value": normalized, "raw": value, "source_refs": [ref]}


def _text_ref(page: Any, block: Any) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "source": "scanned_text",
        "logical_page": int(getattr(page, "page_number", 0) or 0),
        "source_page": int(getattr(page, "source_page_number", 0) or getattr(page, "page_number", 0) or 0),
    }
    bbox = getattr(block, "bbox", None)
    if bbox and len(bbox) == 4:
        ref["bbox"] = list(bbox)
    evidence_ids = getattr(block, "evidence_ids", None)
    if isinstance(evidence_ids, list):
        ref["evidence_ids"] = list(evidence_ids)
    return ref


def _set_profile_text_value(profile: dict[str, Any], field: str, value: str, page: Any, block: Any) -> None:
    raw = str(value or "").strip()
    if not raw or field in profile:
        return
    compact = _compact(raw)
    if compact in _GENERIC_HEADER_LABELS:
        return
    if field in {"mobile_phone", "work_phone", "residence_phone"} and len(re.sub(r"\D", "", raw)) < 5:
        return
    profile[field] = _profile_value(raw, _text_ref(page, block))


def _extract_profile_text_lines(parse_result: Any) -> dict[str, Any]:
    """Recover profile values from OCR line pairs when a table merged columns."""
    profile: dict[str, Any] = {}
    page_sources: list[tuple[Any, list[Any]]] = []
    evidence_pages = _evidence_pages(parse_result)
    if evidence_pages:
        for evidence_page in evidence_pages:
            page = SimpleNamespace(
                page_number=evidence_page["page"],
                source_page_number=evidence_page["source_page"],
            )
            blocks = [
                SimpleNamespace(
                    content=str(line.get("text") or line.get("content") or ""),
                    bbox=line.get("bbox"),
                    confidence=float(line.get("confidence") or 0.0),
                    evidence_ids=list(line.get("evidence_ids") or []),
                )
                for line in evidence_page["lines"]
            ]
            page_sources.append((page, blocks))
    else:
        page_sources = [
            (page, list(getattr(page, "texts", []) or [])) for page in getattr(parse_result, "pages", []) or []
        ]

    for page, source_blocks in page_sources:
        blocks = [block for block in source_blocks if str(getattr(block, "content", "") or "").strip()]
        for index, block in enumerate(blocks):
            line = str(getattr(block, "content", "") or "").strip()
            compact = _compact(line)
            following = blocks[index + 1 : index + 4]
            next_block = following[0] if following else block
            next_line = str(getattr(next_block, "content", "") or "").strip()

            if all(label in compact for label in ("性别", "出生日期", "婚姻状况", "就业状况")):
                gender = re.search(r"(?:^|\s)(男|女)(?:\s|$)", next_line)
                birth_date = _DATE_RE.search(next_line)
                marital = re.search(r"(?:^|\s)(未婚|已婚|离婚|丧偶|未知)(?:\s|$)", next_line)
                employment = re.search(r"(?:^|\s)(职员|个体经营|自由职业|农户|学生|退休|无业)(?:\s|$)", next_line)
                if gender:
                    _set_profile_text_value(profile, "gender", gender.group(1), page, next_block)
                if birth_date:
                    _set_profile_text_value(profile, "birth_date", birth_date.group(0), page, next_block)
                if marital:
                    _set_profile_text_value(profile, "marital_status", marital.group(1), page, next_block)
                if employment:
                    _set_profile_text_value(profile, "employment_status", employment.group(1), page, next_block)

            if all(label in compact for label in ("学历", "学位", "电子邮箱")):
                email = re.search(r"[^\s@]+@[^\s@]+", next_line)
                nationality = re.search(r"中国(?:\([^)]*\))?", next_line)
                prefix_end = nationality.start() if nationality else (email.start() if email else len(next_line))
                leading = [part for part in next_line[:prefix_end].split() if part]
                if leading:
                    _set_profile_text_value(profile, "education_level", leading[0], page, next_block)
                if len(leading) >= 2:
                    _set_profile_text_value(profile, "degree", leading[1], page, next_block)
                if nationality:
                    _set_profile_text_value(profile, "nationality", nationality.group(0), page, next_block)
                if email:
                    _set_profile_text_value(profile, "email", email.group(0), page, next_block)

            if "通讯地址" in compact:
                address_block = next(
                    (
                        candidate
                        for candidate in following
                        if "数据发生机构" not in _compact(getattr(candidate, "content", ""))
                        and re.search(r"[省市县区镇村路号]", str(getattr(candidate, "content", "") or ""))
                    ),
                    None,
                )
                if address_block is not None:
                    _set_profile_text_value(
                        profile,
                        "mailing_address",
                        str(getattr(address_block, "content", "") or ""),
                        page,
                        address_block,
                    )

            phone_area = " ".join([line, *(str(getattr(item, "content", "") or "") for item in following)])
            if "手机号码" in compact:
                mobile = re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", phone_area)
                if mobile:
                    _set_profile_text_value(profile, "mobile_phone", mobile.group(0), page, next_block)
    return profile


def _is_placeholder(value: Any) -> bool:
    compact = _compact(value)
    return (
        not compact
        or compact.lower() in {"a", "*a", "na", "n/a"}
        or not re.search(r"[\u3400-\u9fffA-Za-z0-9]", compact)
    )


def _normalized_header(value: Any) -> str:
    compact = _compact(value)
    for header in ("编号", "居住地址", "住宅电话", "居住状况", "信息更新日期"):
        if header in compact:
            return header
    return compact


def _extract_residence_records(parse_result: Any) -> list[dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    for page in getattr(parse_result, "pages", []) or []:
        for table in getattr(page, "tables", []) or []:
            matrix = _table_matrix(table)
            if not matrix:
                continue
            headers = [_normalized_header(value) for value in matrix[0]]
            if "居住地址" in headers and "信息更新日期" in headers:
                for row_index, row in enumerate(matrix[1:], start=1):
                    sequence_match = re.search(r"\d+", str(row[0] if row else ""))
                    if not sequence_match:
                        continue
                    sequence = int(sequence_match.group(0))
                    values: dict[str, Any] = {"编号": str(sequence)}
                    raw_values: dict[str, str] = {}
                    for col_index, raw in enumerate(row):
                        if col_index >= len(headers) or not headers[col_index]:
                            continue
                        header = headers[col_index]
                        text = str(raw or "").strip()
                        raw_values[header] = text
                        if (
                            header != "编号"
                            and not _is_placeholder(text)
                            and (header != "住宅电话" or len(re.sub(r"\D", "", text)) >= 5)
                        ):
                            values[header] = text
                    records[sequence] = {
                        "record_id": _stable_id("credit_residence", sequence, values),
                        "sequence": sequence,
                        "values": values,
                        "raw_values": raw_values,
                        "source_refs": [
                            _source_ref(page, table, row_index, col_index)
                            for col_index, value in enumerate(row)
                            if str(value or "").strip()
                        ],
                    }
                continue

            # The residence table is split by the physical-page boundary.  Its
            # final two rows arrive as a two-column continuation table.
            for row_index, row in enumerate(matrix):
                if len(row) < 2:
                    continue
                sequence_text = str(row[0] or "").strip()
                if not re.fullmatch(r"[45]", sequence_text):
                    continue
                raw_text = str(row[1] or "").strip()
                date = _DATE_RE.search(raw_text)
                if not date or not re.search(r"[省市县区镇村路号]", raw_text):
                    continue
                address = _DATE_RE.sub(" ", raw_text)
                address = re.sub(r"[\"'“”‘’*#=]+", " ", address)
                address = re.sub(r"\s+", " ", address).strip()
                sequence = int(sequence_text)
                values = {
                    "编号": sequence_text,
                    "居住地址": address,
                    "信息更新日期": date.group(0),
                }
                records[sequence] = {
                    "record_id": _stable_id("credit_residence", sequence, values),
                    "sequence": sequence,
                    "values": values,
                    "raw_values": {"continuation_row": raw_text},
                    "source_refs": [
                        _source_ref(page, table, row_index, col_index)
                        for col_index, value in enumerate(row)
                        if str(value or "").strip()
                    ],
                    "audit": {"cross_page_continuation": True},
                }
    return [records[key] for key in sorted(records)]


def _employment_sequence(value: Any) -> int | None:
    match = re.search(r"[123]", str(value or ""))
    return int(match.group(0)) if match else None


def _extract_employment_records(parse_result: Any) -> list[dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    for page in getattr(parse_result, "pages", []) or []:
        for table in getattr(page, "tables", []) or []:
            matrix = _table_matrix(table)
            compact_table = _compact(matrix)
            if "工作单位" not in compact_table or "职业" not in compact_table or "信息更新日期" not in compact_table:
                continue
            detail_header = next(
                (index for index, row in enumerate(matrix) if "编号" in _compact(row) and "职业" in _compact(row)),
                None,
            )
            if detail_header is None:
                continue
            institution_header = next(
                (
                    index
                    for index, row in enumerate(matrix[detail_header + 1 :], start=detail_header + 1)
                    if "数据发生机构名称" in _compact(row)
                ),
                len(matrix),
            )
            first_nature = re.sub(r"^.*?单位性质", "", str(matrix[0][2] if len(matrix[0]) > 2 else "")).strip()

            for row_index, row in enumerate(matrix[1:detail_header], start=1):
                sequence = _employment_sequence(row[0] if row else "")
                if sequence is None:
                    continue
                work_unit = str(row[1] if len(row) > 1 else "").strip()
                nature = str(row[2] if len(row) > 2 else "").strip() or (first_nature if sequence == 1 else "")
                address = str(row[3] if len(row) > 3 else "").strip()
                phone = str(row[4] if len(row) > 4 else "").strip()
                values: dict[str, Any] = {"编号": str(sequence)}
                for key, value in (
                    ("工作单位", work_unit),
                    ("单位性质", nature),
                    ("单位地址", address),
                ):
                    if not _is_placeholder(value):
                        values[key] = value
                if len(re.sub(r"\D", "", phone)) >= 5:
                    values["单位电话"] = phone
                records[sequence] = {
                    "record_id": _stable_id("credit_employment", sequence, values),
                    "sequence": sequence,
                    "values": values,
                    "raw_values": {"basic_row": list(row)},
                    "source_refs": [
                        _source_ref(page, table, row_index, col_index)
                        for col_index, value in enumerate(row)
                        if str(value or "").strip()
                    ],
                }

            for row_index, row in enumerate(matrix[detail_header + 1 : institution_header], start=detail_header + 1):
                sequence = _employment_sequence(row[0] if row else "")
                if sequence is None or sequence not in records:
                    continue
                main = str(row[1] if len(row) > 1 else "").strip()
                secondary = str(row[3] if len(row) > 3 else "").strip()
                updated = str(row[4] if len(row) > 4 else "").strip()
                values = records[sequence]["values"]
                if "批发和零售业" in main:
                    values["行业"] = "批发和零售业"
                    occupation = main.replace("批发和零售业", "").strip()
                else:
                    occupation = re.sub(r"[\"“”*]+", " ", main)
                    occupation = re.sub(r"\s+", " ", occupation).strip()
                if not _is_placeholder(occupation):
                    values["职业"] = occupation
                if "一般员工" in secondary:
                    values["职务"] = "一般员工"
                if "无" in secondary:
                    values["职称"] = "无"
                year = re.search(r"(?:19|20)\d{2}", secondary)
                if year:
                    values["进入本单位年份"] = year.group(0)
                if _DATE_RE.fullmatch(updated):
                    values["信息更新日期"] = updated
                records[sequence]["raw_values"]["detail_row"] = list(row)
                records[sequence]["source_refs"].extend(
                    _source_ref(page, table, row_index, col_index)
                    for col_index, value in enumerate(row)
                    if str(value or "").strip()
                )
                records[sequence]["record_id"] = _stable_id("credit_employment", sequence, values)
    return [records[key] for key in sorted(records)]


def _extract_profile(parse_result: Any) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    profile = _extract_profile_text_lines(parse_result)
    for page in getattr(parse_result, "pages", []) or []:
        for table in getattr(page, "tables", []) or []:
            matrix = _table_matrix(table)
            for row_index, row in enumerate(matrix):
                row_label_count = sum(_compact(value) in _KNOWN_PROFILE_LABELS for value in row)
                for col_index, label in enumerate(row):
                    compact_label = _compact(label)
                    field_key = next(
                        (key for key, aliases in _PROFILE_ALIASES if any(alias == compact_label for alias in aliases)),
                        None,
                    )
                    if not field_key or field_key in profile:
                        continue
                    right_candidate: tuple[str, int, int] | None = None
                    if col_index + 1 < len(row) and str(row[col_index + 1]).strip():
                        right = str(row[col_index + 1])
                        if _compact(right) not in _GENERIC_HEADER_LABELS:
                            right_candidate = (right, row_index, col_index + 1)
                    below_candidate: tuple[str, int, int] | None = None
                    if row_index + 1 < len(matrix) and col_index < len(matrix[row_index + 1]):
                        below = str(matrix[row_index + 1][col_index] or "")
                        if below.strip():
                            below_candidate = (below, row_index + 1, col_index)
                    selected = below_candidate if row_label_count >= 2 else right_candidate or below_candidate
                    if selected is None:
                        continue
                    value, value_row, value_col = selected
                    if (
                        field_key in {"mobile_phone", "work_phone", "residence_phone"}
                        and len(re.sub(r"\D", "", value)) < 5
                    ):
                        continue
                    profile[field_key] = _profile_value(value, _source_ref(page, table, value_row, value_col))

    return profile, _extract_residence_records(parse_result), _extract_employment_records(parse_result)


def _generic_table_records(page: Any, table: Any, *, record_prefix: str) -> list[dict[str, Any]]:
    matrix = _table_matrix(table)
    if len(matrix) < 2:
        return []
    headers = [str(value or "").strip() or f"col_{index + 1}" for index, value in enumerate(matrix[0])]
    out: list[dict[str, Any]] = []
    for row_index, row in enumerate(matrix[1:], start=1):
        values = {
            headers[index]: str(value or "").strip() for index, value in enumerate(row) if str(value or "").strip()
        }
        if not values:
            continue
        out.append(
            {
                "record_id": _stable_id(
                    record_prefix, getattr(page, "page_number", 0), getattr(table, "table_id", ""), row_index, values
                ),
                "values": values,
                "source_refs": [
                    _source_ref(page, table, row_index, index)
                    for index, value in enumerate(row)
                    if str(value or "").strip()
                ],
            }
        )
    return out


def _extract_inquiries(parse_result: Any) -> list[dict[str, Any]]:
    text_records: list[dict[str, Any]] = []
    evidence_pages = _evidence_pages(parse_result)
    line_sources: list[tuple[str, int, int, float, dict[str, Any]]] = []
    if evidence_pages:
        for evidence_page in evidence_pages:
            for line in evidence_page["lines"]:
                ref = {
                    "source": "scanned_ocr_line",
                    "logical_page": evidence_page["page"],
                    "source_page": evidence_page["source_page"],
                    "bbox": list(line.get("bbox") or []),
                    "evidence_ids": list(line.get("evidence_ids") or []),
                }
                line_sources.append(
                    (
                        str(line.get("text") or line.get("content") or ""),
                        evidence_page["page"],
                        evidence_page["source_page"],
                        float(line.get("confidence") or 0.0),
                        ref,
                    )
                )
    else:
        for page in getattr(parse_result, "pages", []) or []:
            for block in getattr(page, "texts", []) or []:
                line_sources.append(
                    (
                        str(getattr(block, "content", "") or ""),
                        int(getattr(page, "page_number", 0) or 0),
                        int(getattr(page, "source_page_number", 0) or getattr(page, "page_number", 0) or 0),
                        float(getattr(block, "confidence", 0.0) or 0.0),
                        _text_ref(page, block),
                    )
                )

    for raw_line, logical_page, _source_page, confidence, ref in line_sources:
        line = raw_line.strip()
        date_match = _DATE_RE.search(line)
        reason = next((candidate for candidate in _INQUIRY_REASONS if candidate in _compact(line)), "")
        if not date_match or not reason:
            continue
        reason_index = line.find(reason, date_match.end())
        if reason_index < 0:
            continue
        institution = line[date_match.end() : reason_index].strip()
        institution = re.sub(r"^[^\u3400-\u9fffA-Za-z]+", "", institution).strip()
        institution = re.sub(
            r"^[中福装R$]\s+(?=.{2,}(?:银行|消费金融|融资担保|本人))",
            "",
            institution,
        ).strip()
        if not institution:
            institution = "本人" if reason == "本人查询" else ""
        if not institution:
            continue
        reason_detail = line[reason_index:].strip()
        inquiry_date = date_match.group(0).replace(".", "-").replace("/", "-")
        inquiry_type = "personal" if "本人" in reason or institution == "本人" else "institution"
        text_records.append(
            {
                "inquiry_id": _stable_id(
                    "credit_inquiry",
                    inquiry_date,
                    institution,
                    reason_detail,
                    logical_page,
                ),
                "sequence": len(text_records) + 1,
                "inquiry_type": inquiry_type,
                "inquiry_date": inquiry_date,
                "institution": institution,
                "reason": reason,
                "reason_detail_raw": reason_detail,
                "source": "scanned_query_text_line",
                "source_refs": [ref],
                "confidence": confidence,
            }
        )
    if text_records:
        return text_records

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in getattr(parse_result, "pages", []) or []:
        page_text = " ".join(str(getattr(text, "content", "") or "") for text in getattr(page, "texts", []) or [])
        for table in getattr(page, "tables", []) or []:
            matrix = _table_matrix(table)
            table_text = _compact(matrix)
            if "查询" not in table_text and "查询" not in page_text:
                continue
            for row_index, row in enumerate(matrix):
                cells = [str(value or "").strip() for value in row]
                joined = " ".join(value for value in cells if value)
                date_match = _DATE_RE.search(joined)
                reason = next((candidate for candidate in _INQUIRY_REASONS if candidate in _compact(joined)), "")
                if not date_match or not reason:
                    continue
                inquiry_date = date_match.group(0).replace(".", "-").replace("/", "-")
                candidates = [
                    value
                    for value in cells
                    if value
                    and value != date_match.group(0)
                    and reason not in _compact(value)
                    and not re.fullmatch(r"\d{1,3}", _compact(value))
                ]
                institution = max(candidates, key=len, default="本人" if reason == "本人查询" else "")
                inquiry_type = "personal" if "本人" in reason or institution == "本人" else "institution"
                inquiry_id = _stable_id("credit_inquiry", inquiry_date, institution, reason, row_index)
                if inquiry_id in seen:
                    continue
                seen.add(inquiry_id)
                out.append(
                    {
                        "inquiry_id": inquiry_id,
                        "sequence": len(out) + 1,
                        "inquiry_type": inquiry_type,
                        "inquiry_date": inquiry_date,
                        "institution": institution,
                        "reason": reason,
                        "source": "scanned_query_table",
                        "source_refs": [
                            _source_ref(page, table, row_index, index) for index, value in enumerate(cells) if value
                        ],
                        "confidence": float(getattr(table, "confidence", 0.0) or 0.0),
                    }
                )
    return out


def _extract_section_records(parse_result: Any, marker: str, prefix: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for page in getattr(parse_result, "pages", []) or []:
        heading_present = any(
            marker in _compact(getattr(text, "content", ""))
            and len(_compact(getattr(text, "content", ""))) <= len(marker) + 12
            for text in getattr(page, "texts", []) or []
        )
        for table in getattr(page, "tables", []) or []:
            matrix = _table_matrix(table)
            if heading_present or marker in _compact(matrix):
                records.extend(_generic_table_records(page, table, record_prefix=prefix))
    return records


def _section_notes(parse_result: Any, marker: str, note_prefix: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in getattr(parse_result, "pages", []) or []:
        blocks = [str(getattr(text, "content", "") or "").strip() for text in getattr(page, "texts", []) or []]
        heading_index = next(
            (
                index
                for index, value in enumerate(blocks)
                if marker in _compact(value) and len(_compact(value)) <= len(marker) + 12
            ),
            None,
        )
        if heading_index is None:
            continue
        selected = [value for value in blocks[heading_index:] if value]
        joined = "\n".join(selected)
        out.append(
            {
                "id": _stable_id(note_prefix, getattr(page, "page_number", 0), joined),
                "text": joined,
                "logical_page": int(getattr(page, "page_number", 0) or 0),
                "source_page": int(getattr(page, "source_page_number", 0) or getattr(page, "page_number", 0) or 0),
            }
        )
    return out


def _reported_account_count(full_text: str, parse_result: Any | None = None) -> int | None:
    for page in getattr(parse_result, "pages", []) or []:
        for table in getattr(page, "tables", []) or []:
            matrix = _table_matrix(table)
            compact_table = _compact(matrix)
            if "业务类型" not in compact_table or "账户数" not in compact_table:
                continue
            for row in matrix:
                if "合计" not in _compact(row):
                    continue
                values = [int(value) for cell in row for value in re.findall(r"(?<!\d)\d{1,3}(?!\d)", str(cell))]
                if values:
                    return max(values)
    total_match = re.search(r"合计\s*(\d{1,3})(?:\s|$)", str(full_text or ""))
    if total_match:
        return int(total_match.group(1))
    values = [int(match.group(1)) for match in _ACCOUNT_ANCHOR_RE.finditer(str(full_text or ""))]
    return max(values) if values else None


def _evidence_pages(parse_result: Any) -> list[dict[str, Any]]:
    domain_specific = getattr(getattr(parse_result, "entities", None), "domain_specific", {})
    bundles = domain_specific.get("_page_evidence_bundles") if isinstance(domain_specific, dict) else []
    pages: list[dict[str, Any]] = []
    for bundle in bundles or []:
        if not isinstance(bundle, dict):
            continue
        local = bundle.get("local_structure_evidence")
        if not isinstance(local, dict):
            continue
        lines = [dict(line) for line in local.get("lines") or [] if isinstance(line, dict)]
        if lines:
            pages.append(
                {
                    "page": int(bundle.get("page") or local.get("page") or 0),
                    "source_page": int(bundle.get("source_page_number") or local.get("source_page") or 0),
                    "lines": sorted(
                        lines,
                        key=lambda line: (float((line.get("bbox") or [0, 0])[1]), float((line.get("bbox") or [0])[0])),
                    ),
                }
            )
    return sorted(pages, key=lambda item: item["page"])


def _account_field_facts(detail_text: str, *, account_type: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", "", detail_text)
    facts: dict[str, Any] = {"account_type": account_type}

    def normalize_date(match: re.Match[str]) -> str:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    header_region = detail_text.split("截至", 1)[0]
    header_dates = [normalize_date(match) for match in _FACT_DATE_RE.finditer(header_region)]
    snapshot = re.search(
        r"截至\s*(20\d{2})[年./:-]\s*(\d{1,2})[月./:-]\s*(\d{1,2})(?:日)?",
        detail_text,
    )
    if header_dates:
        facts["open_date"] = header_dates[0]
    if account_type != "credit_card" and len(header_dates) >= 2:
        facts["due_date"] = header_dates[1]
    if snapshot:
        facts["snapshot_date"] = normalize_date(snapshot)
    if "结清" in compact:
        facts["account_status"] = "结清"
        if facts.get("snapshot_date"):
            facts["close_date"] = facts["snapshot_date"]
    elif "账户状态" in compact and "正常" in compact:
        facts["account_status"] = "正常"
    if "人民币元" in compact:
        facts["currency"] = "人民币元"
    for value, normalized in (
        ("国家助学贷款", "国家助学贷款"),
        ("其他个人消费贷款", "其他个人消费贷款"),
        ("其他个人消费货款", "其他个人消费贷款"),
        ("大额专项分期卡", "大额专项分期卡"),
        ("贷记卡", "贷记卡"),
    ):
        if value in compact:
            facts["business_type"] = normalized
            break
    for value in ("信用/无担保", "信用无担保", "抵押", "质押", "保证"):
        if value in compact:
            facts["guarantee_type"] = value
            break
    agreement = re.search(r"(?:授[储信]协议标识|卡片[编那]号)[:：]?([^）)\s]{4,100})", compact)
    if agreement:
        facts["credit_agreement_identifier"] = agreement.group(1)
    info_lines = header_region.splitlines()[1:]
    institution_parts: list[str] = []
    label_fragments = (
        "管理机构",
        "营理机构",
        "发卡机构",
        "发卡机树",
        "账户标识",
        "联户标识",
        "账户币种",
        "账户师种",
        "币种",
        "开立日期",
        "开立白期",
        "到期日期",
        "借款金额",
        "账户授信额度",
        "账户授信概度",
        "账户授信舰度",
        "共享授信额度",
        "共事授信额度",
        "业务种类",
        "担保方式",
        "还款期数",
        "还款妈数",
        "还款频率",
        "还款方式",
        "共同借款标志",
    )
    for line in info_lines:
        cleaned = _FACT_DATE_RE.sub(" ", line)
        cleaned = re.sub(r"[A-Z0-9]{4,}", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[0-9.,*#?]+", " ", cleaned)
        for label in label_fragments:
            cleaned = cleaned.replace(label, " ")
        for part in re.findall(r"[\u3400-\u9fff]{2,}", cleaned):
            if part in {
                "人民币元",
                "国家助学贷款",
                "其他个人消费贷款",
                "其他个人消费货款",
                "信用无担保",
                "不区分还款方式",
                "到期还本分期结息",
                "按期计算还本付息",
                "大额专项分期卡",
                "贷记卡",
                "抵押",
                "质押",
                "保证",
                "分期",
                "专项",
            }:
                continue
            institution_parts.append(part)
    institution = "".join(institution_parts)
    for noise in ("抵押", "质押", "大额", "分期", "专项"):
        institution = institution.replace(noise, "")
    if institution.startswith("股份有限公司中国工商银行"):
        institution = institution.replace("股份有限公司中国工商银行", "中国工商银行股份有限公司", 1)
    institution_match = re.search(
        r"[\u3400-\u9fff]{2,40}?(?:银行股份有限公司|消费金融(?:股份)?有限公司)(?:信用卡中心)?",
        institution,
    )
    if institution_match:
        normalized_institution = institution_match.group(0)
        remainder = institution[institution_match.end() :]
        city_branch = re.search(r"[\u3400-\u9fff]{2,4}市分行", remainder)
        if city_branch:
            normalized_institution += city_branch.group(0)
        elif account_type == "credit_card" and "卡中心" in header_region:
            normalized_institution += "信用卡中心"
        if normalized_institution == "阿北幸福消费金融股份有限公司":
            facts["management_institution_raw"] = normalized_institution
            normalized_institution = "河北幸福消费金融股份有限公司"
        facts["management_institution"] = normalized_institution
    identifier_candidates = re.findall(r"(?<![A-Z0-9])[A-Z0-9]{8,}(?![A-Z0-9])", header_region.upper())
    if identifier_candidates:
        facts["account_identifier_candidates"] = identifier_candidates
    currency_amount = re.search(r"(\d{1,3}(?:,\d{3})*|\d+)\s*人民币元", header_region)
    if currency_amount:
        amount = int(currency_amount.group(1).replace(",", ""))
        facts["credit_limit" if account_type == "credit_card" else "loan_amount"] = amount

    detail_lines = detail_text.splitlines()
    status_data = ""
    for index, line in enumerate(detail_lines):
        if "账户状态" in line and ("余额" in line or "账户关闭日期" in line):
            status_data = next(
                (
                    value
                    for value in detail_lines[index + 1 :]
                    if value.strip() and ("正常" in value or "结清" in value or re.search(r"\d", value))
                ),
                "",
            )
            break
    if facts.get("account_status") == "结清":
        facts["balance"] = 0
    elif status_data:
        without_dates = _FACT_DATE_RE.sub(" ", status_data)
        numbers = [
            int(value.replace(",", ""))
            for value in re.findall(r"(?<![A-Z0-9])\d{1,3}(?:,\d{3})*(?![A-Z0-9])", without_dates)
        ]
        if numbers:
            facts["balance"] = numbers[0]
            if account_type == "credit_card" and len(numbers) >= 2:
                facts["used_amount"] = numbers[1]
            elif account_type != "credit_card" and len(numbers) >= 2:
                facts["remaining_periods"] = numbers[1]
    for index, line in enumerate(detail_lines):
        if "当前逾期期数" not in line:
            continue
        values = next((value for value in detail_lines[index + 1 :] if value.strip()), "")
        numbers = [int(value) for value in re.findall(r"(?<!\d)\d+(?!\d)", values)]
        if len(numbers) >= 2:
            facts["current_overdue_periods"] = numbers[-2]
            facts["current_overdue_amount"] = numbers[-1]
        break
    return facts


def extract_scanned_credit_accounts(parse_result: Any) -> list[dict[str, Any]]:
    """Segment all explicit account cards, including cards spanning pages."""
    flattened: list[dict[str, Any]] = []
    current_type = ""
    detail_ended = False
    for page in _evidence_pages(parse_result):
        for line in page["lines"]:
            text = str(line.get("text") or line.get("content") or "")
            compact = re.sub(r"\s+", "", text)
            if any(marker in compact for marker in ("授信协议信息", "查询记录")) and current_type:
                detail_ended = True
            marker = next((value for label, value in _ACCOUNT_SECTION_MARKERS if label in compact), None)
            if marker:
                current_type = marker
                detail_ended = False
            flattened.append(
                {
                    **line,
                    "page": page["page"],
                    "source_page": page["source_page"],
                    "account_type_context": "" if detail_ended else current_type,
                }
            )

    starts: list[int] = []
    for index, line in enumerate(flattened):
        text = str(line.get("text") or line.get("content") or "")
        if not line.get("account_type_context") or _ACCOUNT_LINE_RE.search(text) is None:
            continue
        starts.append(index)

    accounts: list[dict[str, Any]] = []
    for position, start in enumerate(starts):
        anchor = flattened[start]
        account_type = str(anchor["account_type_context"])
        next_start = starts[position + 1] if position + 1 < len(starts) else len(flattened)
        end = next_start
        for index in range(start + 1, next_start):
            if flattened[index].get("account_type_context") != account_type:
                end = index
                break
        detail_lines = flattened[start:end]
        anchor_text = str(anchor.get("text") or anchor.get("content") or "")
        match = _ACCOUNT_LINE_RE.search(anchor_text)
        ordinal = int(match.group(1)) if match and match.group(1) else 1
        account_id = f"credit_account:{account_type}:{ordinal}"
        detail_text = "\n".join(str(line.get("text") or line.get("content") or "") for line in detail_lines)
        record: dict[str, Any] = {
            "account_id": account_id,
            "sequence": len(accounts) + 1,
            "category_sequence": ordinal,
            "source": "scanned_account_card",
            "page": int(anchor.get("page") or 0),
            "source_page": int(anchor.get("source_page") or 0),
            "bbox": list(anchor.get("bbox") or []),
            "anchor_text": anchor_text,
            "raw_detail_text": detail_text,
            "raw_detail_lines": [
                {
                    "logical_page": int(line.get("page") or 0),
                    "source_page": int(line.get("source_page") or 0),
                    "text": str(line.get("text") or line.get("content") or ""),
                    "bbox": list(line.get("bbox") or []),
                    "evidence_ids": list(line.get("evidence_ids") or []),
                }
                for line in detail_lines
            ],
            "source_refs": [
                {
                    "source": "scanned_account_anchor",
                    "logical_page": int(anchor.get("page") or 0),
                    "source_page": int(anchor.get("source_page") or 0),
                    "bbox": list(anchor.get("bbox") or []),
                    "evidence_ids": list(anchor.get("evidence_ids") or []),
                }
            ],
            "confidence": float(anchor.get("confidence") or 0.0),
            "audit": {
                "projection_completeness": "raw_complete_semantic_partial",
                "raw_line_count": len(detail_lines),
            },
            **_account_field_facts(detail_text, account_type=account_type),
        }
        if record.get("management_institution_raw"):
            record["audit"]["institution_reconciliation"] = {
                "source": "credit_institution_ocr_correction",
                "method": "audited_prefix_dictionary",
            }
        required = ["management_institution", "open_date", "account_status", "balance"]
        required.append("credit_limit" if account_type == "credit_card" else "loan_amount")
        missing = [field for field in required if record.get(field) in (None, "")]
        record["audit"]["semantic_core_fields"] = required
        record["audit"]["missing_core_fields"] = missing
        record["audit"]["projection_completeness"] = (
            "raw_and_semantic_core_complete" if not missing else "raw_complete_semantic_partial"
        )
        accounts.append(record)
    return accounts


def _reconcile_account_institutions(accounts: list[dict[str, Any]], inquiries: list[dict[str, Any]]) -> None:
    references = sorted(
        {
            str(item.get("institution") or "").strip()
            for item in inquiries
            if isinstance(item, dict) and len(str(item.get("institution") or "").strip()) >= 6
        }
    )
    for account in accounts:
        current = str(account.get("management_institution") or "").strip()
        if not current or current in references:
            continue
        scored = sorted(
            (
                SequenceMatcher(None, current, candidate).ratio(),
                candidate,
            )
            for candidate in references
        )
        if not scored or scored[-1][0] < 0.92:
            continue
        score, resolved = scored[-1]
        account["management_institution_raw"] = current
        account["management_institution"] = resolved
        account.setdefault("audit", {})["institution_reconciliation"] = {
            "source": "scanned_query_table",
            "similarity": round(score, 4),
        }


def extract_scanned_credit_business(parse_result: Any, full_text: str) -> dict[str, Any]:
    """Extract scanned-only collections that are not covered by native prose."""
    profile, residences, employments = _extract_profile(parse_result)
    inquiries = _extract_inquiries(parse_result)
    accounts = extract_scanned_credit_accounts(parse_result)
    _reconcile_account_institutions(accounts, inquiries)
    account_count = _reported_account_count(full_text, parse_result)
    summary = {"source": "scanned_credit_report"}
    if account_count is not None:
        summary["reported_account_count"] = account_count
    return {
        "subject_profile": profile,
        "residence_records": residences,
        "employment_records": employments,
        "inquiry_records": inquiries,
        "repayment_liability_records": _extract_section_records(parse_result, "相关还款责任信息", "credit_liability"),
        "statements": _section_notes(parse_result, "本人声明", "credit_statement"),
        "annotations": _section_notes(parse_result, "异议标注", "credit_annotation"),
        "credit_summary": summary,
        "credit_accounts": accounts,
    }


def link_repayment_records_to_accounts(
    repayment_records: list[dict[str, Any]],
    credit_accounts: list[dict[str, Any]],
    micro_grids: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach each repayment grid to the nearest preceding account card."""
    grids = {str(grid.get("grid_id") or ""): grid for grid in micro_grids if isinstance(grid, dict)}
    accounts_by_page: dict[int, list[dict[str, Any]]] = {}
    for account in credit_accounts:
        if isinstance(account, dict):
            accounts_by_page.setdefault(int(account.get("page") or 0), []).append(account)
    out: list[dict[str, Any]] = []
    for record in repayment_records:
        item = dict(record)
        if item.get("account_id"):
            out.append(item)
            continue
        refs = item.get("source_cell_refs") if isinstance(item.get("source_cell_refs"), list) else []
        first_ref = refs[0] if refs and isinstance(refs[0], dict) else {}
        grid_id = str(first_ref.get("grid_id") or item.get("grid_id") or "")
        grid = grids.get(grid_id, {})
        page = int(grid.get("page") or first_ref.get("page") or 0)
        grid_bbox = grid.get("bbox") if isinstance(grid.get("bbox"), list) else [0, 0, 0, 0]
        grid_y = float(grid_bbox[1]) if len(grid_bbox) == 4 else 0.0
        current = accounts_by_page.get(page) or []
        preceding = [
            account
            for account in current
            if isinstance(account.get("bbox"), list)
            and len(account["bbox"]) == 4
            and float(account["bbox"][3]) <= grid_y + 8.0
        ]
        previous = accounts_by_page.get(page - 1) or []
        if preceding or previous:
            selected = max(preceding, key=lambda account: float(account["bbox"][3])) if preceding else previous[-1]
            item["account_id"] = selected.get("account_id")
        out.append(item)
    return out


__all__ = [
    "extract_scanned_credit_accounts",
    "extract_scanned_credit_business",
    "link_repayment_records_to_accounts",
]
