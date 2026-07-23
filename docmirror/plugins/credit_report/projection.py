# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Native credit-report facts without constructing an edition envelope."""

from __future__ import annotations

from typing import Any

from docmirror.plugins._base.projector import ProjectionData

_DEFAULT_RECORD_ID_KEYS = ("record_id", "account_id", "inquiry_id", "public_record_id")
_REPAYMENT_RECORD_ID_KEYS = ("record_id", "repayment_id")


def _records(dataset_id: str, values: Any) -> list[dict[str, Any]]:
    """Give projected business records stable canonical record identities."""
    rows: list[dict[str, Any]] = []
    id_keys = _REPAYMENT_RECORD_ID_KEYS if dataset_id == "repayment_records" else _DEFAULT_RECORD_ID_KEYS
    for index, value in enumerate(values or (), start=1):
        if not isinstance(value, dict):
            continue
        row = dict(value)
        identity = next((row.get(key) for key in id_keys if row.get(key)), None)
        row["record_id"] = str(identity or f"{dataset_id}:r{index:06d}")
        rows.append(row)
    return rows


def _account_structure_warnings(accounts: list[dict[str, Any]]) -> tuple[str, ...]:
    """Keep credit-account completeness policy inside the credit plugin."""
    if not accounts:
        return ()
    collapsed = 0
    for account in accounts:
        required = (
            bool(account.get("open_date")),
            bool(account.get("loan_amount") or account.get("credit_limit")),
            bool(account.get("management_institution")),
        )
        if sum(required) <= 1:
            collapsed += 1
    failure_rate = collapsed / len(accounts)
    if failure_rate <= 0.3:
        return ()
    return (f"credit:account_structure_collapse:failure_rate={failure_rate:.3f}",)


def derive_credit_report_projection(plugin: Any, parse_result: Any, full_text: str = "") -> ProjectionData:
    """Return identity, profile, section, and business datasets as one ProjectionData."""
    from docmirror.plugins._base.kv_community_enrich import (
        _canonicalize_credit_accounts,
        _domain_specific,
        _ensure_credit_repayment_records,
        _extract_credit_accounts_from_local_structure_evidence,
        _has_credit_repayment_structures,
        _recover_credit_subject_identity,
        build_credit_sections_light,
    )
    from docmirror.plugins._base.kv_projection import extract_kv_projection
    from docmirror.plugins.credit_report.business_assembly import assemble_credit_report_business
    from docmirror.plugins.credit_report.report_profile import (
        detect_credit_report_content_mode,
        detect_credit_report_subtype,
        recover_credit_report_header_fields,
    )
    from docmirror.plugins.credit_report.scanned_business import (
        extract_scanned_credit_business,
        link_repayment_records_to_accounts,
    )

    base = extract_kv_projection(
        plugin,
        parse_result,
        identity_specs=plugin.identity_fields,
        full_text=full_text,
        include_block_kv=False,
        include_generic_records=False,
    )
    domain_facts = dict(base.domain_facts)
    field_details = dict(domain_facts.get("field_details") or {})

    for field_name, recovered in _recover_credit_subject_identity(parse_result).items():
        domain_facts.setdefault(field_name, recovered["value"])
        field_details.setdefault(
            field_name,
            {
                "source": "canonical_evidence_atoms",
                "page_id": recovered["page_id"],
                "evidence_ids": recovered["evidence_ids"],
            },
        )

    report_subtype = detect_credit_report_subtype(parse_result, full_text)
    content_mode = detect_credit_report_content_mode(parse_result)
    recovered_header = recover_credit_report_header_fields(
        parse_result,
        full_text,
        report_subtype=report_subtype,
    )
    if report_subtype != "unknown":
        recovered_header.setdefault("report_subtype", report_subtype)
    if content_mode != "unknown":
        recovered_header.setdefault("content_mode", content_mode)
    for field_name, value in recovered_header.items():
        domain_facts[field_name] = value
        field_details[field_name] = {
            "source": "credit_report_header",
            "confidence": 0.95 if field_name not in {"report_subtype", "content_mode"} else 1.0,
        }
    domain_facts["field_details"] = field_details

    source_domain = _domain_specific(parse_result)
    scanned_business: dict[str, Any] = {}
    if content_mode in {"scanned_ocr", "mixed"}:
        scanned_business = extract_scanned_credit_business(parse_result, full_text)

    repayment_records = list(source_domain.get("credit_repayment_records") or [])
    if not repayment_records and (
        content_mode in {"scanned_ocr", "mixed"} or _has_credit_repayment_structures(parse_result)
    ):
        repayment_records = _ensure_credit_repayment_records(parse_result)

    credit_accounts = _canonicalize_credit_accounts(list(scanned_business.get("credit_accounts") or []))
    if not credit_accounts:
        credit_accounts = _canonicalize_credit_accounts(list(source_domain.get("credit_accounts") or []))
    if not credit_accounts:
        credit_accounts = _canonicalize_credit_accounts(
            _extract_credit_accounts_from_local_structure_evidence(parse_result)
        )

    from docmirror.models.mirror.domain_access import micro_grid_structures_from_domain_specific

    repayment_records = link_repayment_records_to_accounts(
        repayment_records,
        credit_accounts,
        micro_grid_structures_from_domain_specific(source_domain),
    )
    assembled = assemble_credit_report_business(
        parse_result,
        full_text,
        report_subtype=report_subtype,
        content_mode=content_mode,
        existing_collections={
            "credit_accounts": credit_accounts,
            "credit_lines": [],
            "repayment_records": repayment_records,
            "overdue_records": [],
            "inquiry_records": list(scanned_business.get("inquiry_records") or []),
            "public_records": [],
        },
        existing_summary=dict(scanned_business.get("credit_summary") or {}),
    )
    dataset_names = (
        "credit_accounts",
        "credit_lines",
        "repayment_records",
        "overdue_records",
        "inquiry_records",
        "public_records",
    )
    datasets = {name: rows for name in dataset_names if (rows := _records(name, assembled.get(name)))}
    if assembled.get("credit_summary"):
        domain_facts["credit_summary"] = dict(assembled["credit_summary"])
    if assembled.get("credit_extraction_audit"):
        domain_facts["credit_extraction_audit"] = dict(assembled["credit_extraction_audit"])

    entity_fields = dict(base.entity_fields)
    if domain_facts.get("subject_name"):
        entity_fields["subject_name"] = domain_facts["subject_name"]
    if domain_facts.get("id_number"):
        entity_fields["subject_id"] = domain_facts["id_number"]
    warnings = tuple(dict.fromkeys((*base.warnings, *_account_structure_warnings(credit_accounts))))
    return ProjectionData(
        projector_id=base.projector_id,
        document_type=base.document_type,
        entity_fields=entity_fields,
        domain_facts=domain_facts,
        datasets=datasets,
        sections=tuple(build_credit_sections_light(parse_result, full_text)),
        warnings=warnings,
        evidence_ids=base.evidence_ids,
        confidence=base.confidence,
        reason="post-seal credit-report projection",
    )


__all__ = ["derive_credit_report_projection"]
