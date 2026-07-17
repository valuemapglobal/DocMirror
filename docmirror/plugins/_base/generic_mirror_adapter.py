"""
Mirror → generic community v2.2 output adapter for non-core and unclassified types.

Maps a complete Mirror ``ParseResult`` into a structured community envelope with
heuristic column type detection, value standardization, and identity extraction.

Key capabilities in v2.2:
  - ``_type_detect_column`` infers column types (date/amount/phone/id/email/enum/text)
  - ``_standardize_value`` normalizes values by type (amount→float, date→ISO)
  - ``_extract_identities`` auto-detects name/id/phone/account fields by key pattern
  - ``records[].normalized`` is populated with typed values (was always empty)
  - ``columns`` metadata block added to output
  - ``identities`` block added to output
  - text KV, outline, source metadata, and repeated-row recovery fallbacks

Pipeline role: ``runner._run_community_extract`` calls ``build_generic_community_output``
via ``generic.community_plugin`` when generic fallback is enabled.

Key exports: ``build_generic_community_output``.

Dependencies: stdlib ``re``, ``unicodedata`` only (no external models).
"""

from __future__ import annotations

import re
from collections import Counter
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

_INTERNAL_ENTITY_KEYS = frozenset(
    {
        "plugin_document_type",
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
    }
)
_TEXT_KV_RE = re.compile(r"^\s*([^:：]{1,40})\s*[:：]\s*(\S.{0,499}|\S)\s*$")

ColumnType = str


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


def _infer_record_column_types(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Infer columns from standard records when source tables have no headers."""
    values: dict[str, list[str]] = {}
    for record in records:
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        for key, value in raw.items():
            values.setdefault(str(key), []).append(str(value or ""))
    columns: dict[str, dict[str, Any]] = {}
    for key, samples in values.items():
        column_type, confidence = _type_detect_column(samples)
        columns[key] = {
            "type": column_type,
            "confidence": round(confidence, 3),
            "null_ratio": round(sum(1 for value in samples if not value.strip()) / max(1, len(samples)), 3),
        }
    return columns


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


def _is_public_field(key: Any, value: Any) -> bool:
    """Keep business facts out of Mirror/runtime implementation metadata."""
    name = str(key or "").strip()
    if not name or name.startswith("_") or name in _INTERNAL_ENTITY_KEYS:
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
    fields: dict[str, str] = {}
    for line in (full_text or "").splitlines():
        match = _TEXT_KV_RE.match(line)
        if not match:
            continue
        key, value = match.group(1).strip(), match.group(2).strip()
        if key.lower() in {"http", "https"} or any(ch in key for ch in ("。", "！", "？", "?", "!")):
            continue
        if key and value and key not in fields:
            fields[key] = value
        if len(fields) >= 200:
            break
    return fields


def _recover_repeated_text_records(
    full_text: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any] | None]:
    """Recover a conservative row grid from repeated date-led text sequences.

    This is the last safety net for PDFs whose table geometry was lost but whose
    reading order still repeats a stable row width.  Requiring at least three
    date anchors and a dominant width avoids turning ordinary prose into rows.
    """
    tokens = [line.strip() for line in (full_text or "").splitlines() if line.strip()]
    date_indexes = [index for index, token in enumerate(tokens) if _DATE_RE.match(token) or _DATETIME_RE.match(token)]
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
    )
    headers = header_candidates if useful_headers else [f"col_{index}" for index in range(width)]
    raw_rows: list[dict[str, str]] = []
    for anchor in date_indexes:
        cells = tokens[anchor : anchor + width]
        if len(cells) != width:
            continue
        raw_rows.append({header: cell for header, cell in zip(headers, cells)})
    if len(raw_rows) < 3:
        return [], {}, None

    column_values = {header: [row[header] for row in raw_rows] for header in headers}
    columns: dict[str, dict[str, Any]] = {}
    for header, values in column_values.items():
        column_type, confidence = _type_detect_column(values)
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
    text = str(value or "").strip()
    key_lower = key.lower()
    if any(token in key_lower for token in ("金额", "合计", "总额", "amount", "total", "price", "余额")):
        if _AMOUNT_RE.match(text):
            return "amount", 0.95
    inferred, confidence = _type_detect_column([text])
    return inferred, confidence


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


def _collect_field_metadata(parse_result: Any, fields: dict[str, Any]) -> dict[str, Any]:
    """Attach page/bbox/evidence to generic KV facts without changing field values."""
    metadata: dict[str, Any] = {}
    wanted = set(fields)
    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        for kv in getattr(page, "key_values", []) or []:
            key = str(getattr(kv, "key", "") or "").strip()
            if key not in wanted or key in metadata:
                continue
            item: dict[str, Any] = {
                "source": "mirror_key_value",
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
        ["身份证", "证件号", "ID", "证件号码", "统一社会信用代码", "信用代码", "税号", "纳税人识别号", "营业执照号"],
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
            str_val = str(value).strip()
            if regex.match(str_val):
                identities[id_type] = {
                    "key": key,
                    "value": str_val,
                    "confidence": 0.70,
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
            if _is_public_field(key, value):
                fields[str(key)] = value

    # Priority 2: general entities
    raw = getattr(entities, "entities", None)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if _is_public_field(key, value) and str(key) not in fields:
                fields[str(key)] = value

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
            key = (getattr(kv, "key", None) or "").strip()
            val = (getattr(kv, "value", None) or "").strip()
            if key and val and key not in fields:
                fields[key] = val

    return fields


def _collect_table_records(parse_result: Any) -> list[dict[str, Any]]:
    """Collect table records from ParseResult into raw rows."""
    from docmirror.tables.access import get_logical_tables

    records: list[dict[str, Any]] = []
    logical = get_logical_tables(parse_result)
    if logical:
        tables: list[tuple[Any, list[int]]] = [
            (table, list(getattr(table, "source_pages", []) or [])) for table in logical
        ]
    else:
        tables = []
        for page in getattr(parse_result, "pages", []) or []:
            page_number = int(getattr(page, "page_number", 0) or 0)
            tables.extend((table, [page_number] if page_number else []) for table in getattr(page, "tables", []) or [])

    row_index = 0
    for table_index, (table, source_pages) in enumerate(tables):
        headers = list(getattr(table, "headers", None) or [])
        table_id = str(getattr(table, "logical_id", "") or getattr(table, "table_id", "") or f"table_{table_index}")
        provenance = list(getattr(table, "provenance", []) or [])
        for table_row_index, row in enumerate(getattr(table, "rows", []) or []):
            cells = [getattr(c, "text", str(c)) for c in getattr(row, "cells", [])]
            if not any(str(c).strip() for c in cells):
                continue
            row_index += 1
            if headers and len(headers) == len(cells):
                raw = {str(h): str(c) for h, c in zip(headers, cells)}
            else:
                raw = {f"col_{i}": str(c) for i, c in enumerate(cells)}
            source: dict[str, Any] = {"table_id": table_id, "table_row_index": table_row_index}
            if table_row_index < len(provenance):
                prov = provenance[table_row_index]
                prov_page = int(getattr(prov, "source_page", 0) or 0)
                if prov_page:
                    source["page"] = prov_page
                physical_id = str(getattr(prov, "source_table_id", "") or "")
                if physical_id:
                    source["physical_table_id"] = physical_id
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


def _collect_table_descriptors(parse_result: Any) -> list[dict[str, Any]]:
    """Describe every logical/physical table so records remain navigable."""
    from docmirror.tables.access import get_logical_tables

    logical = get_logical_tables(parse_result) or []
    descriptors: list[dict[str, Any]] = []
    if logical:
        for index, table in enumerate(logical):
            rows = list(getattr(table, "rows", []) or [])
            descriptors.append(
                {
                    "table_id": str(
                        getattr(table, "logical_id", "") or getattr(table, "table_id", "") or f"table_{index}"
                    ),
                    "kind": "logical_table",
                    "headers": [str(item) for item in (getattr(table, "headers", []) or [])],
                    "row_count": len(rows),
                    "source_pages": list(getattr(table, "source_pages", []) or []),
                    "merge_confidence": round(float(getattr(table, "merge_confidence", 0.0) or 0.0), 4),
                }
            )
        return descriptors

    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        for table_index, table in enumerate(getattr(page, "tables", []) or []):
            descriptors.append(
                {
                    "table_id": str(getattr(table, "table_id", "") or f"p{page_number}_table_{table_index}"),
                    "kind": "physical_table",
                    "headers": [str(item) for item in (getattr(table, "headers", []) or [])],
                    "row_count": len(getattr(table, "rows", []) or []),
                    "source_pages": [page_number],
                    "confidence": round(float(getattr(table, "confidence", 0.0) or 0.0), 4),
                }
            )
    return descriptors


def _collect_sections(parse_result: Any) -> list[dict[str, Any]]:
    """Create a compact document outline from sections and heading text blocks."""
    sections: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, section in enumerate(getattr(parse_result, "sections", []) or []):
        title = str(
            (section.get("title") or section.get("name") or "")
            if isinstance(section, dict)
            else (getattr(section, "title", "") or getattr(section, "name", "") or "")
        ).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        sections.append(
            {
                "id": str(section.get("id") if isinstance(section, dict) else getattr(section, "id", ""))
                or f"section_{index}",
                "title": title,
                "page_start": int(
                    (section.get("page_start", 1) if isinstance(section, dict) else getattr(section, "page_start", 1))
                    or 1
                ),
            }
        )

    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        for text in getattr(page, "texts", []) or []:
            content = str(getattr(text, "content", "") or "").strip()
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
            }
            bbox = getattr(text, "bbox", None)
            if bbox:
                item["bbox"] = list(bbox)
            sections.append(item)
    return sections


def _collect_structure_projected_records(parse_result: Any) -> list[dict[str, Any]]:
    """Project L1 regions via structure_project registry."""
    from docmirror.models.mirror.vnext_access import pages as vnext_pages
    from docmirror.models.mirror.vnext_access import resolve_ref
    from docmirror.ocr.structure_project import project_structure
    from docmirror.ocr.structure_projectors import core as _core  # noqa: F401

    projected: list[dict[str, Any]] = []
    if not hasattr(parse_result, "to_mirror_json_vnext"):
        return projected
    mirror = parse_result.to_mirror_json_vnext()
    if not isinstance(mirror, dict):
        return projected

    for page in vnext_pages(mirror):
        if not isinstance(page, dict):
            continue
        page_num = int(page.get("page_number") or 0)
        for block in page.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            ref = str(block.get("ref") or "")
            if not ref.startswith("region:"):
                continue
            region = resolve_ref(mirror, page_num, ref)
            if not isinstance(region, dict):
                continue
            structure = region.get("structure")
            if not isinstance(structure, dict):
                continue
            hint = str(block.get("schema_hint") or region.get("schema_hint") or "core.field_grid.kv_block")
            result = project_structure(structure, page=page_num, schema_hint=hint)
            if result.rejected or result.record is None:
                continue
            projected.append(
                {
                    **result.record,
                    "block_id": block.get("block_id") or block.get("id"),
                    "schema_hint": hint,
                    "projection_completeness": result.completeness,
                    "missing_fields": list(result.missing_fields),
                }
            )
    return projected


def build_generic_community_output(
    parse_result: Any,
    detected_type: str,
    full_text: str = "",
) -> dict[str, Any]:
    """Build v2.2 adaptive Community JSON from any usable Mirror document."""
    fields = _collect_entity_fields(parse_result)
    for key, value in _collect_text_key_values(full_text).items():
        fields.setdefault(key, value)
    records = _collect_table_records(parse_result)
    recovered_records: list[dict[str, Any]] = []
    recovered_columns: dict[str, dict[str, Any]] = {}
    recovered_table: dict[str, Any] | None = None
    if not records:
        recovered_records, recovered_columns, recovered_table = _recover_repeated_text_records(full_text)
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
    from docmirror.tables.access import get_logical_tables

    all_tables = get_logical_tables(parse_result) or []
    if not all_tables:
        for page in getattr(parse_result, "pages", []) or []:
            all_tables.extend(getattr(page, "tables", []) or [])

    col_types = _infer_column_types(all_tables) if all_tables else {}
    if not col_types and records:
        col_types = _infer_record_column_types(records)
    for key, value in recovered_columns.items():
        col_types.setdefault(key, value)

    # ── Build normalized records ──
    for record in records:
        raw = record.get("raw", {})
        if raw and col_types:
            record["normalized"] = _build_normalized_record(raw, col_types)

    # ── Identity extraction ──
    identities = _extract_identities(fields) if fields else {}
    normalized_fields, field_schema = _build_field_intelligence(fields)
    field_metadata = _collect_field_metadata(parse_result, fields)
    sections = _collect_sections(parse_result)
    table_descriptors = _collect_table_descriptors(parse_result)
    if recovered_table is not None:
        table_descriptors.append(recovered_table)

    # ── Assemble structured data ──
    file_path = getattr(parse_result, "file_path", "") or ""
    doc_name = Path(file_path).name if file_path else detected_type
    page_count = len(getattr(parse_result, "pages", []) or [])

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
                matched=detected_type not in {"", "unknown", "generic"},
            ),
            "plugin": {
                "name": "generic",
                "display_name": "Generic Community",
                "version": "community-2.2",
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
    metadata["generic_route"] = "adaptive_structured_fallback"
    metadata["adaptive_features"] = [
        "text_kv_recovery",
        "field_type_inference",
        "value_normalization",
        "identity_discovery",
        "table_schema_inference",
        "repeated_row_recovery",
        "document_outline",
        "source_metadata",
    ]
    if col_types:
        metadata["inferred_columns"] = len(col_types)
    if identities:
        metadata["inferred_identities"] = len(identities)

    return output
