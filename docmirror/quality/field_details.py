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

Internal GA 1.0 trust design reference: field detail policy.
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
    source_refs: list[Any] = field(default_factory=list)
    review: str = "needs_evidence"  # auto_accepted | manual_optional | needs_review | needs_evidence


@dataclass
class FieldDetailCollection:
    """Collection of field details for a document or record.

    Supports the internal full field-detail contract:
    - data.fields.{key} = plain value (stable public shape)
    - FieldDetail = raw/normalized/evidence before the compact public projection
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
    source_refs: list[Any] | None = None,
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
            normalized=detail_data.get("normalized", value),
            normalizer=detail_data.get("normalizer", ""),
            confidence=float(detail_data.get("confidence", 0.0)),
            source_refs=list(detail_data.get("source_refs", [])),
            review=str(detail_data.get("review", "needs_evidence")),
        )

    return collection


def field_details_from_community_data(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build the stable ``data.field_details`` projection without changing fields.

    Community plugins currently expose field intelligence in three compatible
    shapes: rich objects in ``fields``, plain values plus ``normalized_fields``,
    and provenance in ``field_metadata``.  This adapter projects those shapes
    into the existing QTC ``FieldDetail`` contract while leaving every legacy
    path intact.
    """
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    normalized_fields = (
        data.get("normalized_fields") if isinstance(data.get("normalized_fields"), dict) else {}
    )
    field_metadata = data.get("field_metadata") if isinstance(data.get("field_metadata"), dict) else {}
    existing = data.get("field_details") if isinstance(data.get("field_details"), dict) else {}
    out: dict[str, dict[str, Any]] = {}

    for key, field_value in fields.items():
        existing_detail = existing.get(key) if isinstance(existing.get(key), dict) else {}
        metadata = field_metadata.get(key) if isinstance(field_metadata.get(key), dict) else {}
        rich_value = field_value if isinstance(field_value, dict) else {}

        raw_value = existing_detail.get("raw")
        if raw_value is None:
            raw_value = rich_value.get("raw_value", rich_value.get("raw", field_value))

        normalized = existing_detail.get("normalized")
        if normalized is None:
            normalized = rich_value.get("normalized_value", rich_value.get("normalized"))
        if normalized is None and key in normalized_fields:
            normalized = normalized_fields[key]
        if normalized is None:
            normalized = _preferred_plain_value(field_value)

        source_refs = list(existing_detail.get("source_refs") or rich_value.get("source_refs") or [])
        if not source_refs and metadata:
            source_ref = {
                name: value
                for name, value in metadata.items()
                if name not in {"confidence"} and value not in (None, "", [], {})
            }
            if source_ref:
                source_refs = [source_ref]

        confidence = _safe_confidence(
            existing_detail.get("confidence", rich_value.get("confidence", metadata.get("confidence", 0.0)))
        )
        detail = make_field_detail(
            raw=_stringify_raw(raw_value),
            normalized=normalized,
            normalizer=str(existing_detail.get("normalizer") or rich_value.get("normalizer") or ""),
            confidence=confidence,
            source_refs=source_refs,
            review=str(existing_detail.get("review") or "needs_evidence"),
        )
        out[str(key)] = field_detail_to_dict(detail)

    return out


def compact_community_field_projection(
    data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Return canonical field values plus reference-only public field details.

    Plugin-specific rich values and legacy normalization metadata are consumed
    here, before the post-extract hook removes those intermediate structures.
    ``data.fields`` becomes the only normalized-value location.  A raw value is
    retained in ``field_details`` only when it materially differs.
    """
    full_details = field_details_from_community_data(data)
    canonical_fields: dict[str, Any] = {}
    compact_details: dict[str, dict[str, Any]] = {}

    for key, detail in full_details.items():
        value = detail.get("normalized")
        canonical_fields[key] = value
        pointer_key = str(key).replace("~", "~0").replace("/", "~1")
        compact: dict[str, Any] = {
            "value_ref": f"/data/fields/{pointer_key}",
            "normalizer": str(detail.get("normalizer") or ""),
            "confidence": _safe_confidence(detail.get("confidence")),
            "source_refs": list(detail.get("source_refs") or []),
            "review": str(detail.get("review") or "needs_evidence"),
        }
        raw = str(detail.get("raw") or "")
        if not _raw_matches_value(raw, value):
            compact["raw"] = raw
        compact_details[key] = compact

    return canonical_fields, compact_details


def _preferred_plain_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("normalized_value", "value", "raw_value", "raw"):
        if value.get(key) not in (None, ""):
            return value[key]
    return value


def _stringify_raw(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _raw_matches_value(raw: str, value: Any) -> bool:
    if value is None:
        return not raw
    if isinstance(value, str):
        return raw == value
    if isinstance(value, bool):
        return raw.casefold() == str(value).casefold()
    return False
