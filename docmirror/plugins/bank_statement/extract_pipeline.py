# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Shared bank statement extract pipeline for Community / Enterprise / Finance.

Single SSOT for StyleContext → StyleDetector → ParserRegistry → identity enrichment
→ style metadata → LTRO audit warnings.

Pipeline role: called by ``community_plugin.extract_from_mirror`` and extended-edition
``extract()`` methods in ``docmirror_enterprise`` / ``docmirror_finance``.

Key exports: ``BankExtractResult``, ``run_bank_statement_extract``,
``enrich_identity_fields``, ``collect_extract_warnings``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docmirror.plugins.bank_statement.blo import BankLedgerOrchestrator
from docmirror.plugins.bank_statement.canonical import StyleMeta, build_style_meta
from docmirror.plugins.bank_statement.context import StyleContext, build_style_context
from docmirror.plugins.bank_statement.institution_authority import (
    extract_identity_from_header,
    resolve_institution_from_context,
)
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector, StyleDetectionResult
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
from docmirror.plugins.bank_statement.wide_table_recovery import audit_bank_statement_invariants


@dataclass
class BankExtractResult:
    ctx: StyleContext
    detection: StyleDetectionResult
    records: list[dict[str, Any]]
    identity_fields: dict[str, dict]
    style_meta: StyleMeta
    warnings: list[str]


def enrich_identity_fields(
    identity_fields: dict[str, dict],
    full_text: str,
    parse_result: Any = None,
    institution: str | None = None,
) -> dict[str, dict]:
    """Merge header KV identity into registry identity fields (EIP)."""
    fields = dict(identity_fields)
    for field_name, value in extract_identity_from_header(full_text).items():
        if not value:
            continue
        fields[field_name] = {
            "raw_name": field_name,
            "raw_value": value,
            "normalized_value": value,
            "data_type": "string",
            "source": "header.kv",
        }
    if "currency" not in fields:
        fields["currency"] = {
            "raw_name": "currency",
            "raw_value": "CNY",
            "normalized_value": "CNY",
            "data_type": "string",
            "source": "bank_statement.default",
        }

    if parse_result is not None:
        entities = getattr(parse_result, "entities", None)
        metadata = getattr(entities, "metadata", None) if entities is not None else None
        if isinstance(metadata, dict):
            for field_name in (
                "account_holder",
                "account_number",
                "bank_name",
                "query_period",
                "currency",
            ):
                value = metadata.get(field_name)
                if value and field_name not in fields:
                    fields[field_name] = {
                        "raw_name": field_name,
                        "raw_value": str(value),
                        "normalized_value": str(value),
                        "data_type": "string",
                        "source": "metadata",
                    }
        if entities is not None:
            for field_name in ("account_holder", "account_number", "bank_name"):
                value = getattr(entities, field_name, None)
                if value and field_name not in fields:
                    fields[field_name] = {
                        "raw_name": field_name,
                        "raw_value": str(value),
                        "normalized_value": str(value),
                        "data_type": "string",
                        "source": "entities",
                    }
            subject_id = getattr(entities, "subject_id", None)
            if subject_id and "account_number" not in fields:
                fields["account_number"] = {
                    "raw_name": "subject_id",
                    "raw_value": str(subject_id),
                    "normalized_value": str(subject_id),
                    "data_type": "string",
                    "source": "entities.subject_id",
                }
        if institution and "bank_name" not in fields:
            fields["bank_name"] = {
                "raw_name": "bank_name",
                "raw_value": institution,
                "normalized_value": institution,
                "data_type": "string",
                "source": "institution_argument",
            }
        if "bank_name" not in fields:
            institution, authority = resolve_institution_from_context(parse_result, full_text)
            if institution:
                fields["bank_name"] = {
                    "raw_name": "bank_name",
                    "raw_value": institution,
                    "normalized_value": institution,
                    "data_type": "string",
                    "source": authority or "institution_authority",
                }
    return fields


def collect_extract_warnings(ctx: StyleContext, style_meta: StyleMeta) -> list[str]:
    """LTRO / coverage warnings shared across editions."""
    from docmirror.evidence.spe_consumer import read_structure_spe, spe_ltro_warnings

    warnings: list[str] = []
    if ctx.reconstruction and ctx.reconstruction.pipe_parse_failed:
        warnings.append("pipe_parse_failed:no_silent_ocr_fallback")
    expected = style_meta.expected_primary_rows
    extracted = style_meta.extracted_rows
    if expected > 0 and extracted / expected < 0.8:
        warnings.append("low_coverage:bank_ledger")
    if style_meta.extract_status == "degraded":
        warnings.append("cqf_degraded:canonical_quality")
    elif style_meta.extract_status == "low_coverage":
        warnings.append("cqf_low_coverage:canonical_quality")
    if ctx.parse_result is not None:
        spe = read_structure_spe(ctx.parse_result)
        source = style_meta.reconstruction_source or (ctx.reconstruction.source if ctx.reconstruction else "")
        warnings.extend(spe_ltro_warnings(spe, source))
    return warnings


def run_bank_statement_extract(
    parse_result: Any,
    full_text: str,
    plugin: Any,
) -> BankExtractResult:
    """Run the canonical bank-statement extract pipeline."""
    ctx = build_style_context(parse_result, full_text)
    detection = BankStyleDetector().detect(ctx)
    registry = BankStyleParserRegistry()
    records, identity_fields, blo_meta = BankLedgerOrchestrator(registry).run(
        detection,
        ctx,
        plugin,
    )
    identity_fields = enrich_identity_fields(identity_fields, ctx.full_text, parse_result)
    style_meta = build_style_meta(
        detection,
        reconstruction=ctx.reconstruction,
        record_count=len(records),
        parse_result=parse_result,
        records=records,
        blo_meta=blo_meta,
    )
    warnings = collect_extract_warnings(ctx, style_meta)
    invariant_failures = audit_bank_statement_invariants(records, ctx.full_text)
    if invariant_failures:
        style_meta.extract_status = "degraded"
        warnings.extend(invariant_failures)
    return BankExtractResult(
        ctx=ctx,
        detection=detection,
        records=records,
        identity_fields=identity_fields,
        style_meta=style_meta,
        warnings=warnings,
    )
