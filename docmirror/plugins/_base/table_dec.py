# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Table-document DEC builders and edition serialization helpers.

Constructs ``DomainExtractionResult`` instances from table extract steps (identity
fields, transaction records, summary) and serializes them to v2.0 edition JSON
with classification metadata. Shared by payment ledger plugins and bank statement.

Pipeline role: ``BaseTableParser.extract_from_mirror`` and
``bank_statement.community_plugin`` call ``build_table_dec`` / ``serialize_table_plugin_output``
before ``runner._finalize_extract`` validates and runs post-extract hooks.

Key exports: ``table_dec_warnings``, ``build_table_dec``, ``serialize_table_plugin_output``.

Dependencies: ``models.entities.domain_result``, ``models.edition_serializer``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from docmirror.models.edition_serializer import EditionContext, edition_serializer
from docmirror.models.entities.domain_result import DomainExtractionResult, DomainQuality


def table_dec_warnings(
    identity_fields: dict[str, Any],
    summary: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if identity_fields:
        if "account_holder" not in identity_fields:
            warnings.append("missing_identity_field:account_holder")
        if "currency" not in identity_fields:
            warnings.append("missing_identity_field:currency")
    if summary.get("total_rows", 0) == 0:
        warnings.append("no_records_extracted")
    return warnings


def build_table_dec(
    *,
    document_type: str,
    identity_fields: dict[str, Any],
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    properties: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> DomainExtractionResult:
    """Build DEC from table-document extract steps."""
    warnings = table_dec_warnings(identity_fields, summary)
    return DomainExtractionResult(
        document_type=document_type,
        properties=dict(properties or {}),
        entities=dict(identity_fields or {}),
        structured_data={
            "records": records,
            "summary": summary,
            "sections": [],
            "tables": [],
            "line_items": [],
        },
        quality=DomainQuality(
            validation_passed=summary.get("total_rows", 0) > 0,
            issues=[f"warning:{w}" for w in warnings],
        ),
        metadata=dict(metadata or {}),
    )


def serialize_table_plugin_output(
    plugin: Any,
    parse_result: Any,
    *,
    identity_fields: dict[str, Any],
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    text: str = "",
    domain: str = "cashflow_payment",
    match_method: str = "keyword_layout_hybrid",
) -> dict[str, Any]:
    """Mirror → DEC → edition v2.0 for table_document plugins."""
    file_path = getattr(parse_result, "file_path", "") or ""
    doc_name = Path(file_path).name if file_path else getattr(plugin, "display_name", "")
    page_count = len(getattr(parse_result, "pages", []) or [])

    dec = build_table_dec(
        document_type=getattr(plugin, "domain_name", "unknown"),
        identity_fields=identity_fields,
        records=records,
        summary=summary,
    )
    ctx = EditionContext(
        edition=getattr(plugin, "edition", "community"),
        detected_type=getattr(plugin, "domain_name", "unknown"),
        full_text=text,
        document_name=doc_name,
        page_count=page_count,
        archetype="table_document",
        domain=domain,
        match_method=match_method,
        scene_keywords=getattr(plugin, "scene_keywords", ()) or (),
        plugin_name=getattr(plugin, "domain_name", "unknown"),
        plugin_display_name=getattr(plugin, "display_name", ""),
        plugin_version="community-2.0",
        support_level="L2",
        parser_label="docmirror-community",
    )
    return edition_serializer(dec, context=ctx)
