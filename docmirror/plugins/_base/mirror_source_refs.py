# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror source refs computer — computes source_fact_ids and evidence_ids
from a ParseResult's Mirror fact graph for edition metadata enrichment.

GA 1.0 design §8.3 ED-3: Plugin source refs contract. Every community plugin
edition output must expose source_fact_ids and evidence_ids in its metadata
so that the projection resolver can establish lineage.
"""

from __future__ import annotations

from typing import Any

from docmirror.models.mirror.fact_identity import (
    fact_id_for_cell,
    fact_id_for_page,
    fact_id_for_table,
    fact_id_for_text_block,
)


def compute_source_fact_ids(parse_result: Any) -> list[str]:
    """Compute source fact_ids from a ParseResult's Mirror tables and texts.

    Walks all pages, tables, text blocks and generates stable fact_ids.
    Returns a deduplicated sorted list.
    """
    fact_ids: set[str] = set()
    pages = list(getattr(parse_result, "pages", []) or [])

    for page_idx, page in enumerate(pages, start=1):
        fact_ids.add(fact_id_for_page(page_idx))

        # Text blocks
        for text_idx, _text in enumerate(getattr(page, "texts", []) or []):
            fact_ids.add(fact_id_for_text_block(page_idx, text_idx))

        # Tables and cells
        for table_idx, table in enumerate(getattr(page, "tables", []) or []):
            fact_ids.add(fact_id_for_table(page_idx, table_idx))
            data_rows = list(
                getattr(table, "data_rows", [])
                or getattr(table, "rows", [])
                or []
            )
            for row_idx, row in enumerate(data_rows):
                for col_idx, _cell in enumerate(getattr(row, "cells", []) or []):
                    fact_ids.add(
                        fact_id_for_cell(page_idx, table_idx, row_idx, col_idx)
                    )

    return sorted(fact_ids)


def compute_evidence_ids(fact_ids: list[str]) -> list[str]:
    """Compute evidence IDs from fact IDs (one evidence per fact).

    Returns sorted list of ev: prefixed IDs.
    """
    return sorted(f"ev:{fid}" for fid in fact_ids)


def enrich_edition_with_source_refs(
    edition_output: dict[str, Any],
    parse_result: Any,
) -> dict[str, Any]:
    """Enrich an edition output dict with source_fact_ids and evidence_ids
    in its metadata block.

    Idempotent: does not overwrite existing source_fact_ids if already present.
    """
    if not isinstance(edition_output, dict):
        return edition_output

    meta: dict[str, Any] = edition_output.setdefault("metadata", {})

    if not meta.get("source_fact_ids"):
        try:
            meta["source_fact_ids"] = compute_source_fact_ids(parse_result)
        except Exception:
            pass

    if not meta.get("evidence_ids"):
        src_ids = meta.get("source_fact_ids") or []
        if src_ids:
            meta["evidence_ids"] = compute_evidence_ids(src_ids)

    # Per GA 1.0 §8.3 ED-3, source_fact_ids belong at edition metadata level.
    # Per-record source_fact_ids should be set explicitly by plugins that know
    # the row-to-cell mapping. Never default to the full document-level list.
    # (Leaving per-record fields untouched preserves any plugin-set values.)

    return edition_output


def compact_source_ref_metadata(
    meta: dict[str, Any],
    *,
    mirror_ref: str = "001_mirror.json",
) -> None:
    """Replace bulky fact-id lists with counts and a mirror pointer (in-place)."""
    fact_ids = meta.pop("source_fact_ids", None)
    evidence_ids = meta.pop("evidence_ids", None)
    if not fact_ids and not evidence_ids:
        return
    if fact_ids:
        meta["source_fact_id_count"] = len(fact_ids)
    if evidence_ids:
        meta["evidence_id_count"] = len(evidence_ids)
    meta["source_facts_ref"] = mirror_ref


def compact_projection_lineage_source_refs(
    lineage: dict[str, Any],
    *,
    mirror_ref: str = "001_mirror.json",
) -> None:
    """Drop duplicated fact-id arrays from ``edition_lineage`` (in-place)."""
    edition_lineage = lineage.get("edition_lineage")
    if not isinstance(edition_lineage, dict):
        return
    fact_ids = edition_lineage.pop("source_fact_ids", None)
    evidence_ids = edition_lineage.pop("evidence_ids", None)
    if not fact_ids and not evidence_ids:
        return
    if fact_ids:
        edition_lineage["source_fact_id_count"] = len(fact_ids)
    if evidence_ids:
        edition_lineage["evidence_id_count"] = len(evidence_ids)
    edition_lineage["source_facts_ref"] = mirror_ref


def embed_full_source_refs(evidence_depth: str) -> bool:
    """Whether edition JSON should embed full fact-id lists."""
    return evidence_depth in ("full", "forensic")


__all__ = [
    "compute_source_fact_ids",
    "compute_evidence_ids",
    "enrich_edition_with_source_refs",
    "compact_source_ref_metadata",
    "compact_projection_lineage_source_refs",
    "embed_full_source_refs",
]
