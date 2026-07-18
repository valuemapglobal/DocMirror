# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
KV community plugin extract helper for premium L2 key-value documents.

Builds v2.0 community edition output for plugins whose primary archetype is
key-value (VAT invoice, business license, credit report): match identity labels
against Mirror KV pairs and entities, collect table records as structured data,
and serialize via ``edition_serializer``.

Pipeline role: called from domain ``community_plugin.extract_from_mirror`` methods;
``runner`` may also reach KV output through ``build_domain_data`` + ``dec_builder``.

Key exports: ``extract_kv_community_output``.

Dependencies: ``generic_mirror_adapter`` (field/record collectors),
``models.edition_serializer``, ``models.entities.domain_result``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from docmirror.models.edition_serializer import EditionContext, edition_serializer
from docmirror.models.entities.domain_result import DomainExtractionResult, DomainQuality
from docmirror.models.mirror.block_fields import collect_kv_fields_from_blocks
from docmirror.plugins._base.generic_mirror_adapter import _collect_entity_fields, _collect_table_records


def _match_identity_fields(
    parse_result: Any,
    identity_specs: Sequence[tuple[str, Sequence[str]]],
    entity_dict: dict[str, Any],
    full_text: str = "",
) -> dict[str, Any]:
    """Map identity field keys using entity dict + KV label matching."""
    out: dict[str, Any] = {}
    for field_key, labels in identity_specs:
        if field_key in entity_dict and entity_dict[field_key]:
            out[field_key] = entity_dict[field_key]
            continue
        for page in getattr(parse_result, "pages", []) or []:
            for kv in getattr(page, "key_values", []) or []:
                key = (getattr(kv, "key", None) or "").strip()
                val = (getattr(kv, "value", None) or "").strip()
                if not val:
                    continue
                if any(label in key for label in labels):
                    out[field_key] = val
                    break
            if field_key in out:
                break
    if full_text:
        for key, value in _recover_identity_fields_from_text(full_text, identity_specs).items():
            out.setdefault(key, value)
    return out


def _label_pattern(label: str) -> str:
    parts = []
    for part in re.split(r"\s+", label.strip()):
        if not part:
            continue
        if re.fullmatch(r"[\u3400-\u9fff]+", part):
            parts.append(r"\s*".join(re.escape(char) for char in part))
        else:
            parts.append(re.escape(part))
    return r"\s+".join(parts)


def _recover_identity_fields_from_text(
    full_text: str,
    identity_specs: Sequence[tuple[str, Sequence[str]]],
) -> dict[str, str]:
    """Recover label/value facts when PDF extraction splits every visual word."""
    text = re.sub(r"\s+", " ", full_text or "").strip()
    if not text:
        return {}
    labels = sorted(
        {label.strip() for _field, candidates in identity_specs for label in candidates if label.strip()},
        key=len,
        reverse=True,
    )
    if not labels:
        return {}
    structural_boundaries = ("Date", "Transaction", "Description", "Amount", "Balance", "Note", "Type")
    all_boundaries = sorted({*labels, *structural_boundaries}, key=len, reverse=True)
    boundary = "|".join(_label_pattern(label) for label in all_boundaries)
    recovered: dict[str, str] = {}
    for field_name, candidates in identity_specs:
        for label in sorted(candidates, key=len, reverse=True):
            pattern = re.compile(
                rf"(?:^|\s){_label_pattern(label)}\s*[:：]?\s*(.+?)(?=\s+(?:{boundary})\s*[:：]?|$)",
                re.IGNORECASE,
            )
            match = pattern.search(text)
            if not match:
                continue
            value = match.group(1).strip(" \t:：,，;；*")
            if value and len(value) <= 500 and value.strip("*·-— "):
                recovered[field_name] = value
                break
    return recovered


def _collect_identity_field_metadata(
    parse_result: Any,
    fields: dict[str, Any],
    identity_specs: Sequence[tuple[str, Sequence[str]]],
    full_text: str = "",
) -> dict[str, Any]:
    """Preserve where each KV business field came from without wrapping its value."""
    metadata: dict[str, Any] = {}
    labels_by_field = {field: tuple(labels) for field, labels in identity_specs}
    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        for kv in getattr(page, "key_values", []) or []:
            raw_key = str(getattr(kv, "key", "") or "").strip()
            for field_name, labels in labels_by_field.items():
                if field_name not in fields or field_name in metadata:
                    continue
                if not any(label in raw_key for label in labels):
                    continue
                item: dict[str, Any] = {
                    "source": "mirror_key_value",
                    "source_label": raw_key,
                    "page": page_number,
                    "confidence": round(float(getattr(kv, "confidence", 0.0) or 0.0), 4),
                }
                bbox = getattr(kv, "bbox", None)
                if bbox:
                    item["bbox"] = list(bbox)
                evidence_ids = list(getattr(kv, "evidence_ids", []) or [])
                if evidence_ids:
                    item["evidence_ids"] = evidence_ids
                metadata[field_name] = item
    if full_text:
        for field_name in fields:
            metadata.setdefault(field_name, {"source": "full_text", "confidence": 0.7})
    return metadata


def extract_kv_community_output(
    plugin: Any,
    parse_result: Any,
    *,
    identity_specs: Sequence[tuple[str, Sequence[str]]],
    full_text: str = "",
    match_method: str = "keyword_kv_hybrid",
    support_level: str = "L2",
) -> dict[str, Any]:
    """Build v2.0 community output for key-value premium plugins."""
    detected_type = getattr(plugin, "domain_name", "unknown")
    entity_pool = _collect_entity_fields(parse_result)
    block_kv = collect_kv_fields_from_blocks(parse_result)
    for key, value in block_kv.items():
        entity_pool.setdefault(key, value)
    fields = _match_identity_fields(parse_result, identity_specs, entity_pool, full_text)
    if not fields:
        fields = {k: v for k, v in entity_pool.items() if v not in (None, "")}
    field_metadata = _collect_identity_field_metadata(parse_result, fields, identity_specs, full_text)

    records = _collect_table_records(parse_result)
    file_path = getattr(parse_result, "file_path", "") or ""
    doc_name = Path(file_path).name if file_path else getattr(plugin, "display_name", detected_type)
    page_count = len(getattr(parse_result, "pages", []) or [])

    warnings: list[str] = []
    if not fields:
        warnings.append("no_fields_extracted")

    dec = DomainExtractionResult(
        document_type=detected_type,
        properties={},
        entities=fields,
        structured_data={
            "records": records,
            "summary": {"total_rows": len(records)},
            "sections": [],
            "tables": [],
            "line_items": [],
            "field_metadata": field_metadata,
        },
        quality=DomainQuality(
            validation_passed=bool(fields or records),
            issues=[f"warning:{w}" for w in warnings],
        ),
    )

    ctx = EditionContext(
        edition="community",
        detected_type=detected_type,
        full_text=full_text,
        document_name=doc_name,
        page_count=page_count,
        archetype="key_value_document",
        domain=detected_type,
        match_method=match_method,
        scene_keywords=getattr(plugin, "scene_keywords", ()) or (),
        plugin_name=detected_type,
        plugin_display_name=getattr(plugin, "display_name", detected_type),
        plugin_version="community-2.0",
        support_level=support_level,
        parser_label="docmirror-community",
    )
    return edition_serializer(dec, context=ctx)


def _enforce_dgc_boundary(domain: str, support_level: str) -> dict:
    """Enforce DGC (domain governance category) boundary rules for Edition output.

    GA 1.0 SS4.12 N2/N5: DGC status gates Edition output:

      - **"ga"** domain (e.g., bank_statement, credit_report):
        Keeps the provided support_level. No output restriction.
      - **"candidate"** domain (e.g., vat_invoice, business_license):
        Downgraded to L1 (generic fallback fields only).
        Edition output is NOT blocked — only restricted to L1.
      - **"mirror_only"** / **"unknown"** domain:
        Edition output is blocked entirely. Only mirror output is available.

    Args:
        domain: Document domain name (e.g. "bank_statement", "vat_invoice").
        support_level: Requested support level ("L1", "L2", etc.).

    Returns:
        A gate dict with keys:
          - effective_support_level: The support level after applying rules.
          - dgc_status: The resolved DGC status for the domain.
          - block_edition: Whether edition output should be suppressed.
          - dgc_annotation: Human-readable explanation for the gating decision.
    """
    from docmirror.plugins._runtime.plugin_registry import resolve_dgc_status

    if not domain:
        return {
            "effective_support_level": "mirror_only",
            "dgc_status": "mirror_only",
            "block_edition": True,
            "dgc_annotation": "DGC gate: empty domain — edition output suppressed (GA 1.0 N2)",
        }

    dgc_status = resolve_dgc_status(domain)

    if dgc_status == "ga":
        return {
            "effective_support_level": support_level,
            "dgc_status": dgc_status,
            "block_edition": False,
            "dgc_annotation": f"DGC gate: {domain!r} is GA domain — support_level={support_level}",
        }

    if dgc_status == "candidate":
        return {
            "effective_support_level": "L1",
            "dgc_status": dgc_status,
            "block_edition": False,
            "dgc_annotation": f"DGC gate: {domain!r} is candidate domain — downgraded to L1 generic fallback (GA 1.0 N5)",
        }

    # mirror_only / unknown → block edition output
    return {
        "effective_support_level": "mirror_only",
        "dgc_status": dgc_status,
        "block_edition": True,
        "dgc_annotation": f"DGC gate: {domain!r} is mirror_only domain — edition output suppressed (GA 1.0 N2)",
    }
