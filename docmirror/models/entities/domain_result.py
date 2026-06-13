# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Formal domain plugin output protocol (L5 Domain Sandbox)."""

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


def normalize_domain_result(raw: Any) -> DomainExtractionResult:
    """Normalize legacy plugin returns into DomainExtractionResult.

    Accepts:
        - DomainExtractionResult (passthrough)
        - Wrapper dict with ``entities`` key
        - Flat entity dict (credit_report fast mode)
    """
    if isinstance(raw, DomainExtractionResult):
        return raw

    if not isinstance(raw, dict):
        return DomainExtractionResult(
            quality=DomainQuality(issues=[f"unexpected plugin return type: {type(raw).__name__}"]),
        )

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
                field_coverage=float(quality_raw.get("field_coverage", 0)),
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
        if k not in ("quality", "structured_data", "derived_variables", "metadata", "evidence_ids", "document_type", "properties")
    }
    if isinstance(quality_raw, dict):
        quality = DomainQuality(
            confidence=float(quality_raw.get("confidence", 0)),
            trust_score=float(quality_raw.get("trust_score", 0)),
            field_coverage=float(quality_raw.get("field_coverage", 0)),
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
