"""Sealed read view to generic ProjectionData derivation.

Maps canonical evidence into domain facts using heuristic column
typing, value standardization, identity discovery, text KV, outline, source
metadata, and repeated-row recovery fallbacks.

It uses deterministic local rules and no external models.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from docmirror.ocr.correction.validators import (
    validate_cn_resident_id,
    validate_date_text,
    validate_phone_text,
)
from docmirror.plugins._base.standardizer import normalize_amount, normalize_timestamp

_GENERIC_WARNING = "community_generic_fallback"

# ── Column type detection ───────────────────────────────────────────────────

_DATE_RE = re.compile(r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?$")
_DATETIME_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
_AMOUNT_RE = re.compile(r"^[-+]?[¥￥$€£]?[\d,]+\.?\d{0,2}$")
_PCT_RE = re.compile(r"^\d+\.?\d*%$")
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_ID_NUM_RE = re.compile(r"^\d{17}[\dXx]$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_ACCOUNT_RE = re.compile(r"^\d{15,19}$")
_COMPACT_DATE_RE = re.compile(r"^(?:19|20)\d{6}$")
_PERCENTAGE_RE = re.compile(r"^[-+]?\d+(?:\.\d+)?%$")
_CHAPTER_LABEL_RE = re.compile(r"^第.{1,20}[章节条编款项]$")
_PLACEHOLDER_HEADER_RE = re.compile(r"^(?:col(?:umn)?|字段|列)[_\s-]*\d+$", re.IGNORECASE)

_TEXT_KV_STRONG_SUFFIXES = (
    "名称",
    "姓名",
    "代表人",
    "负责人",
    "联系人",
    "代码",
    "号码",
    "编号",
    "单号",
    "户号",
    "证号",
    "识别号",
    "单元号",
    "地址",
    "范围",
    "日期",
    "时间",
    "期间",
    "金额",
    "余额",
    "币种",
    "单位",
    "比例",
    "税率",
    "类型",
    "状态",
    "意见",
    "备注",
    "说明",
    "标题",
    "主题",
    "机构",
    "部门",
    "账户",
    "账号",
    "电话",
    "邮箱",
    "用途",
    "事由",
    "期限",
    "资本",
    "网址",
    "邮编",
    "邮政编码",
    "文号",
    "序号",
)
_TEXT_KV_CLAUSE_KEYS = {"为", "是", "有", "其中", "加", "减", "如下", "分别", "除"}
_TEXT_KV_CLAUSE_ENDINGS = ("进行处理", "予以确认", "确认为", "包括", "如下")
_SECTION_HEADING_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^[一二三四五六七八九十百]{1,4}[、.．]\s*\S.{0,50}$"), "h1"),
    (re.compile(r"^[（(][一二三四五六七八九十百\d]{1,4}[）)]\s*\S.{0,50}$"), "h2"),
    (re.compile(r"^\d{1,2}[、.．]\s*[^\d\s].{0,50}$"), "h2"),
)
_SECTION_MARKER_ONLY_RE = re.compile(r"^(?:[一二三四五六七八九十百]{1,4}|\d{1,2})[、.．]$")
_TABLE_SECTION_METRIC_ENDINGS = (
    "余额",
    "金额",
    "账面价值",
    "账面原值",
    "累计折旧",
    "累计摊销",
    "减值准备",
    "增加",
    "减少",
    "计提",
    "处置",
    "合计",
    "其他",
)
_OCR_LONG_VALUE_SUFFIXES = ("经营范围", "业务范围", "经营内容", "备注", "说明")
_PERSON_FIELD_SUFFIXES = ("姓名", "代表人", "负责人", "联系人")
_AUDIT_REPORT_NUMBER_RE = re.compile(r"(?P<number>[\u3400-\u9fff]{1,12}字[（(]\d{4}[）)]第?[0-9A-Za-z-]{4,32}号)")

_CURRENCY_SYMBOLS = {"¥": "CNY", "$": "USD", "€": "EUR", "£": "GBP", "￥": "CNY"}

_INTERNAL_ENTITY_KEYS = frozenset(
    {
        "canonical_document_type",
        "extractor_scene_hint",
        "extractor_scene_confidence",
        "pre_analyzer_scene_hint",
        "pre_analyzer_scene_confidence",
        "structural_anomaly_report",
        "classification_provenance",
        "classification_source",
        "document_scene_refined",
        "layout_profile_id",
        "layout_profile_id_refined",
        "layout_profile_refine_confidence",
        "mirror_expected_data_rows",
        "mirror_ltqg_enabled",
        "source_file_name",
        "extracted_entities",
        "step_timings",
        "page_evidence_bundles",
        "local_structure_evidence",
        "scanned_ocr_evidence",
        "columns",
        "document_flow",
        "line_items",
        "notes",
        "records",
        "summary",
    }
)
_TEXT_KV_RE = re.compile(r"^\s*([^:：]{1,40})\s*[:：]\s*(\S.{0,499}|\S)\s*$")
_ID_CARD_LABEL_RE = re.compile(r"姓名|性别|民族|出生(?:日期)?|住址|公民身份号码|身份证号码|身份证号")
_ID_CARD_FIELD_BY_LABEL = {
    "姓名": "name",
    "性别": "gender",
    "民族": "ethnicity",
    "出生": "birth_date",
    "出生日期": "birth_date",
    "住址": "address",
    "公民身份号码": "id_number",
    "身份证号码": "id_number",
    "身份证号": "id_number",
}

ColumnType = str


def _nfkc(value: Any) -> str:
    """Normalize OCR-width variants without changing business semantics."""
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _clean_label(value: Any) -> str:
    """Return a stable display label while preserving the source language."""
    return re.sub(r"\s+", " ", _nfkc(value)).strip(" \t:：")


def _normalize_section_title(value: Any) -> str:
    """Normalize layout-only whitespace after a numbered heading marker."""
    title = _clean_label(value)
    return re.sub(r"^((?:[一二三四五六七八九十百]{1,4}|\d{1,2})[、.．])\s+", r"\1", title)


def _valid_normalized_timestamp(value: str) -> str:
    """Normalize a timestamp only when the normalized result is a real date."""
    normalized = normalize_timestamp(_nfkc(value))
    if not normalized:
        return ""
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return normalized


def _is_valid_date_value(value: str) -> bool:
    text = _nfkc(value)
    return validate_date_text(text) or bool(_COMPACT_DATE_RE.fullmatch(text) and _valid_normalized_timestamp(text))


def _is_valid_datetime_value(value: str) -> bool:
    text = _nfkc(value)
    return bool(re.search(r"\d{1,2}:\d{2}", text) and _valid_normalized_timestamp(text))


def _is_valid_time_value(value: str) -> bool:
    text = _nfkc(value)
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def _normalize_phone_value(value: str, *, header_confirmed: bool = False) -> str:
    text = _nfkc(value)
    if not validate_phone_text(text):
        return ""
    digits = re.sub(r"\D", "", text)
    if not 6 <= len(digits) <= 15:
        return ""
    if text.startswith("+"):
        return f"+{digits}"
    if re.fullmatch(r"1[3-9]\d{9}", digits):
        return digits
    return digits if header_confirmed or re.search(r"[ ()-]", text) else ""


def _currency_from_text(value: str) -> str | None:
    text = _nfkc(value).upper()
    markers = (
        ("USD", ("$", "USD", "美元")),
        ("EUR", ("€", "EUR", "欧元")),
        ("GBP", ("£", "GBP", "英镑")),
        ("CNY", ("¥", "￥", "CNY", "RMB", "人民币", "元", "圆")),
    )
    return next((currency for currency, values in markers if any(value in text for value in values)), None)


def _normalize_amount_value(value: str) -> float | None:
    """Parse a generic amount without inventing its currency."""
    text = _nfkc(value)
    negative_parentheses = text.startswith("(") and text.endswith(")")
    if negative_parentheses:
        text = text[1:-1].strip()
    text = re.sub(r"(?i)\b(?:CNY|RMB|USD|EUR|GBP)\b", "", text)
    text = re.sub(r"(?:人民币|美元|欧元|英镑)", "", text)
    # A frequent scan error replaces the final thousands separator with a
    # decimal point (``127,500.000.00``). Repair only the unambiguous shape:
    # grouped thousands followed by exactly one two-digit decimal part. Raw
    # record text remains untouched; this affects only ``normalized`` values.
    malformed_grouped = re.fullmatch(
        r"(?P<sign>[-+]?)"
        r"(?P<head>\d{1,3}(?:,\d{3})*)\."
        r"(?P<thousands>\d{3})\."
        r"(?P<decimal>\d{2})",
        text.replace("，", ",").strip(),
    )
    if malformed_grouped:
        text = (
            f"{malformed_grouped.group('sign')}"
            f"{malformed_grouped.group('head')},"
            f"{malformed_grouped.group('thousands')}."
            f"{malformed_grouped.group('decimal')}"
        )
    normalized = normalize_amount(text)
    if normalized is None:
        return None
    return -abs(normalized) if negative_parentheses else normalized


_HEADER_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("percentage", ("百分比", "比例", "占比", "税率", "rate", "ratio", "percent", "%")),
    ("phone", ("联系电话", "移动电话", "手机号", "手机", "电话", "phone", "mobile", "tel")),
    ("id_number", ("身份证", "证件号", "证件号码", "信用代码", "税号", "id number", "subject id")),
    (
        "identifier",
        (
            "编号",
            "单号",
            "序号",
            "代码",
            "流水号",
            "订单号",
            "合同号",
            "户号",
            "证号",
            "识别号",
            "单元号",
            "invoice no",
            "code",
            "number",
            "no",
        ),
    ),
    (
        "amount",
        (
            "交易金额",
            "金额",
            "合计",
            "总额",
            "数额",
            "余额",
            "价格",
            "单价",
            "税额",
            "保费",
            "保额",
            "赔款",
            "工资",
            "薪资",
            "薪酬",
            "费用",
            "利息",
            "本金",
            "租金",
            "收入",
            "支出",
            "成本",
            "利润",
            "税款",
            "市值",
            "净值",
            "amount",
            "total",
            "price",
            "balance",
        ),
    ),
    ("account", ("银行账号", "银行卡号", "账户", "账号", "卡号", "account")),
    ("datetime", ("日期时间", "交易时间", "发生时间", "timestamp", "datetime")),
    ("date", ("交易日期", "发生日期", "日期", "date")),
    ("time", ("时刻", "时间", "time")),
    ("email", ("电子邮箱", "邮箱", "email", "e-mail")),
)


def _generic_header_hint(header: str) -> str:
    label = _clean_label(header).casefold()
    # A unit declaration describes the values around a table; it is not itself
    # an amount column.  Treating ``金额单位:人民币元`` as an amount header
    # creates false normalization and unknown-currency warnings.
    if re.search(r"(?:金额|货币|币种)单位|(?:单位|币种)\s*[:：]", label):
        return ""
    padded = f" {re.sub(r'[_/-]+', ' ', label)} "
    for kind, keywords in _HEADER_HINTS:
        for keyword in keywords:
            needle = keyword.casefold()
            if any("\u3400" <= char <= "\u9fff" for char in needle) or needle == "%":
                if needle in label:
                    return kind
            elif f" {needle} " in padded or label == needle:
                return kind
    return ""


def _matches_generic_type(value: str, kind: str, *, header_confirmed: bool = False) -> bool:
    text = _nfkc(value)
    if kind == "datetime":
        return _is_valid_datetime_value(text)
    if kind == "date":
        return _is_valid_date_value(text)
    if kind == "time":
        return _is_valid_time_value(text)
    if kind == "percentage":
        return bool(_PERCENTAGE_RE.fullmatch(text))
    if kind == "phone":
        return bool(_normalize_phone_value(text, header_confirmed=header_confirmed))
    if kind == "email":
        return bool(_EMAIL_RE.fullmatch(text))
    if kind == "id_number":
        compact = re.sub(r"[\s-]+", "", text).upper()
        pattern = r"(?:\d{15}|\d{17}[\dX]|[0-9A-Z]{18})" if header_confirmed else r"\d{17}[\dX]"
        return bool(re.fullmatch(pattern, compact))
    if kind == "account":
        compact = re.sub(r"[\s-]+", "", text)
        return bool(re.fullmatch(r"[0-9A-Z]{8,34}", compact, re.IGNORECASE))
    if kind == "amount":
        digits = re.sub(r"\D", "", text)
        if not header_confirmed and len(digits) >= 12 and not (_currency_from_text(text) or re.search(r"[.,]", text)):
            return False
        return _normalize_amount_value(text) is not None
    return False


def _infer_generic_type(header: str, values: list[str]) -> tuple[ColumnType, float]:
    """Infer a Generic column using header semantics plus validated values."""
    sample = [_nfkc(value) for value in values[:50] if _nfkc(value) not in {"", "-", "—"}]
    if not sample:
        return ("text", 0.0)
    hint = _generic_header_hint(header)
    if hint == "identifier":
        return ("text", 0.95)
    if hint:
        match_count = sum(_matches_generic_type(value, hint, header_confirmed=True) for value in sample)
        ratio = match_count / len(sample)
        factor = 1.0 if len(sample) >= 3 else 0.9 if len(sample) == 2 else 0.85
        if hint == "amount" and match_count >= 3 and ratio >= 0.35:
            return (hint, round(ratio * factor, 4))
        return (hint, round(ratio * factor, 4)) if ratio >= 0.6 else ("text", round(ratio, 4))
    candidates = ("datetime", "date", "time", "percentage", "phone", "email", "id_number", "amount")
    counts = {kind: sum(_matches_generic_type(value, kind) for value in sample) for kind in candidates}
    best_type = max(counts, key=counts.get)
    ratio = counts[best_type] / len(sample)
    factor = 1.0 if len(sample) >= 3 else 0.75 if len(sample) == 2 else 0.55
    confidence = ratio * factor
    return (best_type, round(confidence, 4)) if ratio >= 0.6 and confidence >= 0.6 else ("text", round(confidence, 4))


def _type_detect_column(values: list[str]) -> tuple[ColumnType, float]:
    """Infer column type from its values using pattern voting.

    Samples up to 50 values for performance. Returns (type, confidence).
    If confidence < 0.6, returns ("text", confidence).
    """
    if not values:
        return ("text", 0.0)

    sample = [v.strip() for v in values[:50] if v and v.strip() and v not in ("-", "—")]

    if not sample:
        return ("text", 0.0)

    counts: dict[str, int] = {
        "datetime": 0,
        "date": 0,
        "time": 0,
        "amount": 0,
        "percentage": 0,
        "phone": 0,
        "id_number": 0,
        "account": 0,
        "email": 0,
        "text": 0,
    }

    for val in sample:
        matched = False
        for pattern_name, regex in [
            ("datetime", _DATETIME_RE),
            ("date", _DATE_RE),
            ("time", _TIME_RE),
            ("percentage", _PCT_RE),
            ("phone", _PHONE_RE),
            ("email", _EMAIL_RE),
            ("id_number", _ID_NUM_RE),
            ("account", _ACCOUNT_RE),
        ]:
            if regex.match(val):
                counts[pattern_name] += 1
                matched = True
                break
        if not matched and _AMOUNT_RE.match(val):
            counts["amount"] += 1
            matched = True
        if not matched:
            counts["text"] += 1

    total_matched = sum(counts.values())
    if total_matched == 0:
        return ("text", 0.0)

    best_type = max(counts, key=counts.get)
    confidence = counts[best_type] / total_matched
    if confidence < 0.6:
        return ("text", confidence)
    return (best_type, confidence)


def _standardize_value(
    raw: str,
    col_type: str,
    *,
    currency_hint: str | None = None,
) -> str | dict[str, Any]:
    """Standardize a single value based on its detected column type."""
    cleaned = _nfkc(raw)
    if not cleaned:
        return cleaned

    if col_type == "amount":
        currency = _currency_from_text(cleaned) or (
            currency_hint if currency_hint in {"CNY", "USD", "EUR", "GBP"} else None
        )
        normalized = _normalize_amount_value(cleaned)
        if normalized is not None:
            value: dict[str, Any] = {"value": normalized}
            if currency:
                value["currency"] = currency
            return value
        return cleaned

    if col_type in ("date", "datetime"):
        normalized = _valid_normalized_timestamp(cleaned)
        if normalized:
            if col_type == "date":
                return {"value": normalized.split("T", 1)[0]}
            return {"value": normalized}
        return cleaned

    if col_type == "percentage":
        try:
            pct_val = float(cleaned.replace("%", "").strip())
            return {"value": pct_val, "unit": "%"}
        except (ValueError, TypeError):
            pass

    if col_type == "phone":
        normalized_phone = _normalize_phone_value(cleaned, header_confirmed=True)
        if normalized_phone:
            return {"value": normalized_phone}
        return cleaned

    return cleaned


def _infer_column_types(
    tables: list[Any],
) -> dict[str, dict[str, Any]]:
    """Run column type detection on all tables."""
    col_values: dict[str, list[str]] = {}
    for table in tables:
        headers, entries, _header_repaired = _project_table_rows(table)
        for _row_index, _row, cells in entries:
            for h, c in zip(headers, cells):
                key = str(h).strip()
                if key not in col_values:
                    col_values[key] = []
                col_values[key].append(str(c))

    result: dict[str, dict[str, Any]] = {}
    for header, values in col_values.items():
        col_type, confidence = _infer_generic_type(header, values)
        null_count = sum(1 for v in values if not v.strip())
        result[header] = {
            "type": col_type,
            "confidence": round(confidence, 3),
            "null_ratio": round(null_count / max(1, len(values)), 3),
        }
    return result


def _infer_table_column_types(
    table_views: list[tuple[Any, list[int], str]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Infer columns per source table while keeping the public aggregate unchanged."""
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for table_index, (table, _source_pages, _table_kind) in enumerate(table_views):
        table_id = str(getattr(table, "logical_id", "") or getattr(table, "table_id", "") or f"table_{table_index}")
        headers, entries, _header_repaired = _project_table_rows(table)
        values: dict[str, list[str]] = {header: [] for header in headers}
        for _row_index, _row, cells in entries:
            for header, cell in zip(headers, cells):
                values.setdefault(header, []).append(str(cell or ""))
        table_columns: dict[str, dict[str, Any]] = {}
        for header, samples in values.items():
            column_type, confidence = _infer_generic_type(header, samples)
            table_columns[header] = {
                "type": column_type,
                "confidence": round(confidence, 3),
                "null_ratio": round(
                    sum(1 for value in samples if not value.strip()) / max(1, len(samples)),
                    3,
                ),
            }
        result[table_id] = table_columns
    return result


def _infer_record_column_types(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Infer columns from standard records when source tables have no headers."""
    values: dict[str, list[str]] = {}
    for record in records:
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        for key, value in raw.items():
            values.setdefault(str(key), []).append(str(value or ""))
    columns: dict[str, dict[str, Any]] = {}
    for key, samples in values.items():
        column_type, confidence = _infer_generic_type(key, samples)
        columns[key] = {
            "type": column_type,
            "confidence": round(confidence, 3),
            "null_ratio": round(sum(1 for value in samples if not value.strip()) / max(1, len(samples)), 3),
        }
    return columns


def _build_normalized_record(
    raw: dict[str, str],
    col_types: dict[str, dict[str, Any]],
    *,
    currency_hint: str | None = None,
) -> dict[str, Any]:
    """Build the ``normalized`` block for a single record."""
    normalized: dict[str, Any] = {}
    for key, raw_val in raw.items():
        col_info = col_types.get(key, {})
        col_type = col_info.get("type", "text")
        if col_type == "text":
            normalized[key] = raw_val
        else:
            normalized[key] = _standardize_value(raw_val, col_type, currency_hint=currency_hint)
    return normalized


def _normalize_headers(headers: list[Any], column_count: int) -> tuple[list[str], bool]:
    """Build deterministic, unique headers so dictionary projection never drops cells."""
    normalized: list[str] = []
    used: set[str] = set()
    repaired = len(headers) != column_count
    for index in range(column_count):
        base = _clean_label(headers[index]) if index < len(headers) else ""
        compact = re.sub(r"\s+", "", base)
        spaced_parts = base.split()
        if (
            base != compact
            and compact
            and len(spaced_parts) > 1
            and all(len(part) == 1 for part in spaced_parts)
            and re.fullmatch(r"[㐀-鿿\d()（）/%·:：、.．-]+", compact)
        ):
            # PDF text positioning often inserts layout-only gaps inside short
            # Chinese labels (for example ``项 目`` or ``账 龄``).
            # Normalize business column names while leaving source cells and
            # the Canonical reading view untouched.
            base = compact
        if not base:
            base = f"col_{index}"
            repaired = True
        elif _PLACEHOLDER_HEADER_RE.fullmatch(base):
            repaired = True
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
            repaired = True
        used.add(candidate)
        normalized.append(candidate)
    return normalized, repaired


def _row_cell_texts(row: Any) -> list[str]:
    return [str(getattr(cell, "text", cell) or "") for cell in getattr(row, "cells", []) or []]


_TABLE_HEADER_LABEL_RE = re.compile(
    r"项目|名称|序号|类别|类型|性质|账龄|比例|余额|金额|账面|年初|年末|期初|期末|"
    r"本期|上期|本年|上年|数量|单价|日期|说明|备注|准备|增加|减少|计提|转回|核销|合计|"
    r"公司名称|注册地|经营地|业务性质|持股比例|表决权比例|直接|间接|取得方式|"
    r"关联方|关系|出租方|承租方|税种|税率|折旧方法|折旧年限|残值率|折旧率|"
    r"形成原因|折算汇率|外币余额|人民币余额|收入|成本"
)


def _embedded_amount_count(value: Any) -> int:
    """Count amount-shaped fragments without treating section numbers as data."""
    text = _nfkc(value)
    return len(
        re.findall(
            r"(?<![\dA-Za-z])[-+]?(?:\d{1,3}(?:[,，]\d{3})+|\d+\.\d{2,})(?![\dA-Za-z])",
            text,
        )
    )


def _semantic_table_header_label(value: Any) -> str:
    """Return a semantic label, stripping an OCR-merged trailing amount."""
    label = _clean_label(value)
    compact = re.sub(r"\s+", "", label)
    if compact in {"项", "目", "目项", "项目"}:
        return "项目"
    if re.search(r"(?:金额|货币|币种)单位", compact):
        return ""
    if _embedded_amount_count(label) >= 2:
        return ""
    # OCR grids occasionally merge a header with several data cells.  Such a
    # value is evidence of a damaged row, not a safe column name.
    if len(compact) > 24 or (compact.startswith("项目") and len(compact) > 8):
        return ""
    if compact.startswith("公司名称") and re.search(r"公司|企业|集团", compact[4:]):
        return ""
    if compact.startswith("业务性质") and len(compact) > 10:
        return ""
    if compact.startswith("税种") and len(compact) > 8:
        return ""
    amount_suffix = re.search(
        r"\s+[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2,})?"
        r"(?:\s+[-+]?\d[\d,.]*)*\s*$",
        label,
    )
    if amount_suffix:
        prefix = label[: amount_suffix.start()].strip()
        if _TABLE_HEADER_LABEL_RE.search(prefix):
            label = prefix
    return label if _TABLE_HEADER_LABEL_RE.search(label) else ""


def _infer_scanned_table_headers(table: Any, rows: list[Any], column_count: int) -> tuple[list[str], int]:
    """Promote one to three label rows from OCR bordered grids into semantic headers."""
    metadata = getattr(table, "metadata", None) or {}
    source = str(metadata.get("source") or "")
    layer = str(getattr(table, "extraction_layer", "") or metadata.get("extraction_layer") or "")
    first_labels = [_clean_label(value) for value in (_row_cell_texts(rows[0]) if rows else []) if _clean_label(value)]
    semantic_header_count = sum(bool(_semantic_table_header_label(value)) for value in first_labels)
    second_semantic_header_count = sum(
        bool(_semantic_table_header_label(value)) for value in (_row_cell_texts(rows[1]) if len(rows) > 1 else [])
    )
    sparse_parent_then_headers = bool(
        semantic_header_count == 1
        and any(re.search(r"余额|金额|本期|上期|本年|上年|期初|期末|年初|年末", value) for value in first_labels)
        and second_semantic_header_count >= 2
    )
    scanned_source = source == "scanned_bordered_table_reconstructor" or layer == "scanned_image_line_grid"
    # Logical-table assembly does not retain the physical OCR source metadata.
    # In that case require at least two explicit header labels before promotion.
    if not scanned_source and semantic_header_count < 2 and not sparse_parent_then_headers:
        return [], 0

    header_rows: list[list[str]] = []
    for header_row_index, row in enumerate(rows[:3]):
        cells = list(getattr(row, "cells", []) or [])
        values = _row_cell_texts(row)
        nonempty = [_clean_label(value) for value in values if _clean_label(value)]
        if not nonempty:
            continue
        if any(_embedded_amount_count(value) >= 2 for value in nonempty):
            if not header_rows:
                return [], 0
            break
        numeric_count = sum(
            _normalize_amount_value(value) is not None
            or bool(re.search(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+\.\d{2,})(?!\d)", value))
            for value in nonempty
        )
        semantic_labels = [_semantic_table_header_label(value) for value in values]
        semantic_count = sum(bool(value) for value in semantic_labels)
        # A numeric-looking last row is commonly a vertically merged
        # header+data row.  Promoting it would erase the table's only record.
        if numeric_count and header_row_index >= len(rows) - 1:
            break
        if numeric_count and sum(bool(value) for value in semantic_labels) < 2:
            break
        sparse_group_parent = bool(
            not header_rows
            and semantic_count == 1
            and any(
                re.search(r"余额|金额|本期|上期|本年|上年|期初|期末|年初|年末", value)
                for value in semantic_labels
                if value
            )
        )
        if not header_rows and semantic_count < 2 and not sparse_group_parent:
            return [], 0
        expanded = ["" for _ in range(column_count)]
        for column, cell in enumerate(cells[:column_count]):
            label = semantic_labels[column]
            if not label:
                continue
            span = max(1, int(getattr(cell, "col_span", 1) or 1))
            for target in range(column, min(column_count, column + span)):
                expanded[target] = label
        header_rows.append(expanded)
        if numeric_count:
            break
    if not header_rows:
        return [], 0

    if len(header_rows) >= 2:
        parent_row, child_row = header_rows[0], header_rows[1]
        child_columns = [index for index, value in enumerate(child_row) if value and value != "项目"]
        for parent_column, parent in enumerate(parent_row):
            if (
                parent
                and re.search(r"余额|金额|本期|上期|本年|上年|期初|期末|年初|年末", parent)
                and len(child_columns) >= 2
                and min(child_columns) <= parent_column <= max(child_columns)
            ):
                for target in range(min(child_columns), max(child_columns) + 1):
                    parent_row[target] = parent

    parts: list[list[str]] = [[] for _ in range(column_count)]
    for row in header_rows:
        for column, label in enumerate(row):
            if not label:
                continue
            if label not in parts[column]:
                parts[column].append(label)
    headers = ["/".join(values) for values in parts]
    covered = sum(bool(header) for header in headers)
    semantic = sum(
        bool(re.search(r"[A-Za-z\u3400-\u9fff]", header)) and _normalize_amount_value(header) is None
        for header in headers
    )
    unique = len({header for header in headers if header})
    if covered / max(1, column_count) < 0.5 or semantic < 2 or unique < 2:
        return [], 0
    return headers, len(header_rows)


def _infer_first_label_header(headers: list[str], entries: list[tuple[int, Any, list[str]]]) -> list[str]:
    """Replace only an evidence-backed first placeholder with ``项目``.

    Financial and operational tables often lose the top-left label while the
    numeric column labels survive.  Requiring several text labels in column 0
    plus numeric evidence elsewhere keeps this repair generic and conservative.
    """
    if not headers or not _PLACEHOLDER_HEADER_RE.fullmatch(_clean_label(headers[0])):
        return headers
    first_values = [_clean_label(cells[0]) for _row_index, _row, cells in entries if cells and _clean_label(cells[0])]
    if len(first_values) < 2:
        return headers
    label_values = [
        value
        for value in first_values
        if _normalize_amount_value(value) is None and bool(re.search(r"[A-Za-z\u3400-\u9fff]", value))
    ]
    if len(label_values) / len(first_values) < 0.67:
        return headers

    numeric_evidence = False
    for column in range(1, len(headers)):
        values = [
            _clean_label(cells[column])
            for _row_index, _row, cells in entries
            if column < len(cells) and _clean_label(cells[column])
        ]
        if values and sum(_normalize_amount_value(value) is not None for value in values) / len(values) >= 0.6:
            numeric_evidence = True
            break
        header = _clean_label(headers[column])
        if not _PLACEHOLDER_HEADER_RE.fullmatch(header) and re.search(
            r"金额|余额|发生额|账面|比例|数量|单价|收入|成本|利润|费用", header
        ):
            numeric_evidence = True
            break
    if not numeric_evidence or "项目" in headers:
        return headers
    repaired = list(headers)
    repaired[0] = "项目"
    return repaired


def _trim_trailing_statement_noise(
    entries: list[tuple[int, Any, list[str]]], headers: list[str]
) -> list[tuple[int, Any, list[str]]]:
    """Remove signatures and seals captured below a completed financial statement."""
    if "项目" not in headers or not any(
        any(marker in header for marker in ("余额", "金额", "发生额")) for header in headers
    ):
        return entries
    total_re = re.compile(r"^(?:资产总计|负债和所有者权益(?:或股东权益)?总计|期末现金及现金等价物余额)$")
    total_index = next(
        (
            index
            for index in range(len(entries) - 1, -1, -1)
            if entries[index][2] and total_re.fullmatch(_clean_label(entries[index][2][0]))
        ),
        None,
    )
    if total_index is None or total_index == len(entries) - 1:
        return entries
    trailing = entries[total_index + 1 :]
    has_amount = any(
        _normalize_amount_value(value) is not None
        for _row_index, _row, cells in trailing
        for value in cells[1:]
        if _clean_label(value)
    )
    trailing_text = " ".join(value for _index, _row, cells in trailing for value in cells)
    if not has_amount and re.search(r"负责人|会计机构|主管会计|签名|签章|印章", trailing_text):
        return entries[: total_index + 1]
    return entries


def _project_table_rows(table: Any) -> tuple[list[str], list[tuple[int, Any, list[str]]], bool]:
    rows = list(getattr(table, "rows", []) or [])
    source_headers = list(getattr(table, "headers", None) or [])
    column_count = max(
        len(source_headers),
        max((len(getattr(row, "cells", []) or []) for row in rows), default=0),
    )
    inferred_header_rows = 0
    if not source_headers and column_count:
        inferred, inferred_header_rows = _infer_scanned_table_headers(table, rows, column_count)
        if inferred:
            source_headers = inferred
    headers, header_repaired = _normalize_headers(source_headers, column_count)
    entries: list[tuple[int, Any, list[str]]] = []
    for row_index, row in enumerate(rows):
        if row_index < inferred_header_rows:
            continue
        cells = _row_cell_texts(row)
        if not any(value.strip() for value in cells):
            continue
        if _is_repeated_header_row(cells, headers) or _is_embedded_header_row(cells, headers):
            continue
        entries.append((row_index, row, cells))
    headers = _infer_first_label_header(headers, entries)
    return headers, _trim_trailing_statement_noise(entries, headers), header_repaired


def _is_repeated_header_row(cells: list[str], headers: list[str]) -> bool:
    return bool(
        headers
        and len(cells) == len(headers)
        and all(_clean_label(cell).casefold() == header.casefold() for cell, header in zip(cells, headers))
    )


def _is_embedded_header_row(cells: list[str], headers: list[str]) -> bool:
    """Reject a repeated multi-cell header even when PDF extraction merged cells."""
    nonempty = [_clean_label(cell) for cell in cells if _clean_label(cell)]
    labels = [
        _clean_label(header)
        for header in headers
        if _clean_label(header) and not _PLACEHOLDER_HEADER_RE.fullmatch(_clean_label(header))
    ]
    if len(nonempty) < 2 or len(labels) < 2:
        return False
    if any(_normalize_amount_value(value) is not None for value in nonempty):
        return False
    joined = "".join(nonempty).casefold()
    return sum(label.casefold() in joined for label in dict.fromkeys(labels)) >= 2


def _looks_like_typed_candidate(value: Any, column_type: str) -> bool:
    """Return whether a raw value plausibly attempts the inferred scalar type."""
    text = _nfkc(value)
    if not text:
        return False
    if column_type == "amount":
        return bool(re.search(r"\d|[¥￥$€£]", text))
    if column_type in {"date", "datetime", "percentage"}:
        return bool(re.search(r"\d", text) or (column_type == "percentage" and "%" in text))
    if column_type == "phone":
        return len(re.sub(r"\D", "", text)) >= 6
    return True


def _chinese_section_number(value: str) -> int:
    """Parse the compact Chinese numerals commonly used by report headings."""
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    text = _nfkc(value)
    if text == "十":
        return 10
    if "十" in text:
        left, right = text.split("十", 1)
        return (digits.get(left, 1) * 10) + digits.get(right, 0)
    return digits.get(text, 0)


def _is_public_field(key: Any, value: Any) -> bool:
    """Keep business facts out of parser/runtime implementation metadata."""
    name = str(key or "").strip()
    if (
        not name
        or name.startswith(("_", "mirror_"))
        or name in _INTERNAL_ENTITY_KEYS
        or (len(name) > 8 and re.match(r"^\d+\s*", name))
    ):
        return False
    if value in (None, ""):
        return False
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return len(value) <= 20 and all(isinstance(item, (str, int, float, bool)) for item in value)
    if isinstance(value, dict):
        return len(value) <= 20 and all(
            isinstance(item, (str, int, float, bool, type(None))) for item in value.values()
        )
    return False


def _collect_text_key_values(full_text: str) -> dict[str, str]:
    """Conservatively recover label/value lines when adapters emitted no KV object."""
    fields, _metadata = _collect_text_key_value_facts(full_text)
    return fields


def _clean_text_kv_value(value: Any) -> str:
    """Clean transport punctuation around a scalar text-KV value."""
    return _nfkc(value).rstrip(" \t;；")


def _looks_like_scalar_text_kv(key: str, value: str) -> bool:
    """Reject prose clauses and serialized table rows while preserving concise labels."""
    if not 2 <= len(key) <= 30 or key in _TEXT_KV_CLAUSE_KEYS:
        return False
    if "|" in key or "|" in value or re.search(r"[,，;；。！？?!]", key):
        return False
    if key.endswith(_TEXT_KV_CLAUSE_ENDINGS):
        return False
    if re.match(r"^[（(]?\d+(?:[）)、.]|\s+)", key) or (len(key) > 8 and re.match(r"^\d", key)):
        return False
    strong_label = bool(_generic_header_hint(key)) or key.endswith(_TEXT_KV_STRONG_SUFFIXES)
    list_like_value = (
        bool(re.match(r"^(?:[（(]?\d{1,3}[）)]|\d{1,3}[、．]|\d{1,3}\.(?!\d))\s*\S", value)) or ";" in value
    )
    if list_like_value and not strong_label:
        return False
    return True


def _looks_like_ocr_field(key: str, value: Any) -> bool:
    """Keep only conservative scalar facts from OCR-derived generic entities."""
    text = _clean_text_kv_value(value)
    if not _looks_like_scalar_text_kv(key, text):
        return False
    if re.match(r"^[（(]?\d", key) or key.endswith(("其中", " 加", " 减", "加", "减")):
        return False
    if len(key) > 20 and not key.endswith(_OCR_LONG_VALUE_SUFFIXES):
        return False
    hint = _generic_header_hint(key)
    strong_label = (
        key.endswith(_TEXT_KV_STRONG_SUFFIXES)
        or hint in {"phone", "id_number", "email", "date", "datetime", "time", "identifier", "account"}
        or (hint == "amount" and len(key) <= 12 and _normalize_amount_value(text) is not None)
    )
    if not strong_label:
        return False
    if key.endswith(("邮编", "邮政编码")) and (len(key) > 8 or re.search(r"\d", key)):
        return False
    if key.endswith(_PERSON_FIELD_SUFFIXES):
        compact = re.sub(r"\s+", "", text)
        if re.fullmatch(r"[\u3400-\u9fff]{2,8}", compact):
            return True
        if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,60}", text):
            return True
        return False
    if len(text) > 240 and not key.endswith(_OCR_LONG_VALUE_SUFFIXES):
        return False
    return True


def _drop_redundant_generic_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Remove a weaker duplicate unit label without altering its stronger fact."""
    retained = dict(fields)
    amount_unit = _nfkc(retained.get("金额单位"))
    unit = _nfkc(retained.get("单位"))
    if amount_unit and unit and len(unit) <= 8 and unit in amount_unit:
        retained.pop("单位", None)
    return retained


def _extend_ocr_long_fields(fields: dict[str, Any], parse_result: Any) -> dict[str, Any]:
    """Join immediately adjacent OCR lines for explicitly long scalar fields."""
    retained = dict(fields)
    for key, raw_value in list(retained.items()):
        if not isinstance(raw_value, str) or not key.endswith(_OCR_LONG_VALUE_SUFFIXES):
            continue
        value = _clean_text_kv_value(raw_value)
        if not value or value.endswith(("。", "；", ";", ")", "）")):
            continue
        for page in getattr(parse_result, "pages", []) or []:
            texts = list(getattr(page, "texts", []) or [])
            matched = False
            for text_index, text in enumerate(texts):
                content = _nfkc(getattr(text, "content", ""))
                match = re.match(rf"^{re.escape(key)}\s*[:：]\s*(.+)$", content)
                if not match or not value.startswith(_clean_text_kv_value(match.group(1))):
                    continue
                current_bbox = getattr(text, "bbox", None)
                if not current_bbox:
                    continue
                extended = value
                for following in texts[text_index + 1 : text_index + 4]:
                    following_content = _nfkc(getattr(following, "content", ""))
                    following_bbox = getattr(following, "bbox", None)
                    if not following_content or not following_bbox:
                        break
                    vertical_gap = float(following_bbox[1]) - float(current_bbox[3])
                    aligned = float(following_bbox[0]) <= float(current_bbox[0]) + 6.0
                    if not -2.0 <= vertical_gap <= 12.0 or not aligned:
                        break
                    if re.match(r"^[^:：]{2,20}[:：]", following_content) or any(
                        pattern.fullmatch(following_content) for pattern, _level in _SECTION_HEADING_PATTERNS
                    ):
                        break
                    extended += following_content
                    current_bbox = following_bbox
                    if following_content.endswith(("。", "；", ";", ")", "）")):
                        break
                if len(extended) > len(value):
                    retained[key] = extended[:500]
                matched = True
                break
            if matched:
                break
    return retained


def _deduplicate_similar_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Drop OCR label variants only when they carry the exact same scalar value."""
    retained: dict[str, Any] = {}
    scalar_keys_by_value: dict[str, list[str]] = {}
    for key, value in fields.items():
        if not isinstance(value, (str, int, float, bool)):
            retained[key] = value
            continue
        normalized_value = _nfkc(value).casefold()
        duplicate = any(
            SequenceMatcher(None, _clean_label(key), existing).ratio() >= 0.74
            for existing in scalar_keys_by_value.get(normalized_value, [])
        )
        if duplicate:
            continue
        retained[key] = value
        scalar_keys_by_value.setdefault(normalized_value, []).append(_clean_label(key))
    return retained


def _recover_audit_report_number(full_text: str) -> tuple[str, dict[str, Any]] | None:
    """Recover the formal audit document number without replacing QR report IDs."""
    for line_number, line in enumerate((full_text or "").splitlines()[:120], start=1):
        match = _AUDIT_REPORT_NUMBER_RE.search(_nfkc(line))
        if match:
            return match.group("number"), {
                "source": "full_text_line",
                "line": line_number,
                "confidence": 0.72,
            }
    return None


def _collect_text_key_value_facts(full_text: str) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Recover text KV facts with line-level, deliberately low-confidence provenance."""
    fields: dict[str, str] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate((full_text or "").splitlines(), start=1):
        match = _TEXT_KV_RE.match(line)
        if not match:
            continue
        key, value = _clean_label(match.group(1)), _clean_text_kv_value(match.group(2))
        if not key or not value:
            continue
        if key.casefold() in {"http", "https"} or any(ch in key for ch in ("。", "！", "？", "?", "!")):
            continue
        if not re.search(r"[A-Za-z\u3400-\u9fff]", key) or _CHAPTER_LABEL_RE.fullmatch(key):
            continue
        if not _looks_like_scalar_text_kv(key, value):
            continue
        if key not in fields:
            fields[key] = value
            metadata[key] = {"source": "full_text_line", "line": line_number, "confidence": 0.55}
        if len(fields) >= 200:
            break
    return fields, metadata


def _normalize_id_card_field(field: str, value: str) -> str:
    text = _clean_text_kv_value(re.sub(r"<[^>]+>", " ", value))
    if field == "name":
        compact = re.sub(r"\s+", "", text)
        return compact if re.fullmatch(r"[\u3400-\u9fff·]{2,8}", compact) else ""
    if field == "gender":
        match = re.search(r"[男女]", text)
        return match.group(0) if match else ""
    if field == "ethnicity":
        compact = re.sub(r"\s+", "", text).removesuffix("族")
        return compact if re.fullmatch(r"[\u3400-\u9fff]{1,8}", compact) else ""
    if field == "birth_date":
        match = re.search(r"((?:19|20)\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?", text)
        if not match:
            return ""
        normalized = f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        return normalized if validate_date_text(normalized) else ""
    if field == "address":
        compact = re.sub(r"\s+", "", text).strip("，,;；")
        return compact if 4 <= len(compact) <= 200 and re.search(r"[\u3400-\u9fff]", compact) else ""
    if field == "id_number":
        compact = re.sub(r"[\s-]+", "", text).upper()
        match = re.search(r"\d{17}[\dX]", compact)
        candidate = match.group(0) if match else ""
        return candidate if validate_cn_resident_id(candidate) else ""
    return ""


def _recover_id_card_fields(
    full_text: str,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], list[str]]:
    """Recover a fixed-layout identity-card front from OCR text without colons."""
    fields: dict[str, str] = {}
    metadata: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    address_parts: list[str] = []
    address_line = 0
    address_active = False
    address_candidates: list[tuple[str, int, int]] = []

    def finish_address() -> None:
        nonlocal address_parts, address_line, address_active
        value = _normalize_id_card_field("address", "".join(address_parts))
        if value:
            address_candidates.append((value, address_line, len(address_parts)))
        address_parts = []
        address_line = 0
        address_active = False

    for line_number, raw_line in enumerate((full_text or "").splitlines(), start=1):
        line = _nfkc(re.sub(r"<[^>]+>", " ", raw_line)).strip()
        if not line:
            continue
        if address_active:
            compact = re.sub(r"[\s-]+", "", line).upper()
            id_match = re.search(r"(?<!\d)\d{17}[\dX](?![0-9A-Za-z])", compact)
            if id_match and validate_cn_resident_id(id_match.group(0)):
                finish_address()
                fields.setdefault("id_number", id_match.group(0))
                metadata.setdefault(
                    "id_number",
                    {"source": "full_text_line", "line": line_number, "confidence": 0.9, "raw": line},
                )
                continue
            if _ID_CARD_LABEL_RE.search(line):
                finish_address()
            else:
                continuation = _normalize_id_card_field("address", line)
                if continuation:
                    address_parts.append(continuation)
                continue
        matches = list(_ID_CARD_LABEL_RE.finditer(line))
        if matches:
            for index, match in enumerate(matches):
                label = match.group(0)
                field = _ID_CARD_FIELD_BY_LABEL[label]
                end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
                raw_value = line[match.end() : end].strip(" \t:：")
                value = _normalize_id_card_field(field, raw_value)
                if not value:
                    continue
                if field == "address":
                    address_parts = [value]
                    address_line = line_number
                    address_active = True
                    continue
                fields.setdefault(field, value)
                metadata.setdefault(
                    field,
                    {"source": "full_text_line", "line": line_number, "confidence": 0.78, "raw": raw_value},
                )
            continue

        compact = re.sub(r"[\s-]+", "", line).upper()
        id_match = re.search(r"(?<!\d)\d{17}[\dX](?![0-9A-Za-z])", compact)
        if id_match and validate_cn_resident_id(id_match.group(0)):
            finish_address()
            fields.setdefault("id_number", id_match.group(0))
            metadata.setdefault(
                "id_number",
                {"source": "full_text_line", "line": line_number, "confidence": 0.9, "raw": line},
            )
            continue
    finish_address()
    if address_candidates:
        address, selected_line, _part_count = max(
            address_candidates,
            key=lambda item: (len(item[0]), item[2], -item[1]),
        )
        fields["address"] = address
        metadata["address"] = {
            "source": "full_text_lines",
            "line": selected_line,
            "confidence": 0.72,
            "raw": address,
        }
        if any(
            candidate != address and not address.startswith(candidate) and not candidate.startswith(address)
            for candidate, _line, _parts in address_candidates
        ):
            warnings.append("precision:id_card_address_conflict")

    identity_number = fields.get("id_number", "")
    if identity_number:
        derived_birth = f"{identity_number[6:10]}-{identity_number[10:12]}-{identity_number[12:14]}"
        derived_gender = "男" if int(identity_number[16]) % 2 else "女"
        if fields.get("birth_date") and fields["birth_date"] != derived_birth:
            warnings.append("precision:id_card_birth_id_mismatch")
        elif "birth_date" not in fields:
            fields["birth_date"] = derived_birth
            metadata["birth_date"] = {
                "source": "id_number_derived",
                "confidence": 0.85,
                "raw": identity_number[6:14],
            }
        if fields.get("gender") and fields["gender"] != derived_gender:
            warnings.append("precision:id_card_gender_id_mismatch")
        elif "gender" not in fields:
            fields["gender"] = derived_gender
            metadata["gender"] = {
                "source": "id_number_derived",
                "confidence": 0.85,
                "raw": identity_number[16],
            }
    return fields, metadata, warnings


def _recover_repeated_text_records(
    full_text: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any] | None]:
    """Recover a conservative row grid from repeated date-led text sequences.

    This is the last safety net for PDFs whose table geometry was lost but whose
    reading order still repeats a stable row width.  Requiring at least three
    date anchors and a dominant width avoids turning ordinary prose into rows.
    """
    tokens = [line.strip() for line in (full_text or "").splitlines() if line.strip()]
    date_indexes = [
        index for index, token in enumerate(tokens) if _is_valid_date_value(token) or _is_valid_datetime_value(token)
    ]
    if len(date_indexes) < 3:
        return [], {}, None
    spans = [right - left for left, right in zip(date_indexes, date_indexes[1:]) if 2 <= right - left <= 20]
    if not spans:
        return [], {}, None
    width, support = Counter(spans).most_common(1)[0]
    if support < max(2, len(date_indexes) - 2):
        return [], {}, None

    header_candidates = tokens[max(0, date_indexes[0] - width) : date_indexes[0]]
    useful_headers = (
        len(header_candidates) == width
        and len(set(header_candidates)) == width
        and all(re.search(r"[\w\u4e00-\u9fff]", value) for value in header_candidates)
        and not all(_matches_generic_type(value, "amount") for value in header_candidates)
    )
    headers, _header_repaired = _normalize_headers(header_candidates if useful_headers else [], width)
    raw_rows: list[dict[str, str]] = []
    for anchor_index, anchor in enumerate(date_indexes):
        if anchor_index + 1 < len(date_indexes) and date_indexes[anchor_index + 1] - anchor != width:
            continue
        cells = tokens[anchor : anchor + width]
        if len(cells) != width:
            continue
        raw_rows.append({header: cell for header, cell in zip(headers, cells)})
    if len(raw_rows) < 3:
        return [], {}, None

    column_values = {header: [row[header] for row in raw_rows] for header in headers}
    columns: dict[str, dict[str, Any]] = {}
    for header, values in column_values.items():
        column_type, confidence = _infer_generic_type(header, values)
        columns[header] = {
            "type": column_type,
            "confidence": round(confidence, 3),
            "null_ratio": 0.0,
        }
    records = [
        {
            "row_index": index,
            "raw": raw,
            "normalized": _build_normalized_record(raw, columns),
            "source": {"source": "full_text_repeated_rows"},
        }
        for index, raw in enumerate(raw_rows, start=1)
    ]
    descriptor = {
        "table_id": "text_recovered_0",
        "kind": "recovered_text_table",
        "headers": headers,
        "row_count": len(records),
        "source_pages": [],
        "recovery_method": "repeated_date_anchor",
        "row_width": width,
        "confidence": round(support / max(1, len(spans)), 4),
    }
    return records, columns, descriptor


def _field_type(key: str, value: Any) -> tuple[str, float]:
    if isinstance(value, bool):
        return "boolean", 1.0
    if isinstance(value, (int, float)):
        return "number", 1.0
    if isinstance(value, list):
        return "array", 1.0
    if isinstance(value, dict):
        return "object", 1.0
    return _infer_generic_type(key, [_nfkc(value)])


def _build_field_intelligence(fields: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return typed normalized fields and a compact data dictionary."""
    normalized: dict[str, Any] = {}
    schema: dict[str, Any] = {}
    for key, value in fields.items():
        field_type, confidence = _field_type(key, value)
        if isinstance(value, str) and field_type not in {"text", "boolean", "number", "array", "object"}:
            normalized[key] = _standardize_value(value, field_type)
        else:
            normalized[key] = value
        schema[key] = {
            "type": field_type,
            "confidence": round(float(confidence), 3),
            "nullable": False,
        }
    return normalized, schema


def _audit_appendix_boundary(parse_result: Any) -> int | None:
    """Find the signed-report terminus before rotated credential appendices."""
    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        page_text = " ".join(_nfkc(getattr(text, "content", "")) for text in getattr(page, "texts", []) or [])
        if re.search(r"本页无正文.{0,40}(?:签字|签章|盖章)页", page_text):
            return page_number
    return None


def _collect_field_metadata(
    parse_result: Any,
    fields: dict[str, Any],
    *,
    document_type: str = "",
) -> dict[str, Any]:
    """Attach page/bbox/evidence to generic KV facts without changing field values."""
    metadata: dict[str, Any] = {}
    wanted = set(fields)
    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        for kv in getattr(page, "key_values", []) or []:
            key = _clean_label(getattr(kv, "key", ""))
            if key not in wanted or key in metadata:
                continue
            item: dict[str, Any] = {
                "source": "canonical_key_value",
                "page": page_number,
                "confidence": round(float(getattr(kv, "confidence", 0.0) or 0.0), 4),
            }
            bbox = getattr(kv, "bbox", None)
            if bbox:
                item["bbox"] = list(bbox)
            evidence_ids = list(getattr(kv, "evidence_ids", []) or [])
            if evidence_ids:
                item["evidence_ids"] = evidence_ids
            metadata[key] = item

        for text in getattr(page, "texts", []) or []:
            if len(metadata) >= len(wanted):
                break
            for line in str(getattr(text, "content", "") or "").splitlines():
                match = _TEXT_KV_RE.match(line)
                if not match:
                    continue
                key = _clean_label(match.group(1))
                value = _clean_text_kv_value(match.group(2))
                field_value = _nfkc(fields.get(key))
                if (
                    key not in wanted
                    or key in metadata
                    or not (
                        field_value == value
                        or (key.endswith(_OCR_LONG_VALUE_SUFFIXES) and field_value.startswith(value))
                    )
                ):
                    continue
                item = {
                    "source": "canonical_text",
                    "page": page_number,
                    "confidence": round(float(getattr(text, "confidence", 0.0) or 0.0), 4),
                }
                bbox = getattr(text, "bbox", None)
                if bbox:
                    item["bbox"] = list(bbox)
                evidence_ids = list(getattr(text, "evidence_ids", []) or [])
                if evidence_ids:
                    item["evidence_ids"] = evidence_ids
                metadata[key] = item
    appendix_boundary = _audit_appendix_boundary(parse_result) if document_type == "audit_report" else None
    if appendix_boundary is not None:
        for item in metadata.values():
            if int(item.get("page") or 0) > appendix_boundary:
                item["confidence"] = round(min(0.79, float(item.get("confidence", 0.0) or 0.0)), 4)
    return metadata


# ── Identity extraction ─────────────────────────────────────────────────────

_IDENTITY_KEY_MAP: list[tuple[str, list[str]]] = [
    (
        "name",
        [
            "姓名",
            "名称",
            "户名",
            "name",
            "Name",
            "客户",
            "customer",
            "申请人",
            "借款人",
            "被保证人",
            "甲方",
            "乙方",
            "丙方",
        ],
    ),
    (
        "id_number",
        [
            "身份证",
            "证件号",
            "ID",
            "id_number",
            "subject_id",
            "证件号码",
            "统一社会信用代码",
            "信用代码",
            "税号",
            "纳税人识别号",
            "营业执照号",
            "护照号码",
            "护照号",
            "驾驶证号",
            "社会保障号码",
        ],
    ),
    ("phone", ["电话", "手机", "phone", "Phone", "联系电话", "Tel", "移动电话", "mobile", "Mobile"]),
    ("account", ["账号", "账户", "卡号", "account", "Account", "银行账号", "银行卡号", "开户行账号"]),
    ("address", ["地址", "Address", "address", "住所", "住址", "通讯地址", "注册地址", "办公地址"]),
    ("amount_total", ["合计", "总计", "total", "Total", "金额合计", "Sum", "总额", "总金额", "小计"]),
]

_IDENTITY_VALUE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("phone", _PHONE_RE),
    ("id_number", _ID_NUM_RE),
    ("email", _EMAIL_RE),
    ("account", _ACCOUNT_RE),
]


def _key_matches_identity_alias(key: str, alias: str) -> bool:
    key_text, alias_text = _clean_label(key).casefold(), _clean_label(alias).casefold()
    if not alias_text:
        return False
    if any("\u3400" <= char <= "\u9fff" for char in alias_text):
        return alias_text in key_text
    key_tokens = [token for token in re.split(r"[^a-z0-9]+", key_text) if token]
    alias_tokens = [token for token in re.split(r"[^a-z0-9]+", alias_text) if token]
    if len(alias_tokens) == 1:
        if alias_tokens[0] == "id":
            return key_tokens in (["id"], ["id", "number"], ["identity", "id"])
        return alias_tokens[0] in key_tokens
    return bool(alias_tokens) and " ".join(alias_tokens) in " ".join(key_tokens)


def _identity_value_is_valid(identity_type: str, value: Any, *, key_confirmed: bool = False) -> bool:
    text = _nfkc(value)
    if not text:
        return False
    if identity_type == "phone":
        return bool(_normalize_phone_value(text, header_confirmed=key_confirmed))
    if identity_type == "id_number":
        compact = re.sub(r"[\s-]+", "", text).upper()
        return bool(
            re.fullmatch(r"(?:\d{15}|\d{17}[\dX]|[0-9A-Z]{18})", compact)
            or (key_confirmed and re.fullmatch(r"(?=.*\d)[0-9A-Z]{6,20}", compact))
        )
    if identity_type == "account":
        return bool(re.fullmatch(r"[0-9A-Z]{8,34}", re.sub(r"[\s-]+", "", text), re.IGNORECASE))
    if identity_type == "amount_total":
        return _normalize_amount_value(text) is not None
    if identity_type == "email":
        return bool(_EMAIL_RE.fullmatch(text))
    return bool(text.strip("*-— "))


def _extract_identities(fields: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Auto-detect common identity fields from the fields dict.

    Two passes: key-name matching then value-pattern matching.
    """
    identities: dict[str, dict[str, Any]] = {}

    # Pass 1: Key-name matching
    for id_type, keywords in _IDENTITY_KEY_MAP:
        if id_type in identities:
            continue
        for key, value in fields.items():
            for kw in keywords:
                if _key_matches_identity_alias(key, kw) and _identity_value_is_valid(
                    id_type, value, key_confirmed=True
                ):
                    identities[id_type] = {
                        "key": key,
                        "value": str(value),
                        "confidence": 0.85,
                    }
                    break
            if id_type in identities:
                break

    # Pass 2: Value-pattern matching
    for id_type, regex in _IDENTITY_VALUE_PATTERNS:
        if id_type in identities:
            continue
        for key, value in fields.items():
            if id_type in {"id_number", "account"} and _generic_header_hint(key) != id_type:
                continue
            str_val = _nfkc(value)
            value_matches = _identity_value_is_valid(id_type, str_val)
            if id_type != "phone":
                value_matches = bool(regex.fullmatch(str_val)) and value_matches
            if value_matches:
                identities[id_type] = {
                    "key": key,
                    "value": str_val,
                    "confidence": 0.70,
                }
                break

    return identities


# ── Main builder ────────────────────────────────────────────────────────────


def _parse_result_has_ocr(parse_result: Any) -> bool:
    return any(
        str(getattr(page, "page_mode", "") or "").lower() in {"scanned", "scanned_ocr", "ocr"}
        or any(
            str(evidence_id).startswith("ocr:")
            for text in getattr(page, "texts", []) or []
            for evidence_id in getattr(text, "evidence_ids", []) or []
        )
        for page in getattr(parse_result, "pages", []) or []
    )


def _generic_recognition_text(parse_result: Any, fallback: str) -> str:
    """Use source page text for generic recovery, excluding derived tables."""
    raw_text = str(getattr(parse_result, "raw_text", "") or "").strip()
    if raw_text:
        return raw_text

    fallback_text = str(fallback or "").strip()
    rendered_text = str(getattr(parse_result, "full_text", "") or "").strip()
    if fallback_text and fallback_text != rendered_text:
        # Some direct plugin callers provide authoritative extractor text that
        # is more complete than ``pages[].texts``.  Preserve that established
        # path; only reject the known rendered ParseResult view.
        return fallback_text

    page_parts = [
        str(getattr(text, "content", "") or "").strip()
        for page in getattr(parse_result, "pages", []) or []
        for text in getattr(page, "texts", []) or []
        if str(getattr(text, "content", "") or "").strip()
    ]
    if page_parts:
        return "\n\n".join(page_parts)
    return fallback_text


def _collect_entity_fields(parse_result: Any, *, ocr_precision: bool = False) -> dict[str, Any]:
    """Collect entity fields from ParseResult with priority ordering.

    Priority: domain_specific > entities > common attrs > page KVs.
    """
    fields: dict[str, Any] = {}
    entities = getattr(parse_result, "entities", None)
    if entities is None:
        return fields

    # Priority 1: domain_specific entities
    raw = getattr(entities, "domain_specific", None)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if _is_public_field(key, value):
                fields[_clean_label(key)] = value
        extracted_entities = raw.get("extracted_entities")
        if isinstance(extracted_entities, dict):
            for key, value in extracted_entities.items():
                label = _clean_label(key)
                if _is_public_field(label, value) and label not in fields:
                    fields[label] = value

    # Priority 2: general entities
    raw = getattr(entities, "entities", None)
    if isinstance(raw, dict):
        for key, value in raw.items():
            label = _clean_label(key)
            if _is_public_field(label, value) and label not in fields:
                fields[label] = value

    # Priority 3: common structured attributes
    for attr in (
        "organization",
        "subject_name",
        "subject_id",
        "document_date",
        "period_start",
        "period_end",
        "institution",
        "account_number",
        "account_holder",
    ):
        val = getattr(entities, attr, None)
        if _is_public_field(attr, val) and attr not in fields:
            fields[attr] = val

    # Priority 4: page-level key_values
    for page in getattr(parse_result, "pages", []) or []:
        for kv in getattr(page, "key_values", []) or []:
            key = _clean_label(getattr(kv, "key", None))
            val = _nfkc(getattr(kv, "value", None))
            if key and val and key not in fields:
                fields[key] = val

    if ocr_precision and _parse_result_has_ocr(parse_result):
        fields = {
            key: value
            for key, value in fields.items()
            if not isinstance(value, str) or _looks_like_ocr_field(key, value)
        }
        fields = _deduplicate_similar_fields(fields)
    return fields


def _table_content_signature(table: Any) -> set[str]:
    return {
        _clean_label(getattr(cell, "text", cell))
        for row in getattr(table, "rows", []) or []
        for cell in getattr(row, "cells", []) or []
        if _clean_label(getattr(cell, "text", cell))
    }


def _table_bbox(table: Any) -> tuple[float, float, float, float] | None:
    bbox = getattr(table, "bbox", None)
    if not bbox or len(bbox) != 4:
        cell_boxes = [
            getattr(cell, "bbox", None)
            for row in getattr(table, "rows", []) or []
            for cell in getattr(row, "cells", []) or []
            if getattr(cell, "bbox", None)
        ]
        if not cell_boxes:
            return None
        bbox = [
            min(float(value[0]) for value in cell_boxes),
            min(float(value[1]) for value in cell_boxes),
            max(float(value[2]) for value in cell_boxes),
            max(float(value[3]) for value in cell_boxes),
        ]
    values = tuple(float(value) for value in bbox)
    if values[2] <= values[0] or values[3] <= values[1]:
        return None
    return values


def _bbox_overlap_ratio(
    left: tuple[float, float, float, float] | None,
    right: tuple[float, float, float, float] | None,
) -> float:
    """Intersection divided by the smaller table area for containment checks."""
    if left is None or right is None:
        return 0.0
    x0, y0 = max(left[0], right[0]), max(left[1], right[1])
    x1, y1 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    return intersection / max(1.0, min(left_area, right_area))


def _table_evidence_signature(table: Any) -> set[str]:
    return {str(evidence_id) for evidence_id in getattr(table, "evidence_ids", []) or [] if evidence_id} | {
        str(evidence_id)
        for row in getattr(table, "rows", []) or []
        for cell in getattr(row, "cells", []) or []
        for evidence_id in getattr(cell, "evidence_ids", []) or []
        if evidence_id
    }


def _deduplicate_table_views(
    views: list[tuple[Any, list[int], str]],
) -> list[tuple[Any, list[int], str]]:
    """Drop a page-local OCR grid that is wholly contained in a richer grid."""
    signatures = [_table_content_signature(table) for table, _pages, _kind in views]
    widths = [
        max((len(getattr(row, "cells", []) or []) for row in getattr(table, "rows", []) or []), default=0)
        for table, _pages, _kind in views
    ]
    bboxes = [_table_bbox(table) for table, _pages, _kind in views]
    evidence = [_table_evidence_signature(table) for table, _pages, _kind in views]
    retained: list[tuple[Any, list[int], str]] = []
    for index, view in enumerate(views):
        signature = signatures[index]
        pages = tuple(sorted(set(view[1])))
        duplicate = False
        if len(signature) >= 4:
            for other_index, other in enumerate(views):
                if other_index == index or tuple(sorted(set(other[1]))) != pages:
                    continue
                other_signature = signatures[other_index]
                text_overlap = len(signature & other_signature) / max(1, min(len(signature), len(other_signature)))
                evidence_overlap = (
                    len(evidence[index] & evidence[other_index])
                    / max(1, min(len(evidence[index]), len(evidence[other_index])))
                    if evidence[index] and evidence[other_index]
                    else 0.0
                )
                geometry_duplicate = bool(
                    _bbox_overlap_ratio(bboxes[index], bboxes[other_index]) >= 0.85 and text_overlap >= 0.7
                )
                other_rank = (len(other_signature), widths[other_index], other_index)
                current_rank = (len(signature), widths[index], index)
                richer = (
                    signature < other_signature
                    or ((evidence_overlap >= 0.85 or geometry_duplicate) and other_rank > current_rank)
                    or (signature == other_signature and (widths[other_index], other_index) > (widths[index], index))
                )
                if richer and (
                    signature <= other_signature
                    or evidence_overlap >= 0.85
                    or (geometry_duplicate and other_rank > current_rank)
                ):
                    duplicate = True
                    break
        if not duplicate:
            retained.append(view)
    return retained


def _select_generic_tables(parse_result: Any) -> list[tuple[Any, list[int], str]]:
    """Use physical tables only when a multi-page logical merge is unsafe."""
    physical: list[tuple[Any, list[int], str]] = []
    physical_by_id: dict[str, tuple[Any, list[int], str]] = {}
    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        for table_index, table in enumerate(getattr(page, "tables", []) or []):
            view = (table, [page_number], "physical_table")
            table_id = str(getattr(table, "table_id", "") or f"pt_{page_number}_{table_index}")
            physical.append(view)
            physical_by_id[table_id] = view
            physical_by_id.setdefault(f"pt_{page_number}_{table_index}", view)

    logical = list(getattr(parse_result, "logical_tables", []) or [])
    if not logical:
        return _deduplicate_table_views(physical)

    selected: list[tuple[Any, list[int], str]] = []
    used_physical: set[int] = set()
    for table in logical:
        source_pages = [int(page) for page in (getattr(table, "source_pages", []) or []) if int(page) > 0]
        source_ids = [str(value) for value in (getattr(table, "source_physical_ids", []) or []) if value]
        if not source_ids:
            source_ids = [
                str(getattr(prov, "source_table_id", "") or "")
                for prov in (getattr(table, "provenance", []) or [])
                if getattr(prov, "source_table_id", "")
            ]
        source_views = [
            physical_by_id[table_id] for table_id in dict.fromkeys(source_ids) if table_id in physical_by_id
        ]
        if not source_views and source_pages:
            source_views = [view for view in physical if view[1][0] in source_pages]

        signatures = {
            tuple(_clean_label(header) for header in (getattr(view[0], "headers", []) or []))
            for view in source_views
            if getattr(view[0], "headers", None)
        }
        ordered_pages = sorted(dict.fromkeys(source_pages))
        contiguous = all(right - left == 1 for left, right in zip(ordered_pages, ordered_pages[1:]))
        confidence = float(getattr(table, "merge_confidence", 1.0) or 0.0)
        unsafe_merge = len(ordered_pages) > 1 and (confidence < 0.75 or not contiguous or len(signatures) > 1)
        if unsafe_merge and source_views:
            for view in source_views:
                marker = id(view[0])
                if marker not in used_physical:
                    used_physical.add(marker)
                    selected.append(view)
            continue
        selected.append((table, source_pages, "logical_table"))
    return _deduplicate_table_views(selected)


def _collect_table_records(
    parse_result: Any,
    table_views: list[tuple[Any, list[int], str]] | None = None,
) -> list[dict[str, Any]]:
    """Collect table records from ParseResult into raw rows."""
    records: list[dict[str, Any]] = []
    tables = table_views if table_views is not None else _select_generic_tables(parse_result)

    row_index = 0
    for table_index, (table, source_pages, table_kind) in enumerate(tables):
        table_id = str(getattr(table, "logical_id", "") or getattr(table, "table_id", "") or f"table_{table_index}")
        provenance = list(getattr(table, "provenance", []) or [])
        headers, entries, header_repaired = _project_table_rows(table)
        for table_row_index, _row, cells in entries:
            row_index += 1
            raw = {str(h): str(c) for h, c in zip(headers, cells)}
            source: dict[str, Any] = {"table_id": table_id, "table_row_index": table_row_index}
            if header_repaired:
                source["header_repaired"] = True
            if table_row_index < len(provenance):
                prov = provenance[table_row_index]
                prov_page = int(getattr(prov, "source_page", 0) or 0)
                if prov_page:
                    source["page"] = prov_page
                physical_id = str(getattr(prov, "source_table_id", "") or "")
                if physical_id:
                    source["physical_table_id"] = physical_id
            elif table_kind == "physical_table" and source_pages:
                source["page"] = source_pages[0]
                source["physical_table_id"] = table_id
            elif source_pages:
                source["pages"] = source_pages
            records.append(
                {
                    "row_index": row_index,
                    "raw": raw,
                    "normalized": {},
                    "source": source,
                }
            )
    return records


def _collect_table_descriptors(
    parse_result: Any,
    table_views: list[tuple[Any, list[int], str]] | None = None,
) -> list[dict[str, Any]]:
    """Describe every logical/physical table so records remain navigable."""
    descriptors: list[dict[str, Any]] = []
    tables = table_views if table_views is not None else _select_generic_tables(parse_result)
    for index, (table, source_pages, table_kind) in enumerate(tables):
        headers, entries, header_repaired = _project_table_rows(table)
        descriptor = {
            "table_id": str(getattr(table, "logical_id", "") or getattr(table, "table_id", "") or f"table_{index}"),
            "kind": table_kind,
            "headers": headers,
            "row_count": len(entries),
            "source_pages": source_pages,
            **({"header_repaired": True} if header_repaired else {}),
        }
        if table_kind == "logical_table":
            descriptor["merge_confidence"] = round(float(getattr(table, "merge_confidence", 0.0) or 0.0), 4)
        else:
            descriptor["confidence"] = round(float(getattr(table, "confidence", 0.0) or 0.0), 4)
        descriptors.append(descriptor)
    return descriptors


def _collect_sections(parse_result: Any, *, document_type: str = "") -> list[dict[str, Any]]:
    """Create a compact document outline from sections and heading text blocks."""
    sections: list[dict[str, Any]] = []
    audit_mode = document_type == "audit_report"
    seen: set[str] = set()
    for index, section in enumerate(getattr(parse_result, "sections", []) or []):
        title = _normalize_section_title(
            (section.get("title") or section.get("name") or "")
            if isinstance(section, dict)
            else (getattr(section, "title", "") or getattr(section, "name", "") or "")
        )
        if not title or title in seen:
            continue
        seen.add(title)
        explicit_level = str(
            section.get("level", "") if isinstance(section, dict) else getattr(section, "level", "")
        ).lower()
        inferred_level = next(
            (level for pattern, level in _SECTION_HEADING_PATTERNS if pattern.fullmatch(_clean_label(title))),
            "",
        )
        item = {
            "id": str(section.get("id") if isinstance(section, dict) else getattr(section, "id", ""))
            or f"section_{index}",
            "title": title,
            "page_start": int(
                (section.get("page_start", 1) if isinstance(section, dict) else getattr(section, "page_start", 1)) or 1
            ),
        }
        if explicit_level or inferred_level:
            item["level"] = explicit_level or inferred_level
            item["_strict_sequence"] = True
        sections.append(item)

    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        for text in getattr(page, "texts", []) or []:
            content = _normalize_section_title(getattr(text, "content", ""))
            level = getattr(text, "level", None)
            level_value = str(getattr(level, "value", level) or "").lower()
            if level_value not in {"title", "h1", "h2", "h3", "heading"}:
                continue
            if not content or len(content) > 120 or content in seen:
                continue
            seen.add(content)
            item: dict[str, Any] = {
                "id": f"heading_{len(sections)}",
                "title": content,
                "level": level_value,
                "page_start": page_number,
                "_strict_sequence": True,
            }
            bbox = getattr(text, "bbox", None)
            if bbox:
                item["bbox"] = list(bbox)
            sections.append(item)

    trusted_left_edges: list[float] = []
    for page in getattr(parse_result, "pages", []) or []:
        page_texts = list(getattr(page, "texts", []) or [])
        for text_index, text in enumerate(page_texts[:-1]):
            marker = _clean_label(getattr(text, "content", ""))
            if not _SECTION_MARKER_ONLY_RE.fullmatch(marker):
                continue
            following = page_texts[text_index + 1]
            following_content = _clean_label(getattr(following, "content", ""))
            left_bbox = getattr(text, "bbox", None)
            right_bbox = getattr(following, "bbox", None)
            same_line = bool(left_bbox and right_bbox and abs(float(left_bbox[1]) - float(right_bbox[1])) <= 3.0)
            candidate = f"{marker}{following_content}"
            if (
                same_line
                and 4 <= len(following_content) <= 48
                and any(pattern.fullmatch(candidate) for pattern, _level in _SECTION_HEADING_PATTERNS)
            ):
                trusted_left_edges.append(float(left_bbox[0]))

    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        page_texts = list(getattr(page, "texts", []) or [])
        for text_index, text in enumerate(page_texts):
            lines = str(getattr(text, "content", "") or "").splitlines()
            marker = _clean_label(lines[0]) if len(lines) == 1 else ""
            marker_only = bool(_SECTION_MARKER_ONLY_RE.fullmatch(marker))
            joined_marker = False
            joined_bbox = getattr(text, "bbox", None)
            if marker_only and text_index + 1 < len(page_texts):
                following = page_texts[text_index + 1]
                following_content = _clean_label(getattr(following, "content", ""))
                left_bbox = getattr(text, "bbox", None)
                right_bbox = getattr(following, "bbox", None)
                same_line = bool(left_bbox and right_bbox and abs(float(left_bbox[1]) - float(right_bbox[1])) <= 3.0)
                if same_line and following_content and len(following_content) <= 48:
                    lines = [f"{marker}{following_content}"]
                    joined_marker = True
                    joined_bbox = [
                        min(float(left_bbox[0]), float(right_bbox[0])),
                        min(float(left_bbox[1]), float(right_bbox[1])),
                        max(float(left_bbox[2]), float(right_bbox[2])),
                        max(float(left_bbox[3]), float(right_bbox[3])),
                    ]
            if marker_only and not joined_marker and text_index > 0:
                previous = page_texts[text_index - 1]
                previous_content = _clean_label(getattr(previous, "content", ""))
                marker_bbox = getattr(text, "bbox", None)
                previous_bbox = getattr(previous, "bbox", None)
                same_line = bool(
                    marker_bbox and previous_bbox and abs(float(marker_bbox[1]) - float(previous_bbox[1])) <= 3.0
                )
                if same_line and previous_content and len(previous_content) <= 48:
                    lines = [f"{marker}{previous_content}"]
                    joined_marker = True
                    joined_bbox = [
                        min(float(marker_bbox[0]), float(previous_bbox[0])),
                        min(float(marker_bbox[1]), float(previous_bbox[1])),
                        max(float(marker_bbox[2]), float(previous_bbox[2])),
                        max(float(marker_bbox[3]), float(previous_bbox[3])),
                    ]
            for line in lines:
                title = _normalize_section_title(line)
                if (
                    not title
                    or title in seen
                    or "|" in title
                    or len(title) > 32
                    or title.endswith(("。", "；", ";", "，", ","))
                    or re.search(r"\d{1,3}(?:,\d{3})+\.\d", title)
                ):
                    continue
                level_value = next(
                    (level for pattern, level in _SECTION_HEADING_PATTERNS if pattern.fullmatch(title)),
                    "",
                )
                if not level_value:
                    continue
                if (
                    not joined_marker
                    and len(trusted_left_edges) >= 2
                    and joined_bbox
                    and min(abs(float(joined_bbox[0]) - edge) for edge in trusted_left_edges) > 12.0
                ):
                    continue
                heading_text = re.sub(
                    r"^(?:[一二三四五六七八九十百]{1,4}|\d{1,2})[、.．]|^[（(][^）)]{1,4}[）)]",
                    "",
                    title,
                ).strip()
                if len(heading_text) < (2 if audit_mode else 4):
                    continue
                seen.add(title)
                item = {
                    "id": f"heading_{len(sections)}",
                    "title": title,
                    "level": level_value,
                    "page_start": page_number,
                    "_strict_sequence": False,
                }
                if joined_bbox:
                    item["bbox"] = list(joined_bbox)
                sections.append(item)
    table_candidates: list[dict[str, Any]] = []
    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        for table in getattr(page, "tables", []) or []:
            for row in getattr(table, "rows", []) or []:
                nonempty_cells = [
                    cell for cell in (getattr(row, "cells", []) or []) if _clean_label(getattr(cell, "text", cell))
                ]
                candidate_bbox: list[float] | None = None
                if len(nonempty_cells) == 1:
                    cell = nonempty_cells[0]
                    title = _normalize_section_title(getattr(cell, "text", cell))
                    bbox = getattr(cell, "bbox", None)
                    if bbox:
                        candidate_bbox = list(bbox)
                elif len(nonempty_cells) == 2:
                    marker_cell, title_cell = nonempty_cells
                    marker = _clean_label(getattr(marker_cell, "text", marker_cell))
                    following = _clean_label(getattr(title_cell, "text", title_cell))
                    marker_bbox = getattr(marker_cell, "bbox", None)
                    title_bbox = getattr(title_cell, "bbox", None)
                    same_line = bool(
                        marker_bbox and title_bbox and abs(float(marker_bbox[1]) - float(title_bbox[1])) <= 3.0
                    )
                    if not _SECTION_MARKER_ONLY_RE.fullmatch(marker) or not same_line or len(following) > 48:
                        continue
                    title = _normalize_section_title(f"{marker}{following}")
                    candidate_bbox = [
                        min(float(marker_bbox[0]), float(title_bbox[0])),
                        min(float(marker_bbox[1]), float(title_bbox[1])),
                        max(float(marker_bbox[2]), float(title_bbox[2])),
                        max(float(marker_bbox[3]), float(title_bbox[3])),
                    ]
                else:
                    continue
                if not title or title in seen or len(title) > 32 or title.endswith(_TABLE_SECTION_METRIC_ENDINGS):
                    continue
                level_value = next(
                    (level for pattern, level in _SECTION_HEADING_PATTERNS if pattern.fullmatch(title)),
                    "",
                )
                if level_value not in {"h1", "h2"} or title.startswith(("(", "（")):
                    continue
                heading_text = re.sub(
                    r"^(?:[一二三四五六七八九十百]{1,4}|\d{1,2})[、.．]",
                    "",
                    title,
                ).strip()
                if len(heading_text) < 2:
                    continue
                item: dict[str, Any] = {
                    "id": f"table_heading_{len(table_candidates)}",
                    "title": title,
                    "level": level_value,
                    "page_start": page_number,
                    "_table_candidate": True,
                    "_strict_sequence": True,
                }
                if candidate_bbox:
                    item["bbox"] = candidate_bbox
                table_candidates.append(item)

    combined = sorted(
        [*sections, *table_candidates],
        key=lambda item: (
            int(item.get("page_start") or 1),
            float((item.get("bbox") or [0.0, float("inf")])[1]),
            bool(item.get("_table_candidate")),
        ),
    )
    recovered: list[dict[str, Any]] = []
    last_numeric_heading = 0
    last_chinese_heading = 0
    last_chinese_page = 0
    audit_anchor_pages = [
        int(item.get("page_start") or 1)
        for item in combined
        if audit_mode
        and re.search(
            r"公司基本情况|公司概况|企业基本情况|财务报表.*编制基础",
            str(item.get("title") or ""),
        )
    ]
    has_audit_notes_anchor = bool(audit_anchor_pages)
    audit_notes_start_page = max(audit_anchor_pages, default=1)
    strict_numeric_scope = False
    seen.clear()
    for item in combined:
        title = _normalize_section_title(item.get("title") or "")
        item["title"] = title
        if not title or title in seen:
            continue
        numeric_match = re.match(r"^(\d{1,2})[、.．]", title)
        chinese_match = re.match(r"^([一二三四五六七八九十]{1,3})[、.．]", title)
        item.pop("_table_candidate", False)
        strict_sequence = bool(item.pop("_strict_sequence", False))
        if item.get("level") == "h1":
            chinese_number = _chinese_section_number(chinese_match.group(1)) if chinese_match else 0
            page_start = int(item.get("page_start") or 1)
            audit_notes_anchor = bool(
                chinese_number == 1
                and page_start >= audit_notes_start_page
                and re.search(r"公司基本情况|公司概况|企业基本情况|财务报表.*编制基础", title)
            )
            reset_anchor = bool(
                audit_notes_anchor and last_chinese_heading >= 3 and page_start - last_chinese_page >= 3
            )
            if has_audit_notes_anchor and page_start < audit_notes_start_page:
                if not re.search(
                    r"审计意见|形成审计意见的基础|管理层和治理层.*责任|注册会计师.*责任",
                    title,
                ):
                    continue
            enforce_chinese_sequence = strict_sequence or has_audit_notes_anchor
            if (
                enforce_chinese_sequence
                and chinese_number
                and chinese_number <= last_chinese_heading
                and not reset_anchor
            ):
                continue
            if chinese_number:
                last_chinese_heading = chinese_number
                last_chinese_page = page_start
            last_numeric_heading = 0
            strict_numeric_scope = bool(re.search(r"(?:合并|母公司)?财务报表(?:主要)?项目注释", title))
        elif numeric_match:
            if has_audit_notes_anchor and int(item.get("page_start") or 1) < audit_notes_start_page:
                continue
            number = int(numeric_match.group(1))
            if (strict_sequence or strict_numeric_scope) and number <= last_numeric_heading:
                continue
            last_numeric_heading = number
        seen.add(title)
        item["id"] = f"heading_{len(recovered)}"
        recovered.append(item)
    return recovered


def _collect_structure_projected_records(parse_result: Any) -> list[dict[str, Any]]:
    """Project persisted canonical structures directly from ParseResult."""
    from docmirror.models.mirror.domain_access import (
        local_structure_evidence_pages_from_domain_specific,
        micro_grid_structures_from_domain_specific,
    )
    from docmirror.ocr.structure_project import infer_schema_hint, project_structure
    from docmirror.ocr.structure_projectors import core as _core  # noqa: F401

    projected: list[dict[str, Any]] = []
    domain_specific = getattr(getattr(parse_result, "entities", None), "domain_specific", {}) or {}
    structures: list[tuple[int, dict[str, Any]]] = []
    for page in local_structure_evidence_pages_from_domain_specific(domain_specific):
        page_num = int(page.get("page") or 0)
        structures.extend(
            (page_num, structure) for structure in page.get("structures") or [] if isinstance(structure, dict)
        )
    for structure in micro_grid_structures_from_domain_specific(domain_specific):
        structures.append((int(structure.get("page") or 0), structure))

    for page_num, structure in structures:
        hint = infer_schema_hint(structure)
        if not hint:
            continue
        result = project_structure(structure, page=page_num, schema_hint=hint)
        if result.rejected or result.record is None:
            continue
        projected.append(
            {
                **result.record,
                "block_id": structure.get("structure_id") or structure.get("grid_id"),
                "schema_hint": hint,
                "projection_completeness": result.completeness,
                "missing_fields": list(result.missing_fields),
            }
        )
    return projected


def _explicit_currency_context(text: str) -> str | None:
    """Return a currency only from an explicit amount-unit declaration."""
    normalized = _nfkc(text)
    if not (
        re.search(r"(?:金额|货币|币种).{0,12}(?:单位|为|[:：])", normalized)
        or re.search(r"(?:人民币|美元|欧元|英镑)(?:元|币)", normalized)
    ):
        return None
    return _currency_from_text(normalized)


def _collect_page_currency_context(parse_result: Any) -> dict[int, str]:
    """Collect page-local currency and carry it only from explicit scope declarations."""
    contexts: dict[int, str] = {}
    carried: str | None = None
    scope_re = re.compile(r"除(?:特别|另有)说明外|本(?:报告|文档).{0,12}金额单位|以下.{0,12}金额单位")
    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        texts = [str(getattr(text, "content", "") or "") for text in getattr(page, "texts", []) or []]
        for table in getattr(page, "tables", []) or []:
            if getattr(table, "caption", None):
                texts.append(str(getattr(table, "caption", "") or ""))
            texts.extend(str(header or "") for header in getattr(table, "headers", []) or [])
            texts.extend(
                str(getattr(cell, "text", cell) or "")
                for row in list(getattr(table, "rows", []) or [])[:3]
                for cell in getattr(row, "cells", []) or []
            )
        page_text = "\n".join(texts)
        explicit = _explicit_currency_context(page_text)
        if explicit:
            contexts[page_number] = explicit
            if scope_re.search(_nfkc(page_text)):
                carried = explicit
        elif carried:
            contexts[page_number] = carried
    return contexts


def _generic_precision_warnings(
    *,
    fields: dict[str, Any],
    field_metadata: dict[str, Any],
    field_schema: dict[str, Any],
    records: list[dict[str, Any]],
    columns: dict[str, dict[str, Any]],
    tables: list[dict[str, Any]],
) -> list[str]:
    """Return conservative review signals without changing extracted facts."""
    warnings: list[str] = []
    if fields:
        coverage = sum(key in field_metadata for key in fields) / len(fields)
        if coverage < 0.8:
            warnings.append(f"precision:generic_low_source_coverage:{coverage:.4f}")
        text_count = sum(
            isinstance(item, dict)
            and item.get("source") == "full_text_line"
            and float(item.get("confidence", 0.0) or 0.0) < 0.6
            for item in field_metadata.values()
        )
        if text_count:
            warnings.append(f"precision:generic_low_confidence_text_kv:count={text_count}")
    repaired_table_ids = [str(table.get("table_id") or "unknown") for table in tables if table.get("header_repaired")]
    if len(repaired_table_ids) <= 5:
        warnings.extend(f"precision:generic_header_repaired:{table_id}" for table_id in repaired_table_ids)
    elif repaired_table_ids:
        warnings.append(f"precision:generic_header_repaired_ratio:{len(repaired_table_ids)}/{len(tables)}")
    typed = {"amount", "date", "datetime", "percentage", "phone"}
    for key, info in columns.items():
        column_type = str(info.get("type") or "text")
        if column_type not in typed:
            continue
        pairs = [
            ((record.get("raw") or {}).get(key), (record.get("normalized") or {}).get(key))
            for record in records
            if isinstance(record.get("raw"), dict)
            and (record.get("raw") or {}).get(key) not in (None, "")
            and _looks_like_typed_candidate((record.get("raw") or {}).get(key), column_type)
        ]
        failures = [pair for pair in pairs if not isinstance(pair[1], dict)]
        if len(failures) >= 3 and len(failures) / max(1, len(pairs)) >= 0.1:
            warnings.append(f"precision:generic_normalization_failed:{key}")
        if column_type == "amount":
            normalized_amounts = [normalized for _raw, normalized in pairs if isinstance(normalized, dict)]
            if normalized_amounts and any(not normalized.get("currency") for normalized in normalized_amounts):
                warnings.append(f"precision:generic_currency_unknown:{key}")
    for key, info in field_schema.items():
        value = fields.get(key)
        if info.get("type") == "amount" and value not in (None, "") and not _currency_from_text(str(value)):
            warnings.append(f"precision:generic_currency_unknown:{key}")
    for table in tables:
        confidence = float(table.get("confidence", 0.0) or 0.0)
        if table.get("kind") == "recovered_text_table" and confidence < 0.9:
            warnings.append(f"precision:generic_text_table_low_confidence:{confidence:.4f}")
    suspicious_rows: list[str] = []
    for record in records:
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        if not any(_embedded_amount_count(value) >= 2 for value in raw.values()):
            continue
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        table_id = str(source.get("table_id") or "unknown")
        table_row_index = source.get("table_row_index")
        marker = f"{table_id}@row={table_row_index}" if table_row_index is not None else table_id
        suspicious_rows.append(marker)
    warnings.extend(f"precision:generic_row_alignment_suspect:{marker}" for marker in dict.fromkeys(suspicious_rows))
    return list(dict.fromkeys(warnings))[:50]


def derive_generic_projection(
    parse_result: Any,
    detected_type: str,
    full_text: str = "",
) -> Any:
    """Build deterministic generic ``ProjectionData`` from sealed evidence."""
    recognition_text = _generic_recognition_text(parse_result, full_text)
    ocr_document = _parse_result_has_ocr(parse_result)
    raw_entity_fields = _collect_entity_fields(parse_result)
    fields = (
        _deduplicate_similar_fields(
            {
                key: value
                for key, value in raw_entity_fields.items()
                if not isinstance(value, str) or _looks_like_ocr_field(key, value)
            }
        )
        if ocr_document
        else raw_entity_fields
    )
    filtered_ocr_field_count = max(0, len(raw_entity_fields) - len(fields))
    text_fields, text_field_metadata = _collect_text_key_value_facts(recognition_text)
    if ocr_document:
        text_fields = {key: value for key, value in text_fields.items() if _looks_like_ocr_field(key, value)}
        text_field_metadata = {key: value for key, value in text_field_metadata.items() if key in text_fields}
    identity_warnings: list[str] = []
    recovered_fields: dict[str, str] = {}
    if detected_type == "id_card":
        recovered_fields, recovered_metadata, identity_warnings = _recover_id_card_fields(recognition_text)
        for key, value in recovered_fields.items():
            text_fields[key] = value
            text_field_metadata[key] = recovered_metadata[key]
    if detected_type == "audit_report" and "审计报告文号" not in fields:
        recovered_number = _recover_audit_report_number(recognition_text)
        if recovered_number is not None:
            number, number_metadata = recovered_number
            text_fields.setdefault("审计报告文号", number)
            text_field_metadata.setdefault("审计报告文号", number_metadata)
    accepted_text_metadata: dict[str, dict[str, Any]] = {}
    for key, value in text_fields.items():
        if key not in fields:
            fields[key] = value
            accepted_text_metadata[key] = text_field_metadata[key]
        elif key == "address" and key in recovered_fields and isinstance(fields[key], str):
            existing = _normalize_id_card_field("address", fields[key])
            recovered = recovered_fields[key]
            if existing and recovered.startswith(existing) and len(recovered) > len(existing):
                fields[key] = recovered
                accepted_text_metadata[key] = text_field_metadata[key]
            elif existing and existing != recovered and not existing.startswith(recovered):
                identity_warnings.append("precision:id_card_address_conflict")
    if ocr_document:
        fields = _deduplicate_similar_fields(fields)
        accepted_text_metadata = {key: value for key, value in accepted_text_metadata.items() if key in fields}
        fields = _extend_ocr_long_fields(fields, parse_result)
    fields = _drop_redundant_generic_fields(fields)
    accepted_text_metadata = {key: value for key, value in accepted_text_metadata.items() if key in fields}
    table_views = _select_generic_tables(parse_result)
    records = _collect_table_records(parse_result, table_views)
    recovered_records: list[dict[str, Any]] = []
    recovered_columns: dict[str, dict[str, Any]] = {}
    recovered_table: dict[str, Any] | None = None
    if not records:
        recovered_records, recovered_columns, recovered_table = _recover_repeated_text_records(recognition_text)
        records.extend(recovered_records)
    structure_records = _collect_structure_projected_records(parse_result)
    if structure_records:
        for projected in structure_records:
            records.append(
                {
                    "row_index": len(records) + 1,
                    "raw": {},
                    "normalized": dict(projected),
                    "record_type": "structure_projection",
                    "source": {
                        "page": projected.get("page"),
                        "block_id": projected.get("block_id"),
                        "schema_hint": projected.get("schema_hint"),
                    },
                }
            )

    # ── Heuristic column type detection ──
    all_tables = [table for table, _source_pages, _kind in table_views]

    col_types = _infer_column_types(all_tables) if all_tables else {}
    table_col_types = _infer_table_column_types(table_views) if table_views else {}
    if not col_types and records:
        col_types = _infer_record_column_types(records)
    for key, value in recovered_columns.items():
        col_types.setdefault(key, value)

    # ── Build normalized records ──
    currency_context = _collect_page_currency_context(parse_result)
    for record in records:
        raw = record.get("raw", {})
        if raw and col_types:
            source = record.get("source") if isinstance(record.get("source"), dict) else {}
            record_col_types = table_col_types.get(str(source.get("table_id") or ""), col_types)
            page_number = int(source.get("page") or 0)
            if not page_number and isinstance(source.get("pages"), list) and source["pages"]:
                page_number = int(source["pages"][0] or 0)
            record["normalized"] = _build_normalized_record(
                raw,
                record_col_types,
                currency_hint=currency_context.get(page_number),
            )
            if record["normalized"] == raw:
                record["normalized"] = {}

    # ── Identity extraction ──
    identities = _extract_identities(fields) if fields else {}
    normalized_fields, field_schema = _build_field_intelligence(fields)
    field_metadata = _collect_field_metadata(parse_result, fields, document_type=detected_type)
    for key, metadata in accepted_text_metadata.items():
        field_metadata.setdefault(key, metadata)
    sections = _collect_sections(parse_result, document_type=detected_type)
    table_descriptors = _collect_table_descriptors(parse_result, table_views)
    if recovered_table is not None:
        table_descriptors.append(recovered_table)

    # ── Assemble structured data ──
    page_count = len(getattr(parse_result, "pages", []) or [])
    referenced_pages = [
        *[
            int(item.get("page") or 0)
            for item in field_metadata.values()
            if isinstance(item, dict) and int(item.get("page") or 0) > 0
        ],
        *[
            int((record.get("source") or {}).get("page") or 0)
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("source"), dict)
            and int((record.get("source") or {}).get("page") or 0) > 0
        ],
        *[int(page) for table in table_descriptors for page in table.get("source_pages", []) or [] if int(page) > 0],
        *[int(section.get("page_start") or 0) for section in sections if int(section.get("page_start") or 0) > 0],
    ]

    summary = {"total_rows": len(records)}
    summary["field_count"] = len(fields)
    summary["table_count"] = len(table_descriptors)
    summary["section_count"] = len(sections)
    if col_types:
        summary["inferred_columns"] = len(col_types)
    if identities:
        summary["inferred_identities"] = len(identities)
    if recovered_records:
        summary["text_recovered_record_count"] = len(recovered_records)
    if structure_records:
        summary["structure_projected_record_count"] = len(structure_records)

    warnings: list[str] = [_GENERIC_WARNING]
    if not fields and not records:
        warnings.append("no_fields_extracted")
    if page_count and not recognition_text.strip() and not fields and not records:
        warnings.append("precision:generic_ocr_required")
    if filtered_ocr_field_count:
        warnings.append(f"precision:generic_ocr_fields_filtered:count={filtered_ocr_field_count}")
    if referenced_pages and max(referenced_pages) > page_count:
        warnings.append(f"precision:generic_page_reference_mismatch:{max(referenced_pages)}/{page_count}")
    warnings.extend(identity_warnings)
    warnings.extend(
        _generic_precision_warnings(
            fields=fields,
            field_metadata=field_metadata,
            field_schema=field_schema,
            records=records,
            columns=col_types,
            tables=table_descriptors,
        )
    )

    structured_data = {
        "records": records,
        "summary": summary,
        "sections": sections,
        "tables": table_descriptors,
        "line_items": [],
        "normalized_fields": normalized_fields,
        "field_schema": field_schema,
        "field_metadata": field_metadata,
    }
    if col_types:
        structured_data["columns"] = col_types
    if identities:
        structured_data["identities"] = identities

    from docmirror.plugins._base.generic_projection import make_generic_projection

    return make_generic_projection(detected_type, fields, structured_data, warnings)
