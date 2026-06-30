# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Raw-Normalized Preservation Contract — QTC §6.4.

All business fields must follow this contract:
- raw: the original extracted value
- normalized: the standardized value (may be null if normalization fails)
- normalizer: identifier of the normalization function used
- confidence: 0.0–1.0 confidence score
- source_refs: evidence references (page, bbox, cell, token)
- review: auto_accepted | manual_optional | needs_review | needs_evidence

Design reference: docs/design/GA1.0/08_accuracy_trust_ga_gap_closure_plan.md §6.4
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FieldDetail:
    """Unified field-level contract: raw value, normalized form, evidence, confidence, and review status.

    This is the canonical field representation in the QTC. Every P0 key field
    (amount, date, account, serial number, invoice number, etc.) must carry
    these details. The `raw` value is the authoritative extracted text;
    `normalized` is the business-logic transformation result.
    """

    raw: str = ""
    normalized: Any = None  # Can be float, str, dict, None
    normalizer: str = ""  # e.g., "amount.cn.v1", "date.iso8601.v1"
    confidence: float = 0.0
    source_refs: list[str] = field(default_factory=list)
    review: str = "needs_evidence"  # auto_accepted | manual_optional | needs_review | needs_evidence


@dataclass
class FieldDetailCollection:
    """Collection of field details for a document or record.

    Supports the `data.field_details` contract in Edition JSON:
    - data.fields.{key} = plain value (stable public shape)
    - data.field_details.{key} = FieldDetail with raw/normalized/evidence
    """

    fields: dict[str, FieldDetail] = field(default_factory=dict)

    def __getitem__(self, key: str) -> FieldDetail:
        return self.fields[key]

    def __setitem__(self, key: str, value: FieldDetail) -> None:
        self.fields[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self.fields

    def __len__(self) -> int:
        return len(self.fields)

    def __iter__(self):
        return iter(self.fields)


# ── Factory helpers ──────────────────────────────────────────────────────────


def make_field_detail(
    *,
    raw: str,
    normalized: Any = None,
    normalizer: str = "",
    confidence: float = 0.0,
    source_refs: list[str] | None = None,
    review: str = "needs_evidence",
) -> FieldDetail:
    """Create a FieldDetail with sensible defaults.

    Review status is determined by confidence and evidence presence:
    - confidence >= 0.85 and source_refs present -> auto_accepted
    - confidence >= 0.60 and source_refs present -> manual_optional
    - confidence < 0.60 -> needs_review
    - no source_refs -> needs_evidence
    """
    refs = source_refs or []
    if not refs:
        review = "needs_evidence"
    elif confidence >= 0.85:
        review = "auto_accepted"
    elif confidence >= 0.60:
        review = "manual_optional"
    else:
        review = "needs_review"

    return FieldDetail(
        raw=raw,
        normalized=normalized,
        normalizer=normalizer,
        confidence=confidence,
        source_refs=refs,
        review=review,
    )


# ── Currency amount normalization example ────────────────────────────────────


def normalize_amount_cny(raw: str) -> tuple[float | None, dict[str, Any]]:
    """Normalize a Chinese currency amount string.

    Returns (normalized_value, metadata) or (None, metadata) on failure.
    """
    import re

    cleaned = raw.strip().replace("￥", "").replace("¥", "").replace(",", "").replace("，", "")
    # Try to extract a numeric value
    match = re.search(r"-?[\d.,]+\.?\d*", cleaned)
    if not match:
        return None, {"error": "no_numeric_value", "raw": raw}

    try:
        value = float(match.group().replace(",", ""))
    except ValueError:
        return None, {"error": "parse_failed", "raw": raw}

    sign = "debit" if cleaned.startswith("-") or "支出" in raw or "支" in raw else "credit"
    return value, {
        "type": "amount",
        "currency": "CNY",
        "sign": sign,
        "raw": raw,
    }


# ── Date normalization example ───────────────────────────────────────────────


def normalize_date_iso(raw: str) -> tuple[str | None, dict[str, Any]]:
    """Normalize a date string to ISO 8601 format.

    Handles common Chinese date formats: 2024年1月15日, 2024/01/15, 2024-01-15.
    Returns (iso_string, metadata) or (None, metadata) on failure.
    """
    import re

    cleaned = raw.strip()

    patterns = [
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日", lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"),
        (r"(\d{4})/(\d{1,2})/(\d{1,2})", lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"),
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"),
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", lambda m: f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"),
    ]

    for pattern, formatter in patterns:
        match = re.search(pattern, cleaned)
        if match:
            try:
                iso = formatter(match)
                return iso, {"type": "date", "format": "iso8601", "raw": raw}
            except ValueError:
                continue

    return None, {"error": "unrecognized_format", "raw": raw}


# ── Serialization helpers ────────────────────────────────────────────────────


def field_detail_to_dict(fd: FieldDetail) -> dict[str, Any]:
    """Serialize a FieldDetail to a plain dict."""
    d = asdict(fd)
    # Keep normalized even if None (it's a meaningful signal)
    return d


def field_details_from_edition(
    fields: dict[str, Any],
    field_details_raw: dict[str, dict[str, Any]] | None = None,
) -> FieldDetailCollection:
    """Build a FieldDetailCollection from Edition JSON fields.

    Args:
        fields: The data.fields dict from an Edition payload.
        field_details_raw: Optional raw field_details dict with evidence metadata.

    Returns:
        FieldDetailCollection with FieldDetail entries for each key field.
    """
    collection = FieldDetailCollection()
    details_raw = field_details_raw or {}

    for key, value in fields.items():
        detail_data = details_raw.get(key, {})
        raw_val = str(value) if value is not None else ""
        collection[key] = FieldDetail(
            raw=detail_data.get("raw", raw_val),
            normalized=detail_data.get("normalized"),
            normalizer=detail_data.get("normalizer", ""),
            confidence=float(detail_data.get("confidence", 0.0)),
            source_refs=list(detail_data.get("source_refs", [])),
            review=str(detail_data.get("review", "needs_evidence")),
        )

    return collection
