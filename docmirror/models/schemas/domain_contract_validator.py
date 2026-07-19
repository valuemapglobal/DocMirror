# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Domain Contract Validator — validates Edition JSON payload against DGAC.

Reads ``docmirror/configs/yaml/domain_contracts/community_core.yaml`` and
validates that a community Edition JSON payload satisfies the P0 field /
record / section / quality / failure commitments for a given domain.

Key exports: ``validate_domain_schema``, ``DomainContractValidationReport``.

Used by: ``scripts/validate/validate_domain_ga_contracts.py``,
``scripts/sync/compile_dgc_status.py``, and runtime community edition pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DomainContractValidationReport:
    domain: str
    contract_id: str = ""
    status: str = "unknown"  # pass | partial | fail | skip
    required_fields_passed: bool = False
    required_records_passed: bool = False
    evidence_passed: bool = False
    failure_policy_passed: bool = False
    missing_fields: list[str] = field(default_factory=list)
    missing_records: list[str] = field(default_factory=list)
    missing_collections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_CONTRACTS_PATH = Path(__file__).resolve().parents[2] / "configs" / "yaml" / "domain_contracts" / "community_core.yaml"


def _load_contracts() -> dict[str, Any]:
    if not _CONTRACTS_PATH.exists():
        return {}
    with open(_CONTRACTS_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def validate_domain_schema(
    payload: dict[str, Any],
    domain: str,
    *,
    contracts: dict[str, Any] | None = None,
) -> DomainContractValidationReport:
    """Validate an Edition JSON payload against the domain's DGAC P0 commitments.

    Args:
        payload: Edition JSON dict (Community v2.x envelope).
        domain: Domain name (e.g. ``bank_statement``, ``vat_invoice``).
        contracts: Pre-loaded contracts dict (optional; loads from disk if None).

    Returns:
        ``DomainContractValidationReport`` with pass/partial/fail status.
    """
    if contracts is None:
        contracts = _load_contracts()

    report = DomainContractValidationReport(domain=domain)

    domain_contracts = (contracts.get("domains") or {}).get(domain)
    if not domain_contracts:
        report.status = "skip"
        report.warnings.append(f"No DGAC entry for domain={domain}")
        return report

    report.contract_id = domain_contracts.get("domain_contract_version", "")
    p0 = domain_contracts.get("p0_commitment") or {}
    data = payload.get("data") or {}
    fields = data.get("fields") or {}
    records = data.get("records") or []

    # ── Fields validation ──
    field_commitments = p0.get("fields") or {}
    required_fields = field_commitments.get("required") or []
    required_any_fields = field_commitments.get("required_any") or []

    missing_required = [f for f in required_fields if not _field_present(fields, f)]
    report.missing_fields.extend(missing_required)

    if required_any_fields:
        any_present = any(_field_present(fields, f) for f in required_any_fields)
        if not any_present:
            report.missing_fields.append(f"required_any:{','.join(required_any_fields)}")

    report.required_fields_passed = len(report.missing_fields) == 0

    # ── Records validation ──
    record_commitments = p0.get("records") or {}
    required_records = record_commitments.get("required") or []

    missing_recs: list[str] = []
    if required_records:
        if not records:
            missing_recs = list(required_records)
        else:
            for field_name in required_records:
                if not all(_record_has_field(rec, field_name) for rec in records if isinstance(rec, dict)):
                    missing_recs.append(field_name)

    report.missing_records = missing_recs

    # ── Named business collections validation (Community v3) ──
    collection_commitments = p0.get("collections") or {}
    required_collections = list(collection_commitments.get("required") or [])
    profile_name = str(_plain_field_value(fields.get("report_subtype")) or "")
    profiles = collection_commitments.get("profiles") or {}
    profile_contract = profiles.get(profile_name) if isinstance(profiles, dict) else None
    if isinstance(profile_contract, dict):
        required_collections.extend(profile_contract.get("required") or [])
    required_collections = list(dict.fromkeys(str(item) for item in required_collections))
    report.missing_collections = [
        name for name in required_collections if name not in data or not isinstance(data.get(name), list)
    ]
    audit_key = str(collection_commitments.get("audit") or "")
    if audit_key and not isinstance(data.get(audit_key), dict):
        report.missing_collections.append(audit_key)
    report.required_records_passed = not missing_recs and not report.missing_collections

    # ── Evidence check (heuristic) ──
    evidence_ok = _check_evidence_coverage(payload, p0)
    report.evidence_passed = evidence_ok

    # ── Failure policy check ──
    status_block = payload.get("status") or {}
    failure_ok = _check_failure_policy(status_block, p0)
    report.failure_policy_passed = failure_ok

    # ── Overall status ──
    if report.required_fields_passed and report.required_records_passed:
        report.status = "pass"
    elif report.required_fields_passed or report.required_records_passed:
        report.status = "partial"
    else:
        report.status = "fail"

    return report


def _field_present(fields: dict[str, Any], field_name: str) -> bool:
    value = fields.get(field_name)
    if value is None:
        return False
    if isinstance(value, dict):
        normalized = value.get("normalized_value") or value.get("raw_value")
        return bool(str(normalized or "").strip())
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _plain_field_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("normalized_value", "value", "raw_value", "raw"):
        if value.get(key) not in (None, ""):
            return value[key]
    return None


def _record_has_field(record: dict[str, Any], field_name: str) -> bool:
    """Map DGAC record field names to community v2 record shapes."""
    normalized = record.get("normalized") or {}
    raw = record.get("raw") or {}
    aliases = {
        "transaction_date": ("date", "timestamp", "transaction_date", "交易日期", "交易时间"),
        "amount": ("amount", "amount_cny", "交易金额", "收入金额", "支出金额"),
        "trade_no": ("trade_no", "transaction_id", "交易单号"),
        "timestamp": ("timestamp", "date", "交易时间"),
        "balance": ("balance", "账户余额", "余额"),
        "counter_party": ("counter_party", "对方户名", "交易对方", "对方账号与户名"),
        "counter_account": ("counter_account", "对方账号"),
        "summary": ("summary", "摘要", "交易用途"),
    }
    for key in aliases.get(field_name, (field_name,)):
        if key in normalized and normalized.get(key) not in (None, ""):
            if key in ("amount", "amount_cny") and normalized.get(key) == 0:
                continue
            return True
        if key in raw and str(raw.get(key) or "").strip():
            return True
    return False


def _check_evidence_coverage(payload: dict[str, Any], p0: dict[str, Any]) -> bool:
    """Heuristic: check if evidence keys exist in payload."""
    # For now, check if validation block has evidence_passed
    validation = payload.get("validation") or {}
    if isinstance(validation, dict):
        domain_contract = validation.get("domain_contract") or {}
        if domain_contract.get("evidence_passed") is True:
            return True
    # Presence of evidence_refs in data or metadata is a positive signal
    data = payload.get("data") or {}
    if data.get("evidence_refs"):
        return True
    meta = payload.get("metadata") or {}
    if meta.get("evidence_bundle"):
        return True
    return False


def _check_failure_policy(status_block: dict[str, Any], p0: dict[str, Any]) -> bool:
    """Check that failure statuses are mapped to known taxonomy."""
    failure_map = p0.get("failure") or {}
    if not failure_map:
        return True  # No failure policy defined
    current_status = status_block.get("status") or status_block.get("success")
    if current_status is True:
        return True
    if current_status is False and status_block.get("warnings"):
        return True  # partial with explanation
    return bool(status_block.get("failure_policy_applied") or status_block.get("fallback_from_domain"))


def get_domain_contract_version(domain: str, *, contracts: dict[str, Any] | None = None) -> str:
    """Return the ``domain_contract_version`` string for a domain."""
    if contracts is None:
        contracts = _load_contracts()
    domain_entry = (contracts.get("domains") or {}).get(domain)
    if not domain_entry:
        return ""
    return domain_entry.get("domain_contract_version", "")


def apply_domain_contract_validation(payload: dict[str, Any], domain: str) -> DomainContractValidationReport:
    """Validate Community payload and publish one canonical validation block."""
    report = validate_domain_schema(payload, domain)
    if report.status == "skip":
        return report

    status = payload.setdefault("status", {})
    contract_warning_prefixes = (
        "missing_identity_field:",
        "missing_required_field:",
        "missing_required_record_field:",
        "partial_missing_required:",
    )
    warnings = [
        str(warning)
        for warning in (status.get("warnings") or [])
        if not str(warning).startswith(contract_warning_prefixes)
    ]

    status["warnings"] = warnings
    if report.status in ("partial", "fail") and report.missing_fields:
        status.setdefault("success", True)

    contract_block = {
        "contract_id": report.contract_id,
        "status": report.status,
        "required_fields_passed": report.required_fields_passed,
        "required_records_passed": report.required_records_passed,
        "missing_fields": list(report.missing_fields),
        "missing_records": list(report.missing_records),
        "missing_collections": list(report.missing_collections),
    }
    payload.setdefault("validation", {})["domain_contract"] = contract_block
    return report
