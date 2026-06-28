"""Universal evidence verification models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VerificationCandidate:
    source: str
    value: Any
    confidence: float = 1.0
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "value": self.value,
            "confidence": float(self.confidence),
            "evidence_ids": list(self.evidence_ids),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class VerificationClaim:
    claim_id: str
    claim_type: str
    subject_unit_id: str
    status: str
    score: float
    evidence_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "subject_unit_id": self.subject_unit_id,
            "status": self.status,
            "score": float(self.score),
            "evidence_ids": list(self.evidence_ids),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class VerifiedUnit:
    unit_id: str
    unit_type: str
    block_id: str = ""
    region_ids: list[str] = field(default_factory=list)
    page_ids: list[str] = field(default_factory=list)
    bbox: list[float] | None = None
    evidence_ids: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    selected_value: Any = ""
    data_type: str = "unknown"
    confidence: float = 0.0
    candidates: list[VerificationCandidate] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    status: str = "not_evaluated"
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "unit_type": self.unit_type,
            "block_id": self.block_id,
            "region_ids": list(self.region_ids),
            "page_ids": list(self.page_ids),
            "bbox": list(self.bbox) if self.bbox else None,
            "evidence_ids": list(self.evidence_ids),
            "source_refs": list(self.source_refs),
            "selected_value": self.selected_value,
            "data_type": self.data_type,
            "confidence": float(self.confidence),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "verification": {
                "status": self.status,
                "reasons": list(self.reasons),
                "claim_ids": list(self.claim_ids),
            },
        }


@dataclass(frozen=True)
class VerificationRule:
    rule_id: str
    rule_type: str
    status: str
    input_unit_ids: list[str] = field(default_factory=list)
    output_unit_ids: list[str] = field(default_factory=list)
    reason: str = ""
    score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "status": self.status,
            "input_unit_ids": list(self.input_unit_ids),
            "output_unit_ids": list(self.output_unit_ids),
            "reason": self.reason,
            "score": float(self.score),
        }


@dataclass(frozen=True)
class VerificationReport:
    units: list[VerifiedUnit] = field(default_factory=list)
    claims: list[VerificationClaim] = field(default_factory=list)
    rules: list[VerificationRule] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        unit_count = len(self.units)
        status_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        for unit in self.units:
            status_counts[unit.status] = status_counts.get(unit.status, 0) + 1
            type_counts[unit.unit_type] = type_counts.get(unit.unit_type, 0) + 1
        verified = status_counts.get("verified", 0)
        conflict = status_counts.get("conflict", 0)
        not_evaluated = status_counts.get("not_evaluated", 0)
        not_applicable = status_counts.get("not_applicable", 0)
        applicable_count = max(unit_count - not_applicable, 0)
        rule_status_counts: dict[str, int] = {}
        for rule in self.rules:
            rule_status_counts[rule.status] = rule_status_counts.get(rule.status, 0) + 1
        claim_status_counts: dict[str, int] = {}
        claim_type_counts: dict[str, int] = {}
        for claim in self.claims:
            claim_status_counts[claim.status] = claim_status_counts.get(claim.status, 0) + 1
            claim_type_counts[claim.claim_type] = claim_type_counts.get(claim.claim_type, 0) + 1
        candidate_source_counts: dict[str, int] = {}
        for unit in self.units:
            for candidate in unit.candidates:
                candidate_source_counts[candidate.source] = candidate_source_counts.get(candidate.source, 0) + 1
        return {
            "unit_count": unit_count,
            "applicable_unit_count": applicable_count,
            "claim_count": len(self.claims),
            "rule_count": len(self.rules),
            "unit_status_counts": status_counts,
            "unit_type_counts": type_counts,
            "claim_status_counts": claim_status_counts,
            "claim_type_counts": claim_type_counts,
            "candidate_source_counts": candidate_source_counts,
            "rule_status_counts": rule_status_counts,
            "verified_unit_ratio": verified / applicable_count if applicable_count else 1.0,
            "conflict_ratio": conflict / applicable_count if applicable_count else 0.0,
            "not_evaluated_ratio": not_evaluated / applicable_count if applicable_count else 0.0,
            "not_applicable_ratio": not_applicable / unit_count if unit_count else 0.0,
        }

    def diagnostics_entry(self) -> dict[str, Any]:
        return {
            "stage": "universal_evidence_verification",
            "status": "ok",
            "summary": self.summary(),
            "sample_units": [unit.to_dict() for unit in self.units[:20]],
            "sample_claims": [claim.to_dict() for claim in self.claims[:20]],
            "rules": [rule.to_dict() for rule in self.rules[:50]],
        }

    def to_quality_summary(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "units": [unit.to_dict() for unit in self.units[:200]],
            "claims": [claim.to_dict() for claim in self.claims[:200]],
            "rules": [rule.to_dict() for rule in self.rules[:200]],
            "truncated": len(self.units) > 200 or len(self.claims) > 200 or len(self.rules) > 200,
        }
