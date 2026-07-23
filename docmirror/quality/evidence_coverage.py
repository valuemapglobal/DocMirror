"""Evidence Coverage Denominator — QTC W3-03.

Provides the denominator computation for evidence coverage metrics.
Key fields are derived from plugin-owned Domain GA Contracts.
This module computes:
- How many key fields are defined for a domain (denominator).
- How many key fields have evidence (numerator).
- Evidence coverage ratio for each domain and across all domains.

Internal GA 1.0 trust design reference: W3-03.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KeyFieldDef:
    """Definition of a key field for a domain."""

    field_path: str
    priority: str = "P0"  # P0 | P1
    label: str = ""


# ── Evidence coverage computation ───────────────────────────────────────────


@dataclass
class EvidenceCoverageResult:
    """Result of evidence coverage computation for a domain."""

    domain: str
    total_key_fields: int = 0
    key_fields_with_evidence: int = 0
    p0_total: int = 0
    p0_with_evidence: int = 0
    coverage_ratio: float = 0.0
    p0_coverage_ratio: float = 0.0
    uncovered_fields: list[str] = field(default_factory=list)
    uncovered_p0_fields: list[str] = field(default_factory=list)


def get_key_fields_for_domain(domain: str) -> list[KeyFieldDef]:
    """Return the key field definitions for a domain.

    Required/required-any commitments are P0; conditional/optional commitments
    are P1. Unknown domains use the generic plugin contract.
    """
    from docmirror.configs.scene.loader import get_scene_aliases
    from docmirror.models.schemas.domain_contract_validator import load_domain_contracts

    domain_key = domain.lower().replace("-", "_").replace(" ", "_")
    domain_key = get_scene_aliases().get(domain_key, domain_key)
    contracts = load_domain_contracts().get("domains") or {}
    contract = contracts.get(domain_key) or contracts.get("generic") or {}
    commitment = contract.get("p0_commitment") or {}

    priorities: dict[str, str] = {}
    for section_name in ("fields", "records"):
        section = commitment.get(section_name) or {}
        for group in ("required", "required_any"):
            for field_name in section.get(group) or []:
                priorities[str(field_name)] = "P0"
        for group in ("conditional", "optional"):
            for field_name in section.get(group) or []:
                priorities.setdefault(str(field_name), "P1")

    return [
        KeyFieldDef(field_path=name, priority=priority, label=name.replace("_", " ").title())
        for name, priority in priorities.items()
    ]


def compute_evidence_coverage(
    domain: str,
    field_evidence_map: dict[str, dict[str, Any]],
) -> EvidenceCoverageResult:
    """Compute evidence coverage for a domain given a map of field_path → evidence.

    Args:
        domain: Plugin domain identifier.
        field_evidence_map: Mapping of field_path to a dict with evidence info.
            Each value dict should contain at least one of:
            - source_refs (list) — non-empty means has evidence
            - page (int | None) — non-None means has page evidence
            - bbox (list | None) — non-None means has bbox evidence
            - confidence (float) — >0 means has some evidence

    Returns:
        EvidenceCoverageResult with coverage ratios.
    """
    key_fields = get_key_fields_for_domain(domain)
    if not key_fields:
        return EvidenceCoverageResult(domain=domain)

    total = len(key_fields)
    with_evidence = 0
    p0_total = sum(1 for kf in key_fields if kf.priority == "P0")
    p0_with_evidence = 0
    uncovered: list[str] = []
    uncovered_p0: list[str] = []

    for kf in key_fields:
        evidence = field_evidence_map.get(kf.field_path, {})
        has_evidence = _field_has_evidence(evidence)

        if has_evidence:
            with_evidence += 1
            if kf.priority == "P0":
                p0_with_evidence += 1
        else:
            uncovered.append(kf.field_path)
            if kf.priority == "P0":
                uncovered_p0.append(kf.field_path)

    return EvidenceCoverageResult(
        domain=domain,
        total_key_fields=total,
        key_fields_with_evidence=with_evidence,
        p0_total=p0_total,
        p0_with_evidence=p0_with_evidence,
        coverage_ratio=with_evidence / total if total > 0 else 0.0,
        p0_coverage_ratio=p0_with_evidence / p0_total if p0_total > 0 else 0.0,
        uncovered_fields=uncovered,
        uncovered_p0_fields=uncovered_p0,
    )


def _field_has_evidence(evidence: dict[str, Any]) -> bool:
    """Determine whether a field has verifiable evidence."""
    # Non-empty source_refs is the strongest signal
    source_refs = evidence.get("source_refs")
    if isinstance(source_refs, list) and len(source_refs) > 0:
        return True
    # Page-level evidence
    page = evidence.get("page")
    if page is not None and page != "":
        return True
    # Bbox evidence
    bbox = evidence.get("bbox")
    if isinstance(bbox, list) and len(bbox) > 0:
        return True
    # Non-zero confidence is weak evidence
    confidence = evidence.get("confidence")
    if isinstance(confidence, (int, float)) and confidence > 0.0:
        return True
    return False


def compute_multi_domain_coverage(
    domain_evidence_maps: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, EvidenceCoverageResult]:
    """Compute evidence coverage for multiple domains.

    Args:
        domain_evidence_maps: Mapping of domain → field_path → evidence dict.

    Returns:
        Dict of domain → EvidenceCoverageResult.
    """
    results: dict[str, EvidenceCoverageResult] = {}
    for domain, field_map in domain_evidence_maps.items():
        results[domain] = compute_evidence_coverage(domain, field_map)
    return results


def build_evidence_coverage_summary(
    results: dict[str, EvidenceCoverageResult],
) -> dict[str, Any]:
    """Build a summary of evidence coverage across all domains.

    Returns a dict suitable for inclusion in GA metrics reports
    and quality reports.
    """
    total_fields = sum(r.total_key_fields for r in results.values())
    total_with_evidence = sum(r.key_fields_with_evidence for r in results.values())
    total_p0 = sum(r.p0_total for r in results.values())
    total_p0_with_evidence = sum(r.p0_with_evidence for r in results.values())

    all_uncovered_p0: list[str] = []
    for r in results.values():
        for f in r.uncovered_p0_fields:
            all_uncovered_p0.append(f"{r.domain}.{f}")

    return {
        "overall_coverage_ratio": total_with_evidence / total_fields if total_fields > 0 else 0.0,
        "p0_coverage_ratio": total_p0_with_evidence / total_p0 if total_p0 > 0 else 0.0,
        "total_key_fields": total_fields,
        "total_with_evidence": total_with_evidence,
        "p0_total": total_p0,
        "p0_with_evidence": total_p0_with_evidence,
        "uncovered_p0_fields": all_uncovered_p0,
        "per_domain": {
            domain: {
                "coverage_ratio": r.coverage_ratio,
                "p0_coverage_ratio": r.p0_coverage_ratio,
                "key_fields_with_evidence": r.key_fields_with_evidence,
                "total_key_fields": r.total_key_fields,
                "uncovered_p0_fields": r.uncovered_p0_fields,
            }
            for domain, r in results.items()
        },
    }
