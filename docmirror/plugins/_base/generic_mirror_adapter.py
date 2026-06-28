"""
Mirror → generic community v2.1 output adapter for non-premium classified types.

Maps a complete Mirror ``ParseResult`` into a structured community envelope with
heuristic column type detection, value standardization, and identity extraction.

Key changes in v2.1:
  - ``_type_detect_column`` infers column types (date/amount/phone/id/email/enum/text)
  - ``_standardize_value`` normalizes values by type (amount→float, date→ISO)
  - ``_extract_identities`` auto-detects name/id/phone/account fields by key pattern
  - ``records[].normalized`` is populated with typed values (was always empty)
  - ``columns`` metadata block added to output
  - ``identities`` block added to output

Pipeline role: ``runner._run_community_extract`` calls ``build_generic_community_output``
via ``generic.community_plugin`` when generic fallback is enabled.

Key exports: ``build_generic_community_output``.

Dependencies: stdlib ``re``, ``unicodedata`` only (no external models).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docmirror.models.edition_serializer import EditionContext, edition_serializer
from docmirror.models.entities.domain_result import DomainExtractionResult, DomainQuality
from docmirror.plugins._base import build_classification_block
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

_CURRENCY_SYMBOLS = {"¥": "CNY", "$": "USD", "€": "EUR", "£": "GBP", "￥": "CNY"}

ColumnType = str


def _type_detect_column(values: list[str]) -> tuple[ColumnType, float]:
    """Infer column type from its values using pattern voting.

    Samples up to 50 values for performance. Returns (type, confidence).
    If confidence < 0.6, returns ("text", confidence).
    """
    if not values:
        return ("text", 0.0)

    sample = [v.strip() for v in values[:50] if v and v.strip()
              and v not in ("-", "—")]

    if not sample:
        return ("text", 0.0)

    counts: dict[str, int] = {
        "datetime": 0, "date": 0, "time": 0,
        "amount": 0, "percentage": 0,
        "phone": 0, "id_number": 0, "account": 0, "email": 0,
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


def _standardize_value(raw: str, col_type: str) -> str | dict[str, Any]:
    """Standardize a single value based on its detected column type."""
    cleaned = raw.strip()
    if not cleaned:
        return cleaned

    if col_type == "amount":
        currency = "CNY"
        for sym, cur in _CURRENCY_SYMBOLS.items():
            if sym in cleaned:
                currency = cur
                break
        normalized = normalize_amount(cleaned)
        if normalized is not None:
            return {"value": normalized, "currency": currency}
        return cleaned

    if col_type in ("date", "datetime"):
        normalized = normalize_timestamp(cleaned)
        if normalized:
            return {"value": normalized}
        return cleaned

    if col_type == "percentage":
        try:
            pct_val = float(cleaned.replace("%", "").strip())
            return {"value": pct_val, "unit": "%"}
        except (ValueError, TypeError):
            pass

    if col_type == "phone":
        digits = re.sub(r"[^\d]", "", cleaned)
        if len(digits) == 11:
            return {"value": digits}
        return cleaned

    return cleaned


def _infer_column_types(
    tables: list[Any],
) -> dict[str, dict[str, Any]]:
    """Run column type detection on all tables."""
    col_values: dict[str, list[str]] = {}
    for table in tables:
        headers = list(getattr(table, "headers", None) or [])
        for row in getattr(table, "rows", []) or []:
            cells = [getattr(c, "text", str(c)) for c in getattr(row, "cells", [])]
            if not headers or len(headers) != len(cells):
                continue
            for h, c in zip(headers, cells):
                key = str(h).strip()
                if key not in col_values:
                    col_values[key] = []
                col_values[key].append(str(c))

    result: dict[str, dict[str, Any]] = {}
    for header, values in col_values.items():
        col_type, confidence = _type_detect_column(values)
        null_count = sum(1 for v in values if not v.strip())
        result[header] = {
            "type": col_type,
            "confidence": round(confidence, 3),
            "null_ratio": round(null_count / max(1, len(values)), 3),
        }
    return result


def _build_normalized_record(
    raw: dict[str, str],
    col_types: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the ``normalized`` block for a single record."""
    normalized: dict[str, Any] = {}
    for key, raw_val in raw.items():
        col_info = col_types.get(key, {})
        col_type = col_info.get("type", "text")
        if col_type == "text":
            normalized[key] = raw_val
        else:
            normalized[key] = _standardize_value(raw_val, col_type)
    return normalized


# ── Identity extraction ─────────────────────────────────────────────────────

_IDENTITY_KEY_MAP: list[tuple[str, list[str]]] = [
    ("name", ["姓名", "名称", "户名", "name", "Name", "客户", "customer",
              "申请人", "借款人", "被保证人", "甲方", "乙方", "丙方"]),
    ("id_number", ["身份证", "证件号", "ID", "证件号码", "统一社会信用代码",
                   "信用代码", "税号", "纳税人识别号", "营业执照号"]),
    ("phone", ["电话", "手机", "phone", "Phone", "联系电话", "Tel",
               "移动电话", "mobile", "Mobile"]),
    ("account", ["账号", "账户", "卡号", "account", "Account", "银行账号",
                 "银行卡号", "开户行账号"]),
    ("address", ["地址", "Address", "address", "住所", "住址", "通讯地址",
                 "注册地址", "办公地址"]),
    ("amount_total", ["合计", "总计", "total", "Total", "金额合计", "Sum",
                      "总额", "总金额", "小计"]),
]

_IDENTITY_VALUE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("phone", _PHONE_RE),
    ("id_number", _ID_NUM_RE),
    ("email", _EMAIL_RE),
    ("account", _ACCOUNT_RE),
]


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
            key_lower = key.lower().strip()
            for kw in keywords:
                if kw.lower() in key_lower:
                    identities[id_type] = {
                        "key": key, "value": str(value), "confidence": 0.85,
                    }
                    break
            if id_type in identities:
                break

    # Pass 2: Value-pattern matching
    for id_type, regex in _IDENTITY_VALUE_PATTERNS:
        if id_type in identities:
            continue
        for key, value in fields.items():
            str_val = str(value).strip()
            if regex.match(str_val):
                identities[id_type] = {
                    "key": key, "value": str_val, "confidence": 0.70,
                }
                break

    return identities


# ── Main builder ────────────────────────────────────────────────────────────


def _collect_entity_fields(parse_result: Any) -> dict[str, Any]:
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
            if value is not None and value != "":
                fields[str(key)] = value

    # Priority 2: general entities
    raw = getattr(entities, "entities", None)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if value is not None and value != "" and str(key) not in fields:
                fields[str(key)] = value

    # Priority 3: common structured attributes
    for attr in (
        "document_type", "period_start", "period_end",
        "institution", "account_number", "account_holder",
    ):
        val = getattr(entities, attr, None)
        if val is not None and val != "" and attr not in fields:
            fields[attr] = val

    # Priority 4: page-level key_values
    for page in getattr(parse_result, "pages", []) or []:
        for kv in getattr(page, "key_values", []) or []:
            key = (getattr(kv, "key", None) or "").strip()
            val = (getattr(kv, "value", None) or "").strip()
            if key and val and key not in fields:
                fields[key] = val

    return fields


def _collect_table_records(parse_result: Any) -> list[dict[str, Any]]:
    """Collect table records from ParseResult into raw rows."""
    from docmirror.structure.tables.access import get_logical_tables

    records: list[dict[str, Any]] = []
    logical = get_logical_tables(parse_result)
    if logical:
        tables = logical
    else:
        tables = []
        for page in getattr(parse_result, "pages", []) or []:
            tables.extend(getattr(page, "tables", []) or [])

    row_index = 0
    for table in tables:
        headers = list(getattr(table, "headers", None) or [])
        for row in getattr(table, "rows", []) or []:
            cells = [getattr(c, "text", str(c)) for c in getattr(row, "cells", [])]
            if not any(str(c).strip() for c in cells):
                continue
            row_index += 1
            if headers and len(headers) == len(cells):
                raw = {str(h): str(c) for h, c in zip(headers, cells)}
            else:
                raw = {f"col_{i}": str(c) for i, c in enumerate(cells)}
            records.append({"row_index": row_index, "raw": raw, "normalized": {}})
    return records


def _collect_structure_projected_records(parse_result: Any) -> list[dict[str, Any]]:
    """Project L1 regions via structure_project registry."""
    from docmirror.structure.ocr.structure_project import project_structure
    from docmirror.structure.ocr.structure_projectors import core as _core  # noqa: F401

    if hasattr(parse_result, "sync_page_canvases"):
        parse_result.sync_page_canvases()

    projected: list[dict[str, Any]] = []
    for page in getattr(parse_result, "pages", []) or []:
        canvas = getattr(page, "page_canvas", None)
        if canvas is None or not canvas.blocks:
            continue
        page_num = int(getattr(page, "page_number", 0) or 0)
        region_by_id = {r.region_id: r for r in canvas.regions}
        for block in canvas.blocks:
            ref = str(block.ref or "")
            if not ref.startswith("region:"):
                continue
            region_id = ref.split(":", 1)[1]
            region = region_by_id.get(region_id)
            if region is None:
                continue
            hint = block.schema_hint or "core.field_grid.kv_block"
            result = project_structure(region.structure, page=page_num, schema_hint=hint)
            if result.rejected or result.record is None:
                continue
            projected.append({
                **result.record,
                "block_id": block.block_id,
                "schema_hint": hint,
                "projection_completeness": result.completeness,
                "missing_fields": list(result.missing_fields),
            })
    return projected


def build_generic_community_output(
    parse_result: Any,
    detected_type: str,
    full_text: str = "",
) -> dict[str, Any]:
    """Build v2.1 community JSON using heuristic type detection and standardization."""
    fields = _collect_entity_fields(parse_result)
    records = _collect_table_records(parse_result)
    structure_records = _collect_structure_projected_records(parse_result)
    if structure_records:
        records = records + structure_records

    # ── Heuristic column type detection ──
    from docmirror.structure.tables.access import get_logical_tables

    all_tables = get_logical_tables(parse_result) or []
    if not all_tables:
        for page in getattr(parse_result, "pages", []) or []:
            all_tables.extend(getattr(page, "tables", []) or [])

    col_types = _infer_column_types(all_tables) if all_tables else {}

    # ── Build normalized records ──
    for record in records:
        raw = record.get("raw", {})
        if raw and col_types:
            record["normalized"] = _build_normalized_record(raw, col_types)

    # ── Identity extraction ──
    identities = _extract_identities(fields) if fields else {}

    # ── Assemble structured data ──
    file_path = getattr(parse_result, "file_path", "") or ""
    doc_name = Path(file_path).name if file_path else detected_type
    page_count = len(getattr(parse_result, "pages", []) or [])

    summary = {"total_rows": len(records)}
    if col_types:
        summary["inferred_columns"] = len(col_types)
    if identities:
        summary["inferred_identities"] = len(identities)

    warnings: list[str] = [_GENERIC_WARNING]
    if not fields and not records:
        warnings.append("no_fields_extracted")

    structured_data = {
        "records": records,
        "structure_projected_records": structure_records,
        "summary": summary,
        "sections": [], "tables": [], "line_items": [],
    }
    if col_types:
        structured_data["columns"] = col_types
    if identities:
        structured_data["identities"] = identities

    dec = DomainExtractionResult(
        document_type=detected_type,
        properties={},
        entities=fields,
        structured_data=structured_data,
        quality=DomainQuality(
            validation_passed=bool(fields or records),
            issues=[f"warning:{w}" for w in warnings],
        ),
        metadata={
            "classification": build_classification_block(
                document_type=detected_type,
                domain=detected_type,
                archetype="generic_mirror",
                match_method="generic_fallback",
                text=full_text,
                scene_keywords=(),
            ),
            "plugin": {
                "name": "generic",
                "display_name": "Generic Community",
                "version": "community-2.1",
                "support_level": "generic",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    ctx = EditionContext(
        edition="community",
        detected_type=detected_type,
        document_name=doc_name,
        page_count=page_count,
        plugin_display_name="Generic Community",
        scene_keywords=(),
    )

    output = edition_serializer(dec, context=ctx)

    metadata = output.setdefault("metadata", {})
    metadata["generic_route"] = "type_aware_fallback"
    if col_types:
        metadata["inferred_columns"] = len(col_types)
    if identities:
        metadata["inferred_identities"] = len(identities)

    return output
