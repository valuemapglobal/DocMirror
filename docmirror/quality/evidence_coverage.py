"""Evidence Coverage Denominator — QTC W3-03.

Provides the denominator computation for evidence coverage metrics.
Key fields are defined per domain from DGAC/DEC schemas.
This module computes:
- How many key fields are defined for a domain (denominator).
- How many key fields have evidence (numerator).
- Evidence coverage ratio for each domain and across all domains.

Design reference: docs/design/GA1.0/08_accuracy_trust_ga_gap_closure_plan.md W3-03
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── DGAC Key Field Definitions ─────────────────────────────────────────────

# Per-domain key field lists as defined by Domain GA Contracts.
# Each field has a `field_path` used in Edition JSON (e.g., "account_number")
# and a `priority` (P0 = must have evidence, P1 = should have evidence).

@dataclass
class KeyFieldDef:
    """Definition of a key field for a domain."""
    field_path: str
    priority: str = "P0"  # P0 | P1
    label: str = ""


# ── Key fields per domain (from DGAC/DEC schemas) ──────────────────────────

_KEY_FIELDS: dict[str, list[KeyFieldDef]] = {
    "bank_statement": [
        KeyFieldDef("account_number", "P0", "Account Number"),
        KeyFieldDef("account_name", "P0", "Account Name"),
        KeyFieldDef("statement_period_start", "P0", "Statement Period Start"),
        KeyFieldDef("statement_period_end", "P0", "Statement Period End"),
        KeyFieldDef("opening_balance", "P0", "Opening Balance"),
        KeyFieldDef("closing_balance", "P0", "Closing Balance"),
        KeyFieldDef("currency", "P1", "Currency"),
        KeyFieldDef("transaction_count", "P1", "Transaction Count"),
    ],
    "vat_invoice": [
        KeyFieldDef("invoice_number", "P0", "Invoice Number"),
        KeyFieldDef("invoice_date", "P0", "Invoice Date"),
        KeyFieldDef("seller_name", "P0", "Seller Name"),
        KeyFieldDef("seller_tax_id", "P0", "Seller Tax ID"),
        KeyFieldDef("buyer_name", "P0", "Buyer Name"),
        KeyFieldDef("buyer_tax_id", "P0", "Buyer Tax ID"),
        KeyFieldDef("total_amount", "P0", "Total Amount"),
        KeyFieldDef("tax_amount", "P0", "Tax Amount"),
        KeyFieldDef("amount_excluding_tax", "P0", "Amount Excluding Tax"),
        KeyFieldDef("currency", "P1", "Currency"),
    ],
    "credit_report": [
        KeyFieldDef("report_id", "P0", "Report ID"),
        KeyFieldDef("subject_name", "P0", "Subject Name"),
        KeyFieldDef("subject_id_number", "P0", "Subject ID Number"),
        KeyFieldDef("report_date", "P0", "Report Date"),
        KeyFieldDef("credit_score", "P0", "Credit Score"),
        KeyFieldDef("total_credit_lines", "P0", "Total Credit Lines"),
        KeyFieldDef("overdue_record_count", "P0", "Overdue Record Count"),
    ],
    "wechat_payment": [
        KeyFieldDef("transaction_id", "P0", "Transaction ID"),
        KeyFieldDef("transaction_time", "P0", "Transaction Time"),
        KeyFieldDef("counterparty", "P0", "Counterparty"),
        KeyFieldDef("amount", "P0", "Amount"),
        KeyFieldDef("payment_method", "P1", "Payment Method"),
        KeyFieldDef("transaction_type", "P1", "Transaction Type"),
    ],
    "alipay_payment": [
        KeyFieldDef("transaction_id", "P0", "Transaction ID"),
        KeyFieldDef("transaction_time", "P0", "Transaction Time"),
        KeyFieldDef("counterparty", "P0", "Counterparty"),
        KeyFieldDef("amount", "P0", "Amount"),
        KeyFieldDef("payment_method", "P1", "Payment Method"),
        KeyFieldDef("transaction_type", "P1", "Transaction Type"),
    ],
    "business_license": [
        KeyFieldDef("company_name", "P0", "Company Name"),
        KeyFieldDef("registration_number", "P0", "Registration Number"),
        KeyFieldDef("legal_representative", "P0", "Legal Representative"),
        KeyFieldDef("registered_capital", "P0", "Registered Capital"),
        KeyFieldDef("establishment_date", "P0", "Establishment Date"),
        KeyFieldDef("business_scope", "P1", "Business Scope"),
        KeyFieldDef("validity_period", "P0", "Validity Period"),
    ],
    "generic": [
        KeyFieldDef("document_type", "P1", "Document Type"),
        KeyFieldDef("title", "P1", "Title"),
    ],
}


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

    Falls back to generic key fields when domain is not recognized.
    """
    domain_key = domain.lower().replace("-", "_").replace(" ", "_")
    if domain_key in _KEY_FIELDS:
        return _KEY_FIELDS[domain_key]
    # Try partial match
    for key in _KEY_FIELDS:
        if key in domain_key or domain_key in key:
            return _KEY_FIELDS[key]
    return _KEY_FIELDS.get("generic", [])


def compute_evidence_coverage(
    domain: str,
    field_evidence_map: dict[str, dict[str, Any]],
) -> EvidenceCoverageResult:
    """Compute evidence coverage for a domain given a map of field_path → evidence.

    Args:
        domain: Domain identifier (e.g., "bank_statement").
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
