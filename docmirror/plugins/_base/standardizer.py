"""
Community edition field standardizers — amounts, timestamps, and enums.

Lightweight normalization used by table parsers before records enter DEC/edition
output. Community scope is intentionally narrow: parse amounts to float, coerce
dates to ISO8601, and map Chinese enum labels to English tokens. Does not perform
quality scoring, business-rule validation, or redaction.

Pipeline role: ``BaseTableParser`` and bank-statement style parsers call these
functions while building ``normalized`` row dicts during recognition.

Key exports: ``normalize_amount``, ``normalize_timestamp``, ``normalize_enum``,
``extract_period``.

Dependencies: stdlib ``re``, ``datetime``, ``unicodedata`` only.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def normalize_amount(raw: str) -> float | None:
    """Normalize amount.

    - Remove \u00a5 \uffe5 , space
    - Remove leading +
    - Return float or None
    """
    cleaned = re.sub(r"[¥￥$€£₤₩,，\s元圆]", "", raw.strip())
    if not cleaned:
        return None
    cleaned = cleaned.lstrip("+")
    try:
        return round(float(cleaned), 2)
    except (ValueError, TypeError):
        return None


def normalize_timestamp(raw: str) -> str:
    """Normalize time format.

    支持格式：
    - 2022-01-01 10:30:39
    - 2022-01-01 10:30
    - 2022-01-01
    - 2022/01/01 10:30:39
    - 2022年01月01日 10:30:39
    - 2022-09-2810:30:39（支付宝/OCR 缺空格）
    """
    raw = raw.strip()
    if not raw:
        return ""

    # If already ISO8601 (contains T), return directly
    if re.match(r"^\d{4}-\d{2}-\d{2}T", raw):
        return raw

    # Normalize separators
    cleaned = raw.replace("/", "-").replace("年", "-").replace("月", "-").replace("日", " ").strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).isoformat()
        except ValueError:
            continue

    # Alipay/OCR: missing space between date and time, e.g. 2022-09-2810:30:39
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(\d{1,2}:\d{2}(?::\d{2})?)$", cleaned)
    if m:
        date_part, time_part = m.group(1), m.group(2)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(f"{date_part} {time_part}", fmt).isoformat()
            except ValueError:
                continue

    # Compact date: 20220505
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", cleaned)
    if m:
        try:
            return datetime.strptime(cleaned, "%Y%m%d").date().isoformat()
        except ValueError:
            pass

    # YYMMDD pipe ledger dates: 220401 → 2022-04-01
    m = re.match(r"^(\d{6})$", cleaned)
    if m:
        yy, mo, da = int(cleaned[0:2]), int(cleaned[2:4]), int(cleaned[4:6])
        if 1 <= mo <= 12 and 1 <= da <= 31:
            year = 2000 + yy if yy <= 69 else 1900 + yy
            if 2010 <= year <= 2035:
                return datetime(year, mo, da).date().isoformat()

    # Compact format: 20220928 103039
    m = re.match(r"(\d{4})(\d{2})(\d{2})\s*(\d{2})(\d{2})(\d{2})", cleaned)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T{m.group(4)}:{m.group(5)}:{m.group(6)}"

    return raw  # 无法标准化，保留原始值


def normalize_enum(raw: str, enum_map: dict[str, str]) -> str:
    """Normalize enum.

    :param raw: raw Chinese value
    :param enum_map: mapping table, e.g. {"收入": "income", "支出": "expense"}
    :returns: normalized English value, returns raw if unmatched
    """
    if not raw:
        return ""
    return enum_map.get(raw, raw)


def normalize_record(
    raw_txn: dict[str, str],
    col_map: dict[str, str],
    column_registry: dict,
    standard_fields: list[str],
) -> dict[str, Any]:
    """Normalize a single transaction record.

    :param raw_txn: raw row data, keys are header column names
    :param col_map: {standard_field: column_index} or {standard_field: original_header_name}
    :param column_registry: column mapping registry
    :param standard_fields: standardized field order
    :returns: normalized dict
    """
    normalized: dict[str, Any] = {}
    raw_by_field: dict[str, str] = {}

    # Convert col_map to {standard_field: raw_value}
    for field_name, col_ref in col_map.items():
        if isinstance(col_ref, int):
            # col_map is {field: index} format
            # Need to find the matching column in raw_txn
            pass
        else:
            # col_ref is the original column name
            raw_by_field[field_name] = raw_txn.get(col_ref, "")

    # If col_map is {field: index}, match using raw_txn keys
    if not raw_by_field:
        for raw_key, raw_val in raw_txn.items():
            for field_name, col_ref in col_map.items():
                if isinstance(col_ref, int):
                    # Cannot reverse column name from index, already missed
                    pass

    # More general: col_map is {standard_field: original_column_index}
    # While raw_txn keys are header column names (original names)
    # Need to establish bidirectional mapping: original_name <-> standard_field
    # Establish through column_registry

    # Approach: first find the raw value for each standard field
    keys_to_fields: dict[str, str] = {}
    for canonical_name, mapping in column_registry.items():
        keys_to_fields[canonical_name] = mapping.field

    for raw_key, raw_val in raw_txn.items():
        # Try matching canonical_name
        matched_field = None
        for canonical_name, mapping in column_registry.items():
            if raw_key == canonical_name or (mapping.aliases and raw_key in mapping.aliases):
                matched_field = mapping.field
                break
        # Substring match
        if matched_field is None:
            for canonical_name, mapping in column_registry.items():
                if canonical_name in raw_key or raw_key in canonical_name:
                    matched_field = mapping.field
                    break

        if matched_field:
            mapping = column_registry.get(
                next((k for k, v in column_registry.items() if v.field == matched_field), ""),
                None,
            )
            if mapping and mapping.enum_map:
                normalized[matched_field] = normalize_enum(raw_val, mapping.enum_map)
            elif mapping and mapping.field == "amount":
                normalized[matched_field] = normalize_amount(raw_val)
            elif mapping and mapping.field == "timestamp":
                normalized[matched_field] = normalize_timestamp(raw_val)
            else:
                normalized[matched_field] = raw_val
        else:
            # Unmatched fields, preserve as-is
            normalized[f"raw_{raw_key}"] = raw_val

    # Ensure all standard_fields have values
    for field in standard_fields:
        if field not in normalized:
            normalized[field] = "" if field != "amount" else None

    return normalized


def extract_period(text: str) -> str:
    """Extract query time period from full text."""
    m = re.search(
        r"(\d{4}[-./年]\d{1,2}[-./月]\d{1,2}日?\s*[~\-至]\s*\d{4}[-./年]\d{1,2}[-./月]\d{1,2}日?)",
        text,
    )
    return m.group(1) if m else ""
