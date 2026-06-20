# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Domain Extraction Contract (DEC) — formal domain plugin output protocol (L5).

Defines the typed contract that all domain plugins must produce, plus helpers
for normalizing legacy and edition-specific plugin payloads into ``DEC`` form.

Core types::

    DomainQuality            Confidence, trust, field coverage, validation status, issues
    DomainExtractionResult   document_type, entities, structured_data, derived_variables,
                             quality, metadata, evidence_ids
    ExtractionHint           Domain-scoped hints for the universal table resolver

Envelope detection helpers (``_is_edition_v2_payload``, ``_is_enterprise_envelope``,
``_is_finance_envelope``) identify when plugin output is already a full edition
JSON envelope and should bypass ``edition_serializer``.

``normalize_plugin_output`` is the main entry for converting raw plugin dicts
into validated ``DomainExtractionResult`` instances.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DomainQuality(BaseModel):
    """Standardized quality metrics for domain extraction."""

    confidence: float = 0.0
    trust_score: float = 0.0
    field_coverage: float = 0.0
    validation_passed: bool = False
    issues: list[str] = Field(default_factory=list)


class DomainExtractionResult(BaseModel):
    """Formal contract for all domain plugin outputs."""

    document_type: str = "unknown"
    properties: dict[str, Any] = Field(default_factory=dict)
    entities: dict[str, Any] = Field(default_factory=dict)
    structured_data: dict[str, Any] | list[Any] | None = None
    derived_variables: dict[str, Any] = Field(default_factory=dict)
    quality: DomainQuality = Field(default_factory=DomainQuality)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class ExtractionHint(BaseModel):
    """Domain-scoped hints for universal resolver (does not delete candidates)."""

    scope: dict[str, Any] = Field(default_factory=dict)
    preferred_methods: list[str] = Field(default_factory=list)
    disabled_methods: list[str] = Field(default_factory=list)
    scoring_overrides: dict[str, float] = Field(default_factory=dict)
    reason: str = ""


def _is_finance_envelope(raw: dict[str, Any]) -> bool:
    """True when *raw* is finance edition JSON v3.0 (decision-layer blocks)."""
    return (
        raw.get("schema_version") == "3.0" and raw.get("edition") == "finance" and isinstance(raw.get("scenario"), dict)
    )


def _is_enterprise_envelope(raw: dict[str, Any]) -> bool:
    """True when *raw* is enterprise DEC v2.0 (``extraction`` block, schema 2.0)."""
    return (
        raw.get("schema_version") == "2.0"
        and raw.get("edition") == "enterprise"
        and isinstance(raw.get("extraction"), dict)
    )


def _is_edition_v2_payload(raw: dict[str, Any]) -> bool:
    """True when *raw* is community edition JSON v2.0 (``schema_version`` + ``data``)."""
    return raw.get("schema_version") == "2.0" and isinstance(raw.get("data"), dict)


def _is_edition_envelope_passthrough(raw: dict[str, Any]) -> bool:
    """True when plugin output must bypass ``edition_serializer`` (full edition envelope)."""
    return _is_edition_v2_payload(raw) or _is_enterprise_envelope(raw) or _is_finance_envelope(raw)


def _normalize_finance_envelope(raw: dict[str, Any]) -> DomainExtractionResult:
    """Map finance v3.0 blocks → DEC for validation."""
    doc = raw.get("document") if isinstance(raw.get("document"), dict) else {}
    extraction = raw.get("extraction") if isinstance(raw.get("extraction"), dict) else {}
    normalization = raw.get("normalization") if isinstance(raw.get("normalization"), dict) else {}
    status = raw.get("status") if isinstance(raw.get("status"), dict) else {}
    quality_raw = raw.get("quality") if isinstance(raw.get("quality"), dict) else {}
    validation = raw.get("validation") if isinstance(raw.get("validation"), dict) else {}
    subject = raw.get("subject") if isinstance(raw.get("subject"), dict) else {}

    document_type = str(doc.get("document_type") or "unknown")
    properties = dict(doc.get("properties") or {})
    entities = dict(extraction.get("fields") or {})
    if subject.get("subject_name"):
        entities.setdefault("subject_name", subject["subject_name"])

    structured_data = {
        k: extraction.get(k)
        for k in ("records", "summary", "sections", "tables", "line_items")
        if extraction.get(k) is not None
    }
    if not structured_data.get("records") and normalization.get("standard_records"):
        structured_data["records"] = normalization["standard_records"]
    fi = raw.get("financial_indicators")
    if isinstance(fi, dict):
        structured_data["financial_indicators"] = fi

    warnings = list(status.get("warnings") or [])
    errors = list(status.get("errors") or [])
    success = bool(status.get("success", True))

    quality = DomainQuality(
        confidence=float(quality_raw.get("overall_score") or status.get("confidence") or 0),
        field_coverage=_coerce_field_coverage(quality_raw.get("field_coverage")),
        validation_passed=success and not errors and bool(validation.get("passed", True)),
        issues=[*(f"warning:{w}" for w in warnings), *(f"error:{e}" for e in errors)],
    )

    metadata = dict(raw.get("metadata") or {})
    metadata.setdefault("edition", "finance")

    return DomainExtractionResult(
        document_type=document_type,
        properties=properties,
        entities=entities,
        structured_data=structured_data or None,
        quality=quality,
        metadata=metadata,
    )


def _normalize_enterprise_envelope(raw: dict[str, Any]) -> DomainExtractionResult:
    """Map enterprise/finance v2.0 blocks → DEC for validation."""
    doc = raw.get("document") if isinstance(raw.get("document"), dict) else {}
    extraction = raw.get("extraction") if isinstance(raw.get("extraction"), dict) else {}
    normalization = raw.get("normalization") if isinstance(raw.get("normalization"), dict) else {}
    status = raw.get("status") if isinstance(raw.get("status"), dict) else {}
    quality_raw = raw.get("quality") if isinstance(raw.get("quality"), dict) else {}
    validation = raw.get("validation") if isinstance(raw.get("validation"), dict) else {}

    document_type = str(doc.get("document_type") or "unknown")
    properties = dict(doc.get("properties") or {})
    entities = dict(extraction.get("fields") or {})

    structured_data = {
        k: extraction.get(k)
        for k in ("records", "summary", "sections", "tables", "line_items")
        if extraction.get(k) is not None
    }
    if not structured_data.get("records") and normalization.get("standard_records"):
        structured_data["records"] = normalization["standard_records"]

    warnings = list(status.get("warnings") or [])
    errors = list(status.get("errors") or [])
    success = bool(status.get("success", True))

    quality = DomainQuality(
        confidence=float(quality_raw.get("overall_score") or status.get("confidence") or 0),
        field_coverage=_coerce_field_coverage(quality_raw.get("field_coverage")),
        validation_passed=success and not errors and bool(validation.get("passed", True)),
        issues=[*(f"warning:{w}" for w in warnings), *(f"error:{e}" for e in errors)],
    )

    metadata = dict(raw.get("metadata") or {})
    metadata.setdefault("edition", raw.get("edition"))

    return DomainExtractionResult(
        document_type=document_type,
        properties=properties,
        entities=entities,
        structured_data=structured_data or None,
        quality=quality,
        metadata=metadata,
    )


def _normalize_edition_v2(raw: dict[str, Any]) -> DomainExtractionResult:
    """Map edition v2.0 blocks → DEC (table plugins via ``extract_from_mirror``)."""
    doc = raw.get("document") if isinstance(raw.get("document"), dict) else {}
    data = raw["data"]
    status = raw.get("status") if isinstance(raw.get("status"), dict) else {}

    document_type = str(doc.get("document_type") or "unknown")
    properties = dict(doc.get("properties") or {})
    entities = dict(data.get("fields") or {})

    structured_data = {
        k: data.get(k) for k in ("records", "summary", "sections", "tables", "line_items") if data.get(k) is not None
    }

    warnings = list(status.get("warnings") or [])
    errors = list(status.get("errors") or [])
    success = bool(status.get("success", True))

    quality = DomainQuality(
        confidence=float(status.get("confidence") or raw.get("confidence") or 0),
        validation_passed=success and not errors,
        issues=[*(f"warning:{w}" for w in warnings), *(f"error:{e}" for e in errors)],
    )

    metadata = dict(raw.get("metadata") or {})
    if raw.get("edition"):
        metadata["edition"] = raw["edition"]
    if raw.get("classification"):
        metadata["classification"] = raw["classification"]

    return DomainExtractionResult(
        document_type=document_type,
        properties=properties,
        entities=entities,
        structured_data=structured_data or None,
        quality=quality,
        metadata=metadata,
    )


def _coerce_field_coverage(value: Any) -> float:
    """Map per-field coverage dicts to a single scalar for DomainQuality."""
    if isinstance(value, dict):
        nums = [float(v) for v in value.values() if isinstance(v, (int, float))]
        return sum(nums) / len(nums) if nums else 0.0
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_domain_result(raw: Any) -> DomainExtractionResult:
    """Normalize legacy plugin returns into DomainExtractionResult.

    Accepts:
        - DomainExtractionResult (passthrough)
        - Edition JSON v2.0 (``schema_version`` + ``document`` + ``data``)
        - Wrapper dict with ``entities`` key
        - Flat entity dict (credit_report fast mode)
    """
    if isinstance(raw, DomainExtractionResult):
        return raw

    if not isinstance(raw, dict):
        return DomainExtractionResult(
            quality=DomainQuality(issues=[f"unexpected plugin return type: {type(raw).__name__}"]),
        )

    if _is_edition_v2_payload(raw):
        return _normalize_edition_v2(raw)

    if _is_enterprise_envelope(raw):
        return _normalize_enterprise_envelope(raw)

    if _is_finance_envelope(raw):
        return _normalize_finance_envelope(raw)

    # Wrapper form: {document_type, entities, quality, structured_data, ...}
    is_wrapper = "entities" in raw and isinstance(raw.get("entities"), dict)
    if is_wrapper:
        quality_raw = raw.get("quality") or {}
        if isinstance(quality_raw, DomainQuality):
            quality = quality_raw
        else:
            quality = DomainQuality(
                confidence=float(quality_raw.get("confidence", 0)),
                trust_score=float(quality_raw.get("trust_score", 0)),
                field_coverage=_coerce_field_coverage(quality_raw.get("field_coverage", 0)),
                validation_passed=bool(quality_raw.get("validation_passed", False)),
                issues=list(quality_raw.get("issues") or []),
            )
        return DomainExtractionResult(
            document_type=str(raw.get("document_type", "unknown")),
            properties=dict(raw.get("properties") or {}),
            entities=dict(raw["entities"]),
            structured_data=raw.get("structured_data"),
            derived_variables=dict(raw.get("derived_variables") or {}),
            quality=quality,
            metadata=dict(raw.get("metadata") or {}),
            evidence_ids=list(raw.get("evidence_ids") or []),
        )

    # Flat dict form (e.g. credit_report fast mode returns entities directly)
    quality_raw = raw.get("quality", {})
    entities = {
        k: v
        for k, v in raw.items()
        if k
        not in (
            "quality",
            "structured_data",
            "derived_variables",
            "metadata",
            "evidence_ids",
            "document_type",
            "properties",
        )
    }
    if isinstance(quality_raw, dict):
        quality = DomainQuality(
            confidence=float(quality_raw.get("confidence", 0)),
            trust_score=float(quality_raw.get("trust_score", 0)),
            field_coverage=_coerce_field_coverage(quality_raw.get("field_coverage", 0)),
            validation_passed=bool(quality_raw.get("validation_passed", False)),
            issues=list(quality_raw.get("issues") or []),
        )
    else:
        quality = DomainQuality()

    return DomainExtractionResult(
        document_type=str(raw.get("document_type", "unknown")),
        entities=entities,
        quality=quality,
    )
