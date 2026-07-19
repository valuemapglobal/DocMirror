# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical assembly and audit for Community credit-report business data.

Subtype adapters intentionally produce source-shaped candidate facts.  This
module is the single boundary that merges those candidates, adds a stable
``normalized`` view without removing legacy fields, and reports conflicts,
evidence coverage, reconciliation results, and document truncation.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from docmirror.plugins.credit_report.business_records import (
    derive_overdue_records,
    extract_native_credit_business,
)

_COLLECTION_ID_KEYS = {
    "credit_accounts": "account_id",
    "credit_lines": "credit_line_id",
    "repayment_records": "repayment_id",
    "overdue_records": "overdue_id",
    "inquiry_records": "inquiry_id",
    "public_records": "public_record_id",
}

_NORMALIZED_FIELDS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "credit_accounts": (
        ("account_id", ("account_id",)),
        ("account_type", ("account_type",)),
        ("institution", ("management_institution", "institution")),
        ("business_type", ("business_type",)),
        ("account_identifier", ("account_identifier",)),
        ("status", ("account_status", "status")),
        ("open_date", ("open_date",)),
        ("due_date", ("due_date",)),
        ("close_date", ("close_date",)),
        ("currency", ("currency",)),
        ("credit_limit", ("credit_limit",)),
        ("loan_amount", ("loan_amount",)),
        ("balance", ("balance",)),
        ("used_amount", ("used_amount",)),
        ("overdue_amount", ("overdue_amount",)),
        ("five_tier_class", ("five_tier_class",)),
        ("ever_overdue", ("ever_overdue",)),
        ("current_overdue", ("current_overdue",)),
        ("over_90_days", ("over_90_days",)),
        ("overdue_months", ("overdue_months_last_5y", "overdue_months")),
    ),
    "credit_lines": (
        ("credit_line_id", ("credit_line_id",)),
        ("account_id", ("account_id",)),
        ("facility_type", ("facility_type",)),
        ("total_limit", ("total_limit",)),
        ("used_limit", ("used_limit",)),
        ("available_limit", ("available_limit",)),
        ("currency", ("currency",)),
        ("amount_unit", ("amount_unit",)),
        ("status", ("account_status", "status")),
    ),
    "repayment_records": (
        ("repayment_id", ("repayment_id",)),
        ("account_id", ("account_id",)),
        ("grid_id", ("grid_id",)),
        ("year", ("year",)),
        ("month", ("month",)),
        ("status", ("status",)),
        ("overdue_amount", ("overdue_amount",)),
    ),
    "overdue_records": (
        ("overdue_id", ("overdue_id",)),
        ("account_id", ("account_id",)),
        ("period_scope", ("period_scope",)),
        ("year", ("year",)),
        ("month", ("month",)),
        ("overdue_level", ("overdue_level",)),
        ("overdue_amount", ("overdue_amount",)),
        ("overdue_months", ("overdue_months",)),
        ("five_tier_class", ("five_tier_class",)),
        ("current_overdue", ("current_overdue",)),
        ("over_90_days", ("over_90_days",)),
    ),
    "inquiry_records": (
        ("inquiry_id", ("inquiry_id",)),
        ("sequence", ("sequence",)),
        ("inquiry_type", ("inquiry_type",)),
        ("inquiry_date", ("inquiry_date",)),
        ("institution", ("institution",)),
        ("reason", ("reason",)),
    ),
    "public_records": (
        ("public_record_id", ("public_record_id",)),
        ("sequence", ("sequence",)),
        ("record_type", ("record_type",)),
        ("authority", ("authority",)),
        ("category", ("category",)),
        ("start_date", ("start_date",)),
        ("end_date", ("end_date",)),
        ("content", ("content",)),
    ),
}

_DATE_FIELDS = frozenset({"open_date", "due_date", "close_date", "inquiry_date", "start_date", "end_date"})
_NUMBER_FIELDS = frozenset(
    {
        "credit_limit",
        "loan_amount",
        "balance",
        "used_amount",
        "overdue_amount",
        "total_limit",
        "used_limit",
        "available_limit",
        "overdue_months",
        "overdue_level",
        "sequence",
        "year",
        "month",
    }
)
_MERGE_META_FIELDS = frozenset(
    {
        "normalized",
        "source_refs",
        "source_cell_refs",
        "source",
        "confidence",
        "extraction_status",
        "audit",
        "bbox",
        "page",
    }
)


def _plain(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("normalized_value", "value", "raw_value", "raw"):
        if value.get(key) not in (None, ""):
            return value[key]
    normalized = value.get("normalized")
    return normalized if not isinstance(normalized, dict) else None


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(_plain(value) or "")).upper()


def _identifier(value: Any) -> str:
    return re.sub(r"[^0-9A-Z]", "", _compact(value))


def _stable_id(prefix: str, *parts: Any) -> str:
    identity = "|".join(_compact(part) for part in parts)
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _number(value: Any) -> int | float | None:
    value = _plain(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    raw = re.sub(r"[^0-9.-]", "", str(value or "").replace(",", ""))
    if not raw or raw in {"-", ".", "-."}:
        return None
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    return int(number) if number == number.to_integral_value() else float(number)


def _date(value: Any) -> str:
    raw = str(_plain(value) or "").strip()
    match = re.search(r"(20\d{2})[年./-]\s*(\d{1,2})[月./-]\s*(\d{1,2})(?:日)?", raw)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"(20\d{2})[年./-]\s*(\d{1,2})(?:月)?", raw)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
    return raw


def _normalized_value(field: str, value: Any) -> Any:
    value = _plain(value)
    if value in (None, ""):
        return None
    if field in _DATE_FIELDS:
        return _date(value)
    if field in _NUMBER_FIELDS:
        number = _number(value)
        return number if number is not None else value
    if isinstance(value, str):
        return value.strip()
    return value


def _grid_id(record: dict[str, Any]) -> str:
    if record.get("grid_id"):
        return str(record["grid_id"])
    refs = record.get("source_cell_refs") if isinstance(record.get("source_cell_refs"), list) else []
    first = refs[0] if refs and isinstance(refs[0], dict) else {}
    return str(first.get("grid_id") or "")


def _ensure_record_id(collection: str, record: dict[str, Any], index: int) -> None:
    id_key = _COLLECTION_ID_KEYS[collection]
    if record.get(id_key):
        return
    if collection == "credit_accounts":
        anchor = record.get("account_identifier") or record.get("source_structure_id")
        if anchor:
            record[id_key] = f"credit_account:{_identifier(anchor)}"
        else:
            record[id_key] = _stable_id(
                "credit_account",
                record.get("management_institution"),
                record.get("open_date"),
                record.get("business_type"),
                record.get("sequence") or index,
            )
    elif collection == "repayment_records":
        grid_id = _grid_id(record)
        if grid_id:
            record.setdefault("grid_id", grid_id)
        record[id_key] = _stable_id(
            "credit_repayment",
            record.get("account_id") or grid_id,
            record.get("year"),
            record.get("month"),
        )
    else:
        prefix = {
            "credit_lines": "credit_line",
            "overdue_records": "credit_overdue",
            "inquiry_records": "credit_inquiry",
            "public_records": "public_record",
        }[collection]
        record[id_key] = _stable_id(prefix, collection, index, _business_identity(record))


def _business_identity(record: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        _compact(record.get(key))
        for key in sorted(record)
        if key not in _MERGE_META_FIELDS and record.get(key) not in (None, "")
    )


def _natural_key(collection: str, record: dict[str, Any], index: int) -> tuple[Any, ...]:
    if collection == "credit_accounts":
        account_identifier = _identifier(record.get("account_identifier"))
        if account_identifier:
            return (collection, "account_identifier", account_identifier)
        source_structure_id = _compact(record.get("source_structure_id"))
        if source_structure_id:
            return (collection, "source_structure_id", source_structure_id)
    if collection == "repayment_records":
        grid_id = _grid_id(record)
        return (
            collection,
            _compact(record.get("account_id") or grid_id),
            _number(record.get("year")),
            _number(record.get("month")),
        )
    id_key = _COLLECTION_ID_KEYS[collection]
    record_id = _compact(record.get(id_key))
    if record_id:
        return (collection, id_key, record_id)
    return (collection, index, _business_identity(record))


def _source_rank(record: dict[str, Any]) -> int:
    source_text = " ".join(
        [
            str(record.get("source") or ""),
            *[str(ref.get("source") or "") for ref in record.get("source_refs") or [] if isinstance(ref, dict)],
        ]
    ).lower()
    if any(marker in source_text for marker in ("field_grid", "local_structure", "typed_cell", "micro_grid")):
        return 3
    if any(marker in source_text for marker in ("table", "ledger")):
        return 2
    if any(marker in source_text for marker in ("native_text", "narrative", "account_history")):
        return 1
    return 0


def _valid_field_value(field: str, value: Any) -> bool:
    value = _plain(value)
    if value in (None, ""):
        return False
    if field in _DATE_FIELDS:
        return bool(re.fullmatch(r"20\d{2}-\d{2}(?:-\d{2})?", _date(value)))
    if field in _NUMBER_FIELDS:
        return _number(value) is not None
    return True


def _value_score(record: dict[str, Any], field: str, value: Any) -> tuple[int, int, float, str]:
    try:
        confidence = float(record.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    serial = json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, default=str)
    return (_source_rank(record), int(_valid_field_value(field, value)), confidence, serial)


def _merge_refs(*records: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        refs = list(record.get("source_refs") or [])
        for cell_ref in record.get("source_cell_refs") or []:
            if isinstance(cell_ref, dict):
                refs.append({"source": "repayment_micro_grid", **cell_ref})
        if not refs and (record.get("source") or record.get("page") or record.get("source_structure_id")):
            ref: dict[str, Any] = {"source": record.get("source") or "credit_business_projection"}
            if record.get("page"):
                ref["page"] = record["page"]
            if record.get("source_structure_id"):
                ref["structure_id"] = record["source_structure_id"]
            refs.append(ref)
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            marker = json.dumps(ref, ensure_ascii=False, sort_keys=True, default=str)
            if marker in seen:
                continue
            seen.add(marker)
            out.append(dict(ref))
    return out


def _merge_record(
    collection: str,
    natural_key: tuple[Any, ...],
    current: dict[str, Any],
    candidate: dict[str, Any],
    conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    merged = dict(current)
    for field, value in candidate.items():
        if field in _MERGE_META_FIELDS or value in (None, ""):
            continue
        old = merged.get(field)
        if old in (None, ""):
            merged[field] = value
            continue
        if _plain(old) == _plain(value):
            continue
        old_score = _value_score(current, field, old)
        new_score = _value_score(candidate, field, value)
        chosen = value if new_score > old_score else old
        merged[field] = chosen
        conflicts.append(
            {
                "collection": collection,
                "natural_key": list(natural_key),
                "field": field,
                "candidates": [_plain(old), _plain(value)],
                "resolved_value": _plain(chosen),
                "resolution": "source_type_validity_confidence",
            }
        )
    merged["source_refs"] = _merge_refs(current, candidate)
    merged["confidence"] = max(
        float(current.get("confidence") or 0.0),
        float(candidate.get("confidence") or 0.0),
    )
    return merged


def _normalize_record(collection: str, record: dict[str, Any], index: int) -> dict[str, Any]:
    out = dict(record)
    _ensure_record_id(collection, out, index)
    refs = _merge_refs(out)
    if refs:
        out["source_refs"] = refs
    normalized: dict[str, Any] = {}
    for target, aliases in _NORMALIZED_FIELDS[collection]:
        value = next((out.get(alias) for alias in aliases if out.get(alias) not in (None, "")), None)
        value = _normalized_value(target, value)
        if value not in (None, ""):
            normalized[target] = value
    out["normalized"] = normalized
    try:
        confidence = max(0.0, min(1.0, float(out.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    out["confidence"] = confidence
    out.setdefault("extraction_status", "accepted" if confidence >= 0.8 and refs else "review")
    return out


def _merge_collection(
    collection: str,
    sources: list[list[Any]],
    conflicts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: dict[tuple[Any, ...], dict[str, Any]] = {}
    order: list[tuple[Any, ...]] = []
    occurrence: dict[tuple[Any, ...], int] = {}
    for source in sources:
        for source_index, item in enumerate(source or [], start=1):
            if not isinstance(item, dict):
                continue
            candidate = dict(item)
            _ensure_record_id(collection, candidate, source_index)
            key = _natural_key(collection, candidate, source_index)
            if key not in records:
                order.append(key)
                records[key] = candidate
                occurrence[key] = 1
                continue
            records[key] = _merge_record(collection, key, records[key], candidate, conflicts)
            occurrence[key] += 1
    return [_normalize_record(collection, records[key], index) for index, key in enumerate(order, start=1)]


def _source_page_count(parse_result: Any) -> tuple[int | None, str]:
    parser_info = getattr(parse_result, "parser_info", None)
    structure = getattr(parser_info, "structure", None) or {}
    if isinstance(structure, dict) and structure.get("source_page_count") is not None:
        return int(structure["source_page_count"]), "parser_info.structure"
    provenance = getattr(parse_result, "provenance", None)
    properties = getattr(provenance, "document_properties", None) or {}
    if isinstance(properties, dict) and properties.get("source_page_count") is not None:
        return int(properties["source_page_count"]), "provenance.document_properties"
    file_path = str(getattr(parse_result, "file_path", "") or "")
    if file_path.lower().endswith(".pdf") and Path(file_path).is_file():
        try:
            from pypdf import PdfReader

            return len(PdfReader(file_path).pages), "pdf_page_tree"
        except Exception:
            pass
    return None, "unknown"


def _document_completeness(parse_result: Any) -> dict[str, Any]:
    pages = list(getattr(parse_result, "pages", []) or [])
    source_pages = {
        int(getattr(page, "source_page_number", 0) or getattr(page, "page_number", 0) or index)
        for index, page in enumerate(pages, start=1)
    }
    source_pages.discard(0)
    parsed_source_page_count = len(source_pages)
    source_page_count, basis = _source_page_count(parse_result)
    if source_page_count is not None:
        complete = parsed_source_page_count >= source_page_count
    else:
        parser_info = getattr(parse_result, "parser_info", None)
        options = getattr(parser_info, "options", None) or {}
        control = options.get("parse_control") if isinstance(options, dict) else None
        pages_control = control.get("pages") if isinstance(control, dict) else None
        explicitly_selected = bool(
            isinstance(pages_control, dict)
            and any(pages_control.get(key) not in (None, "", [], ()) for key in ("ranges", "max_pages", "last_pages"))
        )
        complete = not explicitly_selected
        basis = "parse_control_selection" if explicitly_selected else basis
    return {
        "document_complete": complete,
        "parsed_source_page_count": parsed_source_page_count,
        "source_page_count": source_page_count,
        "completeness_basis": basis,
    }


def _quarantined_fields(collections: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for collection, records in collections.items():
        id_key = _COLLECTION_ID_KEYS[collection]
        for record in records:
            audit = record.get("audit") if isinstance(record.get("audit"), dict) else {}
            for reason_key in ("quarantined_fields", "type_mismatch"):
                for field in audit.get(reason_key) or []:
                    out.append(
                        {
                            "collection": collection,
                            "record_id": record.get(id_key),
                            "field": str(field),
                            "reason": reason_key,
                        }
                    )
    return out


def _build_audit(
    *,
    parse_result: Any,
    report_subtype: str,
    content_mode: str,
    collections: dict[str, list[dict[str, Any]]],
    conflicts: list[dict[str, Any]],
    credit_summary: dict[str, Any],
) -> dict[str, Any]:
    completeness = _document_completeness(parse_result)
    quarantined = _quarantined_fields(collections)
    collection_audit: dict[str, Any] = {}
    issues: list[str] = []
    for name, records in collections.items():
        with_evidence = sum(bool(record.get("source_refs") or record.get("source_cell_refs")) for record in records)
        evidence_coverage = round(with_evidence / len(records), 4) if records else 1.0
        collection_conflicts = sum(item.get("collection") == name for item in conflicts)
        collection_audit[name] = {
            "count": len(records),
            "evidence_coverage": evidence_coverage,
            "normalized_coverage": round(sum(bool(record.get("normalized")) for record in records) / len(records), 4)
            if records
            else 1.0,
            "conflict_count": collection_conflicts,
        }
        if records and evidence_coverage < 1.0:
            issues.append(f"missing_evidence:{name}")
    reconciliations: list[dict[str, Any]] = []
    expected_accounts = credit_summary.get("account_count")
    if expected_accounts is None:
        expected_accounts = credit_summary.get("extracted_account_count")
    if expected_accounts is not None:
        actual_accounts = len(collections["credit_accounts"])
        matched = _number(expected_accounts) == actual_accounts
        reconciliations.append(
            {
                "name": "credit_account_count",
                "expected": _number(expected_accounts),
                "actual": actual_accounts,
                "matched": matched,
            }
        )
        if not matched:
            issues.append("reconciliation_failed:credit_account_count")
    if not completeness["document_complete"]:
        issues.append("document_truncated")
    if conflicts:
        issues.append("candidate_conflicts")
    if quarantined:
        issues.append("quarantined_fields")
    return {
        "schema_version": "credit_business.v1",
        "report_subtype": report_subtype,
        "content_mode": content_mode,
        **completeness,
        "status": "pass" if not issues else "review",
        "collections": collection_audit,
        "conflicts": conflicts,
        "reconciliations": reconciliations,
        "quarantined_fields": quarantined,
        "issues": issues,
    }


def assemble_credit_report_business(
    parse_result: Any,
    full_text: str,
    *,
    report_subtype: str,
    content_mode: str,
    existing_collections: dict[str, list[Any]] | None = None,
    existing_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble subtype candidates into one backward-compatible business view."""
    existing_collections = existing_collections or {}
    native = extract_native_credit_business(
        parse_result,
        full_text,
        report_subtype=report_subtype,
        content_mode=content_mode,
    )
    conflicts: list[dict[str, Any]] = []
    collections: dict[str, list[dict[str, Any]]] = {}
    for collection in _COLLECTION_ID_KEYS:
        if collection == "overdue_records":
            continue
        collections[collection] = _merge_collection(
            collection,
            [
                list(existing_collections.get(collection) or []),
                list(native.get(collection) or []),
            ],
            conflicts,
        )
    overdue_candidates = derive_overdue_records(
        collections["credit_accounts"],
        collections["repayment_records"],
        [
            *list(existing_collections.get("overdue_records") or []),
            *list(native.get("overdue_records") or []),
        ],
    )
    collections["overdue_records"] = _merge_collection(
        "overdue_records",
        [overdue_candidates],
        conflicts,
    )
    # Keep a stable public collection order in the returned mapping and audit.
    collections = {name: collections[name] for name in _COLLECTION_ID_KEYS}

    native_summary = native.get("credit_summary") if isinstance(native.get("credit_summary"), dict) else {}
    credit_summary = {
        **dict(existing_summary or {}),
        **dict(native_summary),
        "projected_account_count": len(collections["credit_accounts"]),
    }
    audit = _build_audit(
        parse_result=parse_result,
        report_subtype=report_subtype,
        content_mode=content_mode,
        collections=collections,
        conflicts=conflicts,
        credit_summary=credit_summary,
    )
    return {
        **collections,
        "credit_summary": credit_summary,
        "credit_extraction_audit": audit,
    }


__all__ = ["assemble_credit_report_business"]
