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

from docmirror.plugins.bank_statement.canonical import StyleMeta, build_style_meta
from docmirror.plugins.bank_statement.context import StyleContext, build_style_context
from docmirror.plugins.bank_statement.institution_authority import extract_identity_from_header
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector, StyleDetectionResult
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry


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
) -> dict[str, dict]:
    """Merge header KV identity into registry identity fields."""
    fields = dict(identity_fields)
    for field_name, value in extract_identity_from_header(full_text).items():
        if value and field_name not in fields:
            fields[field_name] = {
                "raw_name": field_name,
                "raw_value": value,
                "normalized_value": value,
                "data_type": "string",
            }
    return fields


def collect_extract_warnings(ctx: StyleContext, style_meta: StyleMeta) -> list[str]:
    """LTRO / coverage warnings shared across editions."""
    from docmirror.core.analyze.spe_consumer import read_structure_spe, spe_ltro_warnings

    warnings: list[str] = []
    if ctx.reconstruction and ctx.reconstruction.pipe_parse_failed:
        warnings.append("pipe_parse_failed:no_silent_ocr_fallback")
    expected = style_meta.expected_primary_rows
    extracted = style_meta.extracted_rows
    if expected > 0 and extracted / expected < 0.8:
        warnings.append("low_coverage:bank_ledger")
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
    records, identity_fields = BankStyleParserRegistry().run(detection, ctx, plugin)
    identity_fields = enrich_identity_fields(identity_fields, ctx.full_text)
    style_meta = build_style_meta(
        detection,
        reconstruction=ctx.reconstruction,
        record_count=len(records),
    )
    warnings = collect_extract_warnings(ctx, style_meta)
    return BankExtractResult(
        ctx=ctx,
        detection=detection,
        records=records,
        identity_fields=identity_fields,
        style_meta=style_meta,
        warnings=warnings,
    )
