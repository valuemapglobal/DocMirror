# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Consumer-first business projection for Community 6+1 outputs.

The domain plugins remain responsible for factual extraction.  This hook turns
their facts into a consistent, immediately usable layer: business overview,
descriptive metrics, data dictionary, contract gaps and extraction readiness.
It deliberately avoids predictive risk scoring and never mutates Core Mirror.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins._runtime.post_extract.base import PostExtractHook

_DOMAIN_LABELS = {
    "bank_statement": "银行流水",
    "wechat_payment": "微信支付交易明细",
    "alipay_payment": "支付宝交易明细",
    "vat_invoice": "增值税发票",
    "business_license": "营业执照",
    "credit_report": "征信报告",
    "generic": "通用业务文档",
}

_FIELD_LABELS = {
    "account_holder": "账户户名",
    "account_number": "账户号码",
    "bank_name": "银行名称",
    "query_period": "查询期间",
    "currency": "币种",
    "date": "日期",
    "timestamp": "交易时间",
    "transaction_date": "交易日期",
    "trade_no": "交易单号",
    "merchant_no": "商户单号",
    "transaction_type": "交易类型",
    "direction": "收支方向",
    "amount": "金额",
    "amount_cny": "人民币金额",
    "balance": "余额",
    "counter_party": "交易对方",
    "counter_account": "对方账户",
    "payment_method": "支付方式",
    "summary": "摘要",
    "invoice_code": "发票代码",
    "invoice_number": "发票号码",
    "invoice_date": "开票日期",
    "buyer_name": "购买方名称",
    "buyer_tax_id": "购买方纳税人识别号",
    "seller_name": "销售方名称",
    "seller_tax_id": "销售方纳税人识别号",
    "total_amount": "价税合计",
    "amount_without_tax": "不含税金额",
    "tax_amount": "税额",
    "tax_rate": "税率",
    "company_name": "企业名称",
    "unified_social_credit_code": "统一社会信用代码",
    "legal_representative": "法定代表人",
    "registered_capital": "注册资本",
    "date_of_establishment": "成立日期",
    "business_term": "营业期限",
    "business_scope": "经营范围",
    "address": "地址",
    "subject_name": "报告主体",
    "id_number": "证件号码",
    "report_time": "报告时间",
    "report_number": "报告编号",
    "phone": "联系电话",
    "wechat_id": "微信号",
    "alipay_account": "支付宝账户",
}

_DATASET_LABELS = {
    "records": "结构化记录",
    "line_items": "商品与服务明细",
    "credit_accounts": "信贷账户",
    "repayment_records": "还款记录",
    "overdue_records": "逾期记录",
    "inquiry_records": "查询记录",
}

_DATASET_KINDS = {
    "records": "generic_record",
    "line_items": "line_item",
    "credit_accounts": "credit_account",
    "repayment_records": "repayment",
    "overdue_records": "overdue",
    "inquiry_records": "inquiry",
}

_SENSITIVE_EXACT = {
    "account_number": "keep_last_4",
    "counter_account": "keep_last_4",
    "id_number": "keep_first_3_last_4",
    "buyer_tax_id": "keep_first_4_last_4",
    "seller_tax_id": "keep_first_4_last_4",
    "unified_social_credit_code": "keep_first_4_last_4",
    "phone": "keep_first_3_last_4",
    "wechat_id": "keep_last_4",
    "alipay_account": "keep_last_4",
}

_DATA_KEYS_NOT_DATASETS = {
    "document_flow",
    "notes",
    "sections",
    "tables",
}

_GENERIC_LEGACY_DATA_KEYS = {
    "normalized_fields",
    "field_schema",
    "identities",
}


def _unwrap(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("normalized_value", "value", "raw_value"):
        if value.get(key) not in (None, ""):
            return value[key]
    return value


def _present(value: Any) -> bool:
    value = _unwrap(value)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _as_float(value: Any) -> float | None:
    value = _unwrap(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from docmirror.plugins._base.standardizer import normalize_amount

        return normalize_amount(str(value or ""))
    except Exception:
        return None


def _record_value(record: dict[str, Any], *keys: str) -> Any:
    normalized = record.get("normalized") if isinstance(record.get("normalized"), dict) else {}
    raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
    for pool in (normalized, raw):
        for key in keys:
            if pool.get(key) not in (None, ""):
                return _unwrap(pool[key])
    return None


def _infer_type(values: list[Any]) -> str:
    sample = [_unwrap(value) for value in values if _present(value)]
    if not sample:
        return "unknown"
    if all(isinstance(value, bool) for value in sample):
        return "boolean"
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in sample):
        return "number"
    if all(isinstance(value, list) for value in sample):
        return "array"
    if all(isinstance(value, dict) for value in sample):
        return "object"
    strings = [str(value).strip() for value in sample]
    try:
        from docmirror.plugins._base.generic_mirror_adapter import _type_detect_column

        inferred, confidence = _type_detect_column(strings)
        return inferred if confidence >= 0.6 else "text"
    except Exception:
        return "text"


def _pointer_token(value: Any) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _field_label(key: Any) -> str:
    text = str(key)
    return _FIELD_LABELS.get(text, text.replace("_", " ") if text.isascii() else text)


def _normalized_json_type(field_type: str) -> str:
    if field_type in {"amount", "percentage"}:
        return "number"
    if field_type in {"date", "datetime", "phone", "text"}:
        return "string"
    return field_type if field_type in {"string", "number", "integer", "boolean", "array", "object"} else "unknown"


def _field_format(key: Any, field_type: str) -> str:
    text = str(key).lower()
    if key in _SENSITIVE_EXACT:
        if "phone" in text:
            return "phone"
        if "id_number" in text or "tax_id" in text:
            return "id_number"
        if "account" in text:
            return "account_number"
        return "identifier"
    if field_type == "datetime" or any(token in text for token in ("timestamp", "_time")):
        return "datetime"
    if field_type == "date" or "date" in text:
        return "date"
    if field_type == "percentage" or any(token in text for token in ("rate", "ratio", "percent")):
        return "percentage"
    if field_type == "amount" or any(
        token in text for token in ("amount", "income", "expense", "balance", "capital", "price", "tax", "金额", "余额")
    ):
        return "currency"
    if field_type == "boolean":
        return "boolean"
    if field_type == "integer" or text.endswith("_count") or text in {"row_index", "page"}:
        return "integer"
    if field_type == "number":
        return "decimal"
    if any(token in text for token in ("number", "_no", "code")):
        return "identifier"
    return "text"


def _sensitive_policy(key: Any) -> tuple[bool, str | None]:
    text = str(key)
    if text in _SENSITIVE_EXACT:
        return True, _SENSITIVE_EXACT[text]
    lowered = text.lower()
    if any(token in lowered for token in ("身份证", "银行卡", "account_number", "id_number", "phone")):
        return True, "keep_last_4"
    return False, None


def _row_values(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"value": row}
    normalized = row.get("normalized") if isinstance(row.get("normalized"), dict) else {}
    if any(_present(value) for value in normalized.values()):
        return normalized
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    if raw:
        return raw
    return {
        str(key): value
        for key, value in row.items()
        if key
        not in {
            "source",
            "source_refs",
            "source_fact_ids",
            "evidence_ids",
        }
    }


def _build_dataset_columns(rows: list[Any]) -> dict[str, dict[str, Any]]:
    values_by_column: dict[str, list[Any]] = defaultdict(list)
    present_by_column: Counter[str] = Counter()
    for row in rows:
        values = _row_values(row)
        for key, value in values.items():
            column = str(key)
            values_by_column[column].append(value)
            if _present(value):
                present_by_column[column] += 1

    columns: dict[str, dict[str, Any]] = {}
    for order, (key, values) in enumerate(values_by_column.items()):
        inferred = _infer_type(values)
        field_format = _field_format(key, inferred)
        sensitive, mask = _sensitive_policy(key)
        item: dict[str, Any] = {
            "label": _field_label(key),
            "type": _normalized_json_type(inferred),
            "format": field_format,
            "coverage": round(present_by_column[key] / max(1, len(rows)), 4),
            "nullable": present_by_column[key] < len(rows),
            "sensitive": sensitive,
            "display_order": order,
        }
        if field_format == "currency":
            item["unit"] = "CNY"
        if mask:
            item["mask"] = mask
        columns[key] = item
    return columns


def _dataset_descriptor(key: str, rows: list[Any], *, domain: str, role: str) -> dict[str, Any]:
    kind = _DATASET_KINDS.get(key, key.removesuffix("_records") or "generic_record")
    if key == "records" and domain in {"bank_statement", "wechat_payment", "alipay_payment"}:
        kind = "transaction"
    columns_ref = (
        "/data/data_dictionary/record_columns"
        if key == "records"
        else f"/data/data_dictionary/datasets/{_pointer_token(key)}/columns"
    )
    return {
        "id": key,
        "label": _DATASET_LABELS.get(key, _field_label(key)),
        "kind": kind,
        "role": role,
        "data_ref": f"/data/{_pointer_token(key)}",
        "row_count": len(rows),
        "columns_ref": columns_ref,
    }


def _build_dataset_catalog(data: dict[str, Any], domain: str) -> list[dict[str, Any]]:
    candidates: list[str] = []
    if domain == "vat_invoice":
        if isinstance(data.get("line_items"), list) and data["line_items"]:
            candidates.append("line_items")
        elif isinstance(data.get("records"), list) and data["records"]:
            candidates.append("records")
    elif domain == "credit_report":
        candidates.extend(
            key
            for key in ("credit_accounts", "repayment_records", "overdue_records", "inquiry_records")
            if isinstance(data.get(key), list) and data[key]
        )
        if not candidates and isinstance(data.get("records"), list) and data["records"]:
            candidates.append("records")
    elif isinstance(data.get("records"), list) and data["records"]:
        candidates.append("records")

    base_keys = {
        "fields",
        "field_details",
        "field_metadata",
        "field_schema",
        "normalized_fields",
        "records",
        "line_items",
        "summary",
        "data_dictionary",
        "datasets",
        *_DATA_KEYS_NOT_DATASETS,
    }
    for key, value in data.items():
        if key in base_keys or key in candidates:
            continue
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            candidates.append(str(key))

    return [
        _dataset_descriptor(key, data[key], domain=domain, role="primary" if index == 0 else "auxiliary")
        for index, key in enumerate(candidates)
    ]


def _deduplicate_vat_records(data: dict[str, Any]) -> None:
    """Drop VAT base records only when ``line_items`` already carries every normalized row."""
    records = data.get("records") if isinstance(data.get("records"), list) else []
    line_items = data.get("line_items") if isinstance(data.get("line_items"), list) else []
    if not records or len(records) != len(line_items):
        return
    normalized_rows = [
        record.get("normalized") if isinstance(record, dict) and isinstance(record.get("normalized"), dict) else record
        for record in records
    ]
    if normalized_rows == line_items:
        data["records"] = []


def _build_data_dictionary(
    data: dict[str, Any],
    datasets: list[dict[str, Any]],
) -> dict[str, Any]:
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    records = data.get("records") if isinstance(data.get("records"), list) else []
    field_details = data.get("field_details") if isinstance(data.get("field_details"), dict) else {}
    legacy_schema = data.get("field_schema") if isinstance(data.get("field_schema"), dict) else {}
    field_schema: dict[str, dict[str, Any]] = {}
    for order, (key, value) in enumerate(fields.items()):
        if not _present(value):
            continue
        detail = field_details.get(key) if isinstance(field_details.get(key), dict) else {}
        legacy = legacy_schema.get(key) if isinstance(legacy_schema.get(key), dict) else {}
        inferred = str(legacy.get("type") or _infer_type([detail.get("normalized", value)]))
        field_format = _field_format(key, inferred)
        sensitive, mask = _sensitive_policy(key)
        item: dict[str, Any] = {
            "label": _field_label(key),
            "type": _normalized_json_type(inferred),
            "format": field_format,
            "nullable": False,
            "sensitive": sensitive,
            "has_source": bool(detail.get("source_refs")),
            "display_order": order,
            "value_ref": f"/data/fields/{_pointer_token(key)}",
            "detail_ref": f"/data/field_details/{_pointer_token(key)}",
        }
        if field_format == "currency":
            item["unit"] = "CNY"
        if mask:
            item["mask"] = mask
        field_schema[str(key)] = item

    record_schema = _build_dataset_columns(records)
    dataset_schemas: dict[str, dict[str, Any]] = {}
    for dataset in datasets:
        dataset_id = str(dataset["id"])
        if dataset_id == "records":
            dataset_schemas[dataset_id] = {"columns_ref": "/data/data_dictionary/record_columns"}
            continue
        rows = data.get(dataset_id) if isinstance(data.get(dataset_id), list) else []
        dataset_schemas[dataset_id] = {"columns": _build_dataset_columns(rows)}
    primary_record_count = int(datasets[0]["row_count"]) if datasets else len(records)
    return {
        "version": "community.dictionary.v1",
        "field_count": len(field_schema),
        "record_count": primary_record_count,
        "fields": field_schema,
        "record_columns": record_schema,
        "datasets": dataset_schemas,
    }


def _correct_generic_currency_units(data: dict[str, Any]) -> None:
    """Keep Generic currency units only when normalized facts state a currency."""
    dictionary = data.get("data_dictionary") if isinstance(data.get("data_dictionary"), dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    for key, schema in (dictionary.get("fields") or {}).items():
        if not isinstance(schema, dict) or schema.get("format") != "currency":
            continue
        value = fields.get(key)
        currency = value.get("currency") if isinstance(value, dict) else None
        if currency:
            schema["unit"] = str(currency)
        else:
            schema.pop("unit", None)
    records = data.get("records") if isinstance(data.get("records"), list) else []
    for key, schema in (dictionary.get("record_columns") or {}).items():
        if not isinstance(schema, dict) or schema.get("format") != "currency":
            continue
        currencies = {
            str(value["currency"])
            for record in records
            if isinstance(record, dict)
            for value in [(record.get("normalized") or {}).get(key)]
            if isinstance(value, dict) and value.get("currency")
        }
        if len(currencies) == 1:
            schema["unit"] = next(iter(currencies))
        else:
            schema.pop("unit", None)


def _normalization_rate(records: list[Any], fields: dict[str, Any]) -> float:
    if not records:
        return 1.0 if fields else 0.0
    normalized = 0
    for record in records:
        if isinstance(record, dict) and isinstance(record.get("normalized"), dict):
            if any(_present(value) for value in record["normalized"].values()):
                normalized += 1
    return round(normalized / len(records), 4)


def _generic_typed_normalization_rate(data: dict[str, Any]) -> float | None:
    """Measure Generic typed cells instead of counting copied text as normalized."""
    records = data.get("records") if isinstance(data.get("records"), list) else []
    columns = data.get("columns") if isinstance(data.get("columns"), dict) else {}
    typed = {
        str(key)
        for key, info in columns.items()
        if isinstance(info, dict) and info.get("type") in {"amount", "date", "datetime", "percentage", "phone"}
    }
    considered = 0
    normalized = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        values = record.get("normalized") if isinstance(record.get("normalized"), dict) else {}
        for key in typed:
            raw_value = raw.get(key)
            if raw_value in (None, ""):
                continue
            column_type = str((columns.get(key) or {}).get("type") or "")
            text = str(raw_value).strip()
            is_candidate = (
                bool(re.search(r"\d|[¥￥$€£]", text))
                if column_type == "amount"
                else len(re.sub(r"\D", "", text)) >= 6
                if column_type == "phone"
                else bool(re.search(r"\d", text) or (column_type == "percentage" and "%" in text))
            )
            if not is_candidate:
                continue
            considered += 1
            if isinstance(values.get(key), dict) and values[key].get("value") not in (None, ""):
                normalized += 1
    return round(normalized / considered, 4) if considered else None


def _adjust_generic_quality(quality: dict[str, Any], output: dict[str, Any]) -> None:
    """Keep Generic score/grade consistent with typed-cell quality and review signals."""
    data = output.get("data") if isinstance(output.get("data"), dict) else {}
    typed_rate = _generic_typed_normalization_rate(data)
    if typed_rate is not None:
        previous = float(quality.get("normalization_rate", 0.0) or 0.0)
        quality["normalization_rate"] = typed_rate
        quality["score"] = round(
            max(0.0, float(quality.get("score", 0.0) or 0.0) - 0.2 * max(0.0, previous - typed_rate)),
            4,
        )
    warnings = (output.get("status") or {}).get("warnings") or []
    tables = data.get("tables") if isinstance(data.get("tables"), list) else []
    repaired_ratio = (
        sum(isinstance(table, dict) and bool(table.get("header_repaired")) for table in tables) / len(tables)
        if tables
        else 0.0
    )
    placeholder_ratio = (
        sum(
            isinstance(table, dict)
            and any(
                re.fullmatch(r"(?:col(?:umn)?|字段|列)[_\s-]*\d+", str(header), re.IGNORECASE)
                for header in table.get("headers", []) or []
            )
            for table in tables
        )
        / len(tables)
        if tables
        else 0.0
    )
    structural_review_ratio = max(repaired_ratio, placeholder_ratio)
    if structural_review_ratio:
        quality["score"] = round(
            max(0.0, float(quality.get("score", 0.0) or 0.0) - 0.18 * structural_review_ratio),
            4,
        )
    if any("generic_page_reference_mismatch" in str(warning) for warning in warnings):
        quality["score"] = round(max(0.0, float(quality.get("score", 0.0) or 0.0) - 0.15), 4)
    has_precision_review = any(str(warning).startswith("precision:") for warning in warnings)
    if quality.get("readiness") == "review" and has_precision_review:
        quality["score"] = min(float(quality.get("score", 0.0) or 0.0), 0.8999)
    score = float(quality.get("score", 0.0) or 0.0)
    quality["grade"] = (
        "excellent" if score >= 0.9 else "good" if score >= 0.75 else "review" if score >= 0.5 else "insufficient"
    )


def _source_quality(result: ParseResult) -> float:
    candidates = [
        float(getattr(result, "confidence", 0.0) or 0.0),
        float(getattr(getattr(result, "parser_info", None), "overall_confidence", 0.0) or 0.0),
        float(getattr(getattr(result, "trust", None), "trust_score", 0.0) or 0.0),
    ]
    available = [value for value in candidates if value > 0]
    return round(max(available) if available else 0.0, 4)


def _evidence_quality(result: ParseResult, data: dict[str, Any]) -> dict[str, Any]:
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    records = list(data.get("records") or []) if isinstance(data.get("records"), list) else []
    if not records:
        for collection_name in (
            "credit_accounts",
            "credit_lines",
            "repayment_records",
            "overdue_records",
            "inquiry_records",
            "public_records",
            "residence_records",
            "employment_records",
            "repayment_liability_records",
        ):
            collection = data.get(collection_name)
            if isinstance(collection, list):
                records.extend(item for item in collection if isinstance(item, dict))
    field_metadata = data.get("field_metadata") if isinstance(data.get("field_metadata"), dict) else {}
    field_details = data.get("field_details") if isinstance(data.get("field_details"), dict) else {}
    sourced_fields = sum(
        1
        for key, value in fields.items()
        if key in field_metadata
        or (isinstance(field_details.get(key), dict) and bool(field_details[key].get("source_refs")))
        or (isinstance(value, dict) and bool(value.get("source_refs") or value.get("evidence_ids")))
    )
    sourced_records = sum(
        1
        for record in records
        if isinstance(record, dict)
        and bool(
            record.get("source")
            or record.get("source_refs")
            or record.get("source_cell_refs")
            or record.get("source_fact_ids")
            or record.get("evidence_ids")
        )
    )
    evidence_ids: set[str] = set()
    for page in getattr(result, "pages", []) or []:
        for item in [*(getattr(page, "texts", []) or []), *(getattr(page, "key_values", []) or [])]:
            evidence_ids.update(str(value) for value in (getattr(item, "evidence_ids", []) or []) if value)
    return {
        "field_source_coverage": round(sourced_fields / max(1, len(fields)), 4) if fields else 0.0,
        "record_source_coverage": round(sourced_records / max(1, len(records)), 4) if records else 0.0,
        "direct_evidence_id_count": len(evidence_ids),
    }


def _quality_summary(
    result: ParseResult,
    output: dict[str, Any],
    *,
    contract_status: str,
    missing_fields: list[str],
    missing_records: list[str],
) -> dict[str, Any]:
    data = output.get("data") if isinstance(output.get("data"), dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    records = data.get("records") if isinstance(data.get("records"), list) else []
    source_score = _source_quality(result)
    normalization_rate = _normalization_rate(records, fields)
    has_structured_content = any(
        bool(value)
        for key, value in data.items()
        if key
        not in {
            "fields",
            "records",
            "summary",
            "data_dictionary",
            "datasets",
            "field_details",
            "field_metadata",
            "field_schema",
            "normalized_fields",
        }
    )
    data_score = 1.0 if records else 0.85 if fields else 0.75 if has_structured_content else 0.0
    contract_score = {"pass": 1.0, "partial": 0.65, "fail": 0.25, "skip": 0.8}.get(contract_status, 0.6)
    score = round(
        0.35 * contract_score + 0.25 * data_score + 0.20 * normalization_rate + 0.20 * source_score,
        4,
    )
    status = output.get("status") if isinstance(output.get("status"), dict) else {}
    errors = list(status.get("errors") or [])
    review_warnings = [
        str(warning)
        for warning in (status.get("warnings") or [])
        if str(warning).startswith(
            (
                "uscc_checksum_invalid",
                "partial_",
                "missing_required_",
                "dec_validation:",
                "no_fields_extracted",
                "no_records_extracted",
                "cqf_",
                "precision:",
            )
        )
    ]
    has_data = bool(fields or records or has_structured_content)
    if errors or not has_data:
        readiness = "insufficient"
    elif review_warnings or missing_fields or missing_records or score < 0.8 or not bool(status.get("success", True)):
        readiness = "review"
    else:
        readiness = "ready"
    grade = "excellent" if score >= 0.9 else "good" if score >= 0.75 else "review" if score >= 0.5 else "insufficient"
    return {
        "score": score,
        "grade": grade,
        "readiness": readiness,
        "needs_review": readiness != "ready",
        "source_confidence": source_score,
        "normalization_rate": normalization_rate,
        "evidence": _evidence_quality(result, data),
    }


def _period_from_records(records: list[Any], summary: dict[str, Any]) -> dict[str, str]:
    period = summary.get("period") if isinstance(summary.get("period"), dict) else {}
    if period.get("start") or period.get("end"):
        return {key: str(value) for key, value in period.items() if value}
    dates: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        value = _record_value(record, "date", "timestamp", "transaction_date", "交易日期", "交易时间")
        if value:
            text = str(value)[:10]
            try:
                datetime.fromisoformat(text)
                dates.append(text)
            except ValueError:
                continue
    return {"start": min(dates), "end": max(dates)} if dates else {}


def _transaction_business(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    records = data.get("records") if isinstance(data.get("records"), list) else []
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    income = _as_float(summary.get("total_income"))
    expense = _as_float(summary.get("total_expense"))
    if income is None or expense is None:
        income = 0.0
        expense = 0.0
        for record in records:
            if not isinstance(record, dict):
                continue
            amount = _as_float(_record_value(record, "amount", "amount_cny", "金额", "交易金额"))
            direction = str(_record_value(record, "direction", "收/支", "收/支/其他") or "").lower()
            if amount is None:
                continue
            if direction in {"income", "收入", "存入", "credit"}:
                income += abs(amount)
            elif direction in {"expense", "支出", "取出", "debit"}:
                expense += abs(amount)
    income, expense = round(income or 0.0, 2), round(expense or 0.0, 2)

    counterparties: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"transaction_count": 0, "total_amount": 0.0}
    )
    transaction_types: Counter[str] = Counter()
    for record in records:
        if not isinstance(record, dict):
            continue
        party = str(_record_value(record, "counter_party", "对方户名", "交易对方", "对方") or "").strip()
        amount = _as_float(_record_value(record, "amount", "amount_cny", "金额", "交易金额")) or 0.0
        if party:
            counterparties[party]["transaction_count"] = int(counterparties[party]["transaction_count"]) + 1
            counterparties[party]["total_amount"] = round(float(counterparties[party]["total_amount"]) + abs(amount), 2)
        txn_type = str(_record_value(record, "transaction_type", "交易类型", "description", "商品说明") or "").strip()
        if txn_type:
            transaction_types[txn_type] += 1

    top_counterparties = [
        {"name": name, **values}
        for name, values in sorted(
            counterparties.items(),
            key=lambda item: (float(item[1]["total_amount"]), int(item[1]["transaction_count"])),
            reverse=True,
        )[:5]
    ]
    metrics = {
        "transaction_count": len(records),
        "total_income": income,
        "total_expense": expense,
        "net_flow": round(income - expense, 2),
    }
    dimensions: dict[str, Any] = {}
    if top_counterparties:
        dimensions["top_counterparties"] = top_counterparties
    if transaction_types:
        dimensions["top_transaction_types"] = [
            {"name": name, "transaction_count": count} for name, count in transaction_types.most_common(5)
        ]
    period = _period_from_records(records, summary)
    if period:
        dimensions["period"] = period
    return metrics, dimensions


def _build_business(output: dict[str, Any], domain: str, readiness: str) -> dict[str, Any]:
    data = output.get("data") if isinstance(output.get("data"), dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    records = data.get("records") if isinstance(data.get("records"), list) else []
    sections = data.get("sections") if isinstance(data.get("sections"), list) else []
    tables = data.get("tables") if isinstance(data.get("tables"), list) else []
    label = _DOMAIN_LABELS.get(domain, _DOMAIN_LABELS["generic"])
    document_type = str((output.get("document") or {}).get("document_type") or "")
    if domain == "generic" and document_type == "audit_report":
        label = "审计报告（通用处理）"
    metrics: dict[str, Any] = {}
    dimensions: dict[str, Any] = {}
    highlights: list[dict[str, Any]] = []

    if domain in {"bank_statement", "wechat_payment", "alipay_payment"}:
        metrics, dimensions = _transaction_business(data)
        summary = (
            f"已结构化 {metrics['transaction_count']} 笔交易；"
            f"收入 {metrics['total_income']:.2f} 元，支出 {metrics['total_expense']:.2f} 元，"
            f"净现金流 {metrics['net_flow']:.2f} 元。"
        )
    elif domain == "vat_invoice":
        total = _as_float(fields.get("total_amount"))
        without_tax = _as_float(fields.get("amount_without_tax"))
        tax = _as_float(fields.get("tax_amount"))
        line_items = data.get("line_items") if isinstance(data.get("line_items"), list) else []
        metrics = {
            "line_item_count": len(line_items),
            "total_amount": total,
            "amount_without_tax": without_tax,
            "tax_amount": tax,
        }
        if total is not None and without_tax is not None and tax is not None:
            difference = round(total - without_tax - tax, 2)
            dimensions["amount_reconciliation"] = {
                "status": "balanced" if abs(difference) <= 0.01 else "mismatch",
                "difference": difference,
                "unit": "CNY",
            }
        summary = f"已提取发票核心字段与 {len(line_items)} 条商品/服务明细。"
        if total is not None:
            summary += f"价税合计 {total:.2f} 元。"
    elif domain == "business_license":
        company = _unwrap(fields.get("company_name"))
        metrics = {"field_count": sum(1 for value in fields.values() if _present(value))}
        if "uscc_valid" in fields:
            highlights.append(
                {
                    "code": "uscc_checksum",
                    "label": "统一社会信用代码校验",
                    "status": "pass" if fields.get("uscc_valid") is True else "review",
                }
            )
        summary = (
            f"已形成“{company}”的工商主体档案，提取 {metrics['field_count']} 个业务字段。"
            if company
            else f"已形成工商主体档案，提取 {metrics['field_count']} 个业务字段。"
        )
    elif domain == "credit_report":
        accounts = data.get("credit_accounts") if isinstance(data.get("credit_accounts"), list) else []
        repayments = data.get("repayment_records") if isinstance(data.get("repayment_records"), list) else []
        overdue = data.get("overdue_records") if isinstance(data.get("overdue_records"), list) else []
        inquiries = data.get("inquiry_records") if isinstance(data.get("inquiry_records"), list) else []
        metrics = {
            "credit_account_count": len(accounts),
            "repayment_record_count": len(repayments),
            "overdue_record_count": len(overdue),
            "inquiry_record_count": len(inquiries),
            "section_count": len(sections),
        }
        summary = (
            f"已构建征信报告目录与主体信息，识别 {len(accounts)} 个信贷账户、"
            f"{len(repayments)} 条还款记录和 {len(sections)} 个章节。"
        )
    else:
        metrics = {
            "field_count": sum(1 for value in fields.values() if _present(value)),
            "record_count": len(records),
            "table_count": len(tables),
            "section_count": len(sections),
        }
        if metrics["field_count"] and metrics["record_count"]:
            shape = "mixed_document"
        elif metrics["record_count"]:
            shape = "tabular_document"
        elif metrics["field_count"]:
            shape = "key_value_document"
        elif metrics["section_count"]:
            shape = "report_document"
        else:
            shape = "unstructured_document"
        dimensions["adaptive_profile"] = {
            "document_shape": shape,
            "inferred_identities": len(data.get("identities") or {}),
            "inferred_columns": len(data.get("columns") or {}),
        }
        summary = (
            f"通用引擎自适应提取 {metrics['field_count']} 个字段、{metrics['table_count']} 张表、"
            f"{metrics['record_count']} 条记录和 {metrics['section_count']} 个章节。"
        )

    if readiness == "insufficient":
        summary += "当前可用信息不足，建议检查文档清晰度或解析范围。"
    elif readiness == "review":
        summary += "结果可用于预填与检索，关键缺失项建议复核。"
    else:
        summary += "结构完整，可直接用于检索、预填或下游规则处理。"

    return {
        "version": "community.business.v1",
        "derived": True,
        "derived_from": ["/data", "/quality/readiness"],
        "document_label": label,
        "summary": summary,
        "key_metrics": {key: value for key, value in metrics.items() if value is not None},
        "dimensions": dimensions,
        "highlights": highlights,
        "readiness_ref": "/quality/readiness",
    }


def _issue_parts(raw_code: str) -> tuple[str, str]:
    code, _, detail = raw_code.partition(":")
    return code or "unknown", detail


def _issue_target(code: str, detail: str, output: dict[str, Any] | None = None) -> str:
    if code == "missing_required_field" and detail:
        return f"/data/fields/{_pointer_token(detail)}"
    if code == "missing_required_record_field" and detail:
        return f"/data/records/*/normalized/{_pointer_token(detail)}"
    if code == "uscc_checksum_invalid":
        return "/data/fields/unified_social_credit_code"
    if code == "no_fields_extracted":
        return "/data/fields"
    if code == "no_records_extracted":
        return "/data/records"
    if code == "precision" and detail.startswith("generic_"):
        generic_code, _, target = detail.partition(":")
        if generic_code in {"generic_low_source_coverage", "generic_low_confidence_text_kv"}:
            return "/data/field_details"
        if generic_code in {"generic_ocr_required", "generic_ocr_fields_filtered"}:
            return "/data/fields"
        if generic_code in {"generic_normalization_failed", "generic_currency_unknown", "generic_ambiguous_type"}:
            return f"/data/columns/{_pointer_token(target)}" if target else "/data/columns"
        data = output.get("data") if isinstance(output, dict) and isinstance(output.get("data"), dict) else {}
        if generic_code == "generic_header_repaired" and target:
            tables = data.get("tables") if isinstance(data.get("tables"), list) else []
            table_index = next(
                (
                    index
                    for index, table in enumerate(tables)
                    if isinstance(table, dict) and str(table.get("table_id") or "") == target
                ),
                None,
            )
            if table_index is not None:
                return f"/data/tables/{table_index}"
        if generic_code == "generic_row_alignment_suspect" and target:
            table_id, _, raw_row = target.partition("@row=")
            records = data.get("records") if isinstance(data.get("records"), list) else []
            record_index = next(
                (
                    index
                    for index, record in enumerate(records)
                    if isinstance(record, dict)
                    and isinstance(record.get("source"), dict)
                    and str(record["source"].get("table_id") or "") == table_id
                    and (not raw_row or str(record["source"].get("table_row_index")) == raw_row)
                ),
                None,
            )
            if record_index is not None:
                return f"/data/records/{record_index}"
            return "/data/records"
        if generic_code in {
            "generic_header_repaired",
            "generic_header_repaired_ratio",
            "generic_text_table_low_confidence",
        }:
            return "/data/tables"
        if generic_code == "generic_page_reference_mismatch":
            return "/document/page_count"
    return "/quality"


def _issue_message(code: str, detail: str, output: dict[str, Any] | None = None) -> str:
    if code == "missing_required_field":
        return f"缺少必填字段：{_field_label(detail)}"
    if code == "missing_required_record_field":
        return f"明细记录缺少必填列：{_field_label(detail)}"
    if code == "partial_missing_required":
        return f"部分必填信息缺失：{detail or '请复核源文档'}"
    if code == "uscc_checksum_invalid":
        return "统一社会信用代码校验未通过"
    if code == "no_fields_extracted":
        return "未提取到可用字段"
    if code == "no_records_extracted":
        return "未提取到可用明细记录"
    if code == "community_generic_fallback":
        return "文档由通用结构化引擎处理"
    if code == "precision" and detail.startswith("generic_"):
        generic_code, _, target = detail.partition(":")
        messages = {
            "generic_low_source_coverage": "部分通用字段缺少页码、坐标或直接证据，建议核对原文",
            "generic_low_confidence_text_kv": "部分字段仅由全文行恢复，缺少页面坐标，建议核对原文",
            "generic_ambiguous_type": "列类型存在歧义，已保守按文本保留",
            "generic_normalization_failed": "部分值未通过标准化校验，已保留原文",
            "generic_header_repaired": "表头存在重复或空列名，已生成唯一列名以避免丢失单元格",
            "generic_header_repaired_ratio": "多张表格仍需表头复核",
            "generic_currency_unknown": "金额已解析，但源文档未明确币种",
            "generic_text_table_low_confidence": "表格由全文重复行恢复，列边界置信度较低",
            "generic_ocr_required": "扫描件没有可用文本层，请启用 --ocr auto 或 --ocr force",
            "generic_ocr_fields_filtered": "已过滤不满足标量字段约束的 OCR 候选",
            "generic_page_reference_mismatch": "证据页码超出文档页数，页面映射需要复核",
            "generic_row_alignment_suspect": "同一单元格疑似包含多条金额记录，建议核对行列对齐",
        }
        message = messages.get(generic_code, "通用结构化结果需要复核")
        if target and generic_code in {
            "generic_normalization_failed",
            "generic_header_repaired",
            "generic_header_repaired_ratio",
            "generic_currency_unknown",
            "generic_ocr_fields_filtered",
            "generic_page_reference_mismatch",
            "generic_row_alignment_suspect",
        }:
            message += f"：{target}"
        if generic_code == "generic_header_repaired_ratio" and isinstance(output, dict):
            data = output.get("data") if isinstance(output.get("data"), dict) else {}
            page_counts = Counter(
                int(page)
                for table in (data.get("tables") or [])
                if isinstance(table, dict) and table.get("header_repaired")
                for page in (table.get("source_pages") or [])
                if int(page) > 0
            )
            if page_counts:
                priority_pages = "、".join(f"{page}页({count}张)" for page, count in page_counts.most_common(5))
                message += f"；优先复核：{priority_pages}"
        return message
    if code.startswith("cqf_"):
        return f"文档结构质量需要复核：{detail or code}"
    if code == "dec_validation":
        return f"结构化结果校验提示：{detail}"
    return detail or code.replace("_", " ")


def _structured_issues(output: dict[str, Any]) -> list[dict[str, Any]]:
    status = output.get("status") if isinstance(output.get("status"), dict) else {}
    candidates: list[tuple[str, str]] = [
        *(("error", str(item)) for item in (status.get("errors") or [])),
        *(("warning", str(item)) for item in (status.get("warnings") or [])),
    ]

    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for default_severity, raw_code in candidates:
        code, detail = _issue_parts(raw_code)
        target = _issue_target(code, detail, output)
        marker = (raw_code, target)
        if marker in seen:
            continue
        seen.add(marker)
        severity = "info" if code in {"community_generic_fallback"} else default_severity
        issues.append(
            {
                "code": code,
                "severity": severity,
                "target": target,
                "message": _issue_message(code, detail, output),
                "action": "inspect_result" if severity == "info" else "review_source",
                "source_code": raw_code,
            }
        )
    return issues


class CommunityBusinessProjectionHook(PostExtractHook):
    """Add the stable consumer-facing layer to every Community projection."""

    hook_id = "community_business_projection"

    def apply(
        self,
        result: ParseResult,
        *,
        extracted: dict[str, Any],
        edition: str,
        document_type: str,
        plugin: Any | None = None,
    ) -> None:
        if edition != "community":
            return
        plugin_name = str((extracted.get("plugin") or {}).get("name") or "")
        domain = plugin_name if plugin_name and plugin_name != "generic" else "generic"
        if domain == "bank_reconciliation":
            domain = "bank_statement"

        data = extracted.setdefault("data", {})
        if domain == "vat_invoice":
            _deduplicate_vat_records(data)
            fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
            if "invoice_date" in fields and _unwrap(fields.get("invoice_date")) == _unwrap(fields.get("issue_date")):
                fields.pop("issue_date", None)
                field_metadata = data.get("field_metadata") if isinstance(data.get("field_metadata"), dict) else {}
                field_metadata.pop("issue_date", None)
        from docmirror.quality.field_details import compact_community_field_projection

        canonical_fields, field_details = compact_community_field_projection(data)
        data["fields"] = canonical_fields
        data["field_details"] = field_details
        from docmirror.plugins._base.community_reading_view import finalize_community_reading_view

        finalize_community_reading_view(result, data, domain)
        datasets = _build_dataset_catalog(data, domain)
        data["datasets"] = datasets
        data["data_dictionary"] = _build_data_dictionary(data, datasets)
        if domain == "generic":
            _correct_generic_currency_units(data)

        contract_status = "skip"
        missing_fields: list[str] = []
        missing_records: list[str] = []
        try:
            from docmirror.models.schemas.domain_contract_validator import apply_domain_contract_validation

            report = apply_domain_contract_validation(extracted, domain)
            contract_status = report.status
            missing_fields = list(report.missing_fields)
            missing_records = list(report.missing_records)
        except Exception:
            pass

        quality = _quality_summary(
            result,
            extracted,
            contract_status=contract_status,
            missing_fields=missing_fields,
            missing_records=missing_records,
        )
        if domain == "generic":
            _adjust_generic_quality(quality, extracted)
        existing_quality = extracted.get("quality") if isinstance(extracted.get("quality"), dict) else {}
        extracted["quality"] = {**existing_quality, **quality}
        for key in (
            "contract_status",
            "missing_required_fields",
            "missing_required_record_fields",
            "review_reasons",
        ):
            extracted["quality"].pop(key, None)
        extracted["business"] = _build_business(extracted, domain, quality["readiness"])
        extracted["quality"]["issues"] = _structured_issues(extracted)
        if domain == "generic":
            for key in _GENERIC_LEGACY_DATA_KEYS:
                data.pop(key, None)
        data.pop("field_metadata", None)
        extracted["$schema"] = "https://valuemapglobal.github.io/DocMirror/schemas/edition_community.schema.json"
        extracted["schema_version"] = "2.2"
        metadata = extracted.setdefault("metadata", {})
        if domain == "vat_invoice":
            metadata.pop("field_provenance", None)
        metadata.pop("business_projection_version", None)
        metadata.pop("data_dictionary_version", None)
        metadata["consumer_contract_version"] = "community.consumer.v2"
        metadata["community_contract"] = "6+1"
