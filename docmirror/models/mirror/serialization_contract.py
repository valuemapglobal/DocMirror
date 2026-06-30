# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Mirror JSON serialization contract (Design 21).

Centralizes counts, roles, physical-table SSOT, quarantine index, and document
identity so vNext mirror serialization stays unambiguous.
"""

from __future__ import annotations

import re
from typing import Any

MIRROR_CONTRACT_VERSION = "1.1"

DEPRECATED_META_COUNT_ALIASES = (
    "table_count",
    "physical_table_count",
    "logical_table_count",
    "row_count",
)


def plugin_domain_hint(document_type: str) -> str:
    """Map Mirror ``document.type`` / scene to community plugin domain."""
    mapping = {
        "bank_reconciliation": "bank_statement",
    }
    return mapping.get(document_type or "", document_type or "unknown")


_PROSE_DISCLAIMER_MARKERS = (
    "本证明",
    "免责声明",
    "温馨提示",
    "仅供参考",
    "证明事项",
    "不作",
    "历史交易记录情况",
)


def is_prose_disclaimer_table(headers: list[str], raw_rows: list[list[str]]) -> bool:
    """Detect annex/disclaimer prose tables (Alipay p44, WeChat tail pages)."""
    joined_headers = " ".join(str(h or "") for h in headers)
    if any(marker in joined_headers for marker in _PROSE_DISCLAIMER_MARKERS):
        return True
    for row in raw_rows[:4]:
        cells = [str(c or "") for c in row]
        if not any(c.strip() for c in cells):
            continue
        row_text = " ".join(cells)
        if any(marker in row_text for marker in _PROSE_DISCLAIMER_MARKERS):
            return True
        first = cells[0].strip()
        if re.match(r"^\d+[\.．、]", first):
            return True
    return False


def infer_header_source(headers: list[str], raw_rows: list[list[str]]) -> str:
    """Classify how the first raw row relates to table headers."""
    if not raw_rows:
        return "none"
    first = [str(c or "") for c in raw_rows[0]]
    if not any(c.strip() for c in first):
        return "none"
    if is_prose_disclaimer_table(headers, raw_rows):
        return "prose_block"
    from docmirror.layout.vocabulary import _is_header_row, _score_header_by_vocabulary

    categories = ["BANK_STATEMENT", "WECHAT_PAYMENT"]
    score = _score_header_by_vocabulary(first, categories=categories)
    if score >= 2 or _is_header_row(first):
        return "vocabulary_match"
    hdr = [str(h or "") for h in headers]
    if hdr and hdr == first:
        return "inherited"
    if hdr and hdr != first and any(hdr):
        return "data_row"
    return "data_row"


def infer_content_role(
    *,
    header_source: str,
    page_number: int | None,
    annex_pages: set[int] | frozenset[int],
) -> str:
    if page_number is not None and page_number in annex_pages:
        return "annex"
    if header_source == "prose_block":
        return "prose"
    return "ledger"


def header_row_index_for(raw_rows: list[list[str]], header_source: str) -> int:
    if not raw_rows:
        return 0
    if header_source in ("vocabulary_match", "inherited", "prose_block", "none"):
        return 0
    return 0


def enrich_physical_table_dict(
    table: dict[str, Any],
    *,
    page_number: int | None = None,
    annex_pages: set[int] | frozenset[int] | None = None,
) -> dict[str, Any]:
    """Apply Design 21 physical-table SSOT fields."""
    out = dict(table)
    raw_rows = out.get("raw_rows")
    if not raw_rows:
        headers = [str(h) for h in (out.get("headers") or [])]
        rows = out.get("rows") or []
        body: list[list[str]] = []
        for row in rows:
            if isinstance(row, dict):
                body.append([str(c.get("text", "") if isinstance(c, dict) else c) for c in (row.get("cells") or [])])
            else:
                body.append([str(c) for c in row])
        raw_rows = ([headers] + body) if headers else body
    raw_rows = [[str(c) for c in row] for row in raw_rows if isinstance(row, (list, tuple))]
    out["raw_rows"] = raw_rows
    out["ssot"] = "raw_rows"
    headers = [str(h) for h in (out.get("headers") or [])]
    header_source = infer_header_source(headers, raw_rows)
    out["header_source"] = header_source
    out["header_row_index"] = header_row_index_for(raw_rows, header_source)
    page_num = page_number if page_number is not None else out.get("page")
    out["content_role"] = infer_content_role(
        header_source=header_source,
        page_number=int(page_num) if page_num is not None else None,
        annex_pages=annex_pages or frozenset(),
    )
    table_id = str(out.get("table_id") or "")
    if table_id:
        out["navigation_ref"] = f"table:{table_id}"
    return out


def annex_pages_from_logical_tables(logical_tables: list[Any]) -> set[int]:
    pages: set[int] = set()
    for lt in logical_tables:
        if logical_table_role(lt) != "annex":
            continue
        for page in getattr(lt, "source_pages", None) or []:
            try:
                pages.add(int(page))
            except (TypeError, ValueError):
                continue
    return pages


def _physical_rows_on_pages(pages: list[dict[str, Any]], page_filter: set[int]) -> int:
    total = 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_num = int(page.get("page_number") or 0)
        if page_num not in page_filter:
            continue
        for table in page.get("tables") or []:
            if not isinstance(table, dict):
                continue
            total += int(table.get("row_count") or len(table.get("rows") or []) or 0)
    return total


def build_count_reconciliation(
    *,
    counts: dict[str, int],
    logical_tables: list[Any],
    pages: list[dict[str, Any]] | None,
) -> dict[str, int]:
    export_pages: set[int] = set()
    for lt in logical_tables:
        if logical_table_role(lt) != "primary":
            continue
        for page in getattr(lt, "source_pages", None) or []:
            try:
                export_pages.add(int(page))
            except (TypeError, ValueError):
                continue
    annex_rows = sum(
        int(getattr(lt, "row_count", 0) or 0) for lt in logical_tables if logical_table_role(lt) == "annex"
    )
    page_list = pages or []
    physical_in_export = _physical_rows_on_pages(page_list, export_pages) if export_pages else 0
    if not export_pages and page_list:
        physical_in_export = counts["physical_data_rows"] - annex_rows
    cross_page_merge_adjustment = counts["logical_data_rows_export"] - physical_in_export
    return {
        "annex_data_rows": int(annex_rows),
        "physical_rows_in_export_pages": int(physical_in_export),
        "cross_page_merge_adjustment": int(cross_page_merge_adjustment),
    }


def link_blocks_to_tables(blocks: list[dict[str, Any]], tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Design 21 B2 — bidirectional block ↔ physical table navigation links."""
    table_by_id = {str(t.get("table_id")): t for t in tables if t.get("table_id")}
    linked: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            linked.append(block)
            continue
        blk = dict(block)
        table_id = str(blk.get("table_id") or blk.get("audit", {}).get("table_id") or "")
        ref = str(blk.get("ref") or "")
        if not table_id and ref.startswith("table:"):
            table_id = ref.split(":", 1)[-1]
        if not table_id and blk.get("morphology") == "S2" and len(tables) == 1:
            table_id = str(tables[0].get("table_id") or "")
        table = table_by_id.get(table_id) if table_id else None
        if table:
            nav = str(table.get("navigation_ref") or f"table:{table_id}")
            blk.setdefault("table_id", table_id)
            blk.setdefault("ref", nav)
            blk["navigation_ref"] = nav
            table.setdefault("block_ref", blk.get("block_id") or blk.get("ref"))
        elif ref.startswith("table:"):
            blk["navigation_ref"] = ref
        linked.append(blk)
    return linked


def logical_table_role(lt: Any) -> str:
    merge = str(getattr(lt, "merge_method", "") or "")
    passed = getattr(lt, "quality_passed", True)
    if merge == "quarantine_standalone" or passed is False:
        return "annex"
    return "primary"


def logical_table_composition(lt: Any) -> dict[str, Any]:
    merge = str(getattr(lt, "merge_method", "") or "none")
    pages = list(getattr(lt, "source_pages", None) or [])
    skip = getattr(lt, "quality_skip_reason", None)
    if merge == "quarantine_standalone":
        topology = "annex"
        merge_policy = "standalone"
        quarantine_reason = skip or "col_count_mismatch"
    elif len(pages) > 1 or merge == "cross_page_continuation":
        topology = "cross_page"
        merge_policy = "continuation"
        quarantine_reason = None
    else:
        topology = "single_page"
        merge_policy = "none"
        quarantine_reason = None
    return {
        "topology": topology,
        "merge_policy": merge_policy,
        "quarantine_reason": quarantine_reason,
        "source_merge_method": merge,
    }


def serialize_logical_table_dict(lt: Any, *, row_serializer, include_debug: bool = False) -> dict[str, Any]:
    from docmirror.tables.compose.ledger_quality import exported_data_row_estimate

    role = logical_table_role(lt)
    payload: dict[str, Any] = {
        "logical_id": lt.logical_id or lt.table_id,
        "table_id": lt.table_id,
        "role": role,
        "composition": logical_table_composition(lt),
        "source_physical_ids": lt.source_physical_ids,
        "headers": lt.headers,
        "rows": [
            {
                "cells": [row_serializer(c) for c in row.cells],
                "row_type": row.row_type.value if hasattr(row.row_type, "value") else row.row_type,
                "confidence": row.confidence,
                "source_page": row.source_page,
                "source_physical_id": row.source_physical_id,
                "source_row_index": row.source_row_index,
                **({"source_cell_refs": row.source_cell_refs} if row.source_cell_refs else {}),
            }
            for row in lt.rows
        ],
        "source_pages": lt.source_pages,
        "page_span": list(lt.page_span),
        "row_count": lt.row_count,
        "confidence": lt.confidence,
        "merge_method": lt.merge_method,
        "merge_confidence": lt.merge_confidence,
        "quality_score": lt.quality_score,
        "quality_passed": lt.quality_passed,
        "quality_skip_reason": lt.quality_skip_reason,
        "data_row_estimate": exported_data_row_estimate(lt),
    }
    if include_debug:
        payload["merge_log"] = lt.merge_log
        payload["merge_audit"] = lt.merge_audit
    return payload


def build_mirror_counts(
    *,
    physical_table_count: int,
    physical_data_rows: int,
    logical_tables: list[Any],
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    export = [lt for lt in logical_tables if logical_table_role(lt) == "primary"]
    annex = [lt for lt in logical_tables if logical_table_role(lt) == "annex"]
    export_rows = sum(int(getattr(lt, "row_count", 0) or 0) for lt in export)
    counts: dict[str, Any] = {
        "physical_tables": int(physical_table_count),
        "physical_data_rows": int(physical_data_rows),
        "logical_tables_total": len(logical_tables),
        "logical_tables_export": len(export),
        "logical_tables_annex": len(annex),
        "logical_data_rows_export": export_rows,
    }
    if logical_tables:
        counts["reconciliation"] = build_count_reconciliation(
            counts=counts,
            logical_tables=logical_tables,
            pages=pages,
        )
    return counts


def build_quarantine_index(logical_tables: list[Any], spe: dict[str, Any] | None) -> dict[str, Any]:
    annex_entries: list[dict[str, Any]] = []
    for lt in logical_tables:
        if logical_table_role(lt) != "annex":
            continue
        pages = list(getattr(lt, "source_pages", None) or [])
        comp = logical_table_composition(lt)
        annex_entries.append(
            {
                "pages": pages,
                "logical_id": str(getattr(lt, "logical_id", "") or getattr(lt, "table_id", "")),
                "reason": comp.get("quarantine_reason") or getattr(lt, "quality_skip_reason", None),
                "action": "standalone_logical_table",
                "row_count": int(getattr(lt, "row_count", 0) or 0),
            }
        )
    physical_count = int((spe or {}).get("quarantined_physical_count") or 0)
    return {
        "physical_count": physical_count,
        "logical_annex_count": len(annex_entries),
        "annex_logical_tables": annex_entries,
    }


def build_document_identity(
    *,
    document_type: str,
    spe: dict[str, Any] | None,
    properties: dict[str, Any],
) -> dict[str, Any]:
    st = spe or {}
    layout = st.get("layout_profile_id") or properties.get("layout_profile_id")
    return {
        "document_type": document_type,
        "structure_class": st.get("primary") or "unknown",
        "scene_hint": document_type,
        "layout_profile_id": layout,
        "plugin_domain_hint": plugin_domain_hint(document_type),
        "extraction_layer": st.get("extraction_layer"),
    }


def build_information_architecture(
    *,
    document: dict[str, Any],
    spe: dict[str, Any] | None,
) -> dict[str, Any]:
    st = spe or {}
    pages = document.get("pages") or []
    has_sections = bool(document.get("sections"))
    has_logical = bool(document.get("logical_tables"))
    has_regions = any((p.get("regions") or []) for p in pages if isinstance(p, dict))
    primary = st.get("primary") or "unknown"
    if has_sections:
        cross_page = "sections"
    elif has_logical:
        cross_page = "logical_tables"
    else:
        cross_page = "none"
    return {
        "primary_carrier": primary.replace("_led", "") if isinstance(primary, str) else primary,
        "navigation": "blocks",
        "cross_page_model": cross_page,
        "has_regions": has_regions,
        "dual_view": bool(st.get("dual_view")),
    }


def build_morphology_slots(page: dict[str, Any]) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    blocks = page.get("blocks") or []
    tables = page.get("tables") or []
    flow = page.get("flow") or {}
    s1_refs = [b.get("ref") for b in blocks if b.get("morphology") == "S1" and b.get("ref")]
    s2_refs = [b.get("ref") for b in blocks if b.get("morphology") == "S2" and b.get("ref")]
    s5_refs = [b.get("ref") for b in blocks if b.get("morphology") == "S5" and b.get("ref")]
    if flow.get("texts") is not None or s1_refs:
        slots["S1"] = {"ssot": "flow.texts", "block_refs": s1_refs}
    if tables:
        nav_refs = [t.get("navigation_ref") for t in tables if t.get("navigation_ref")]
        slots["S2"] = {"ssot": "tables", "block_refs": s2_refs or nav_refs}
    if flow.get("key_values") is not None or s5_refs:
        slots["S5"] = {"ssot": "flow.key_values", "block_refs": s5_refs}
    region_refs = [b.get("ref") for b in blocks if b.get("morphology") in ("S3", "S4") and b.get("ref")]
    if page.get("regions") or region_refs:
        slots["S3_S4"] = {"ssot": "regions", "block_refs": region_refs}
    return slots


def enrich_api_page_contract(
    page: dict[str, Any],
    *,
    annex_pages: set[int] | frozenset[int] | None = None,
) -> dict[str, Any]:
    out = dict(page)
    page_number = int(out.get("page_number") or 0) or None
    tables = [
        enrich_physical_table_dict(
            t,
            page_number=page_number,
            annex_pages=annex_pages or frozenset(),
        )
        for t in (out.get("tables") or [])
        if isinstance(t, dict)
    ]
    blocks = link_blocks_to_tables(list(out.get("blocks") or []), tables)
    out["tables"] = tables
    out["blocks"] = blocks
    if out.get("reading_order"):
        out["reading_order_canonical"] = "reading_order"
    if out.get("reading_order_refs") is not None:
        out["reading_order_ref_status"] = "page_local_projection"
    slots = build_morphology_slots(out)
    if slots:
        out["morphology_slots"] = slots
    return out


def enrich_document_pages(
    pages: list[dict[str, Any]] | None,
    *,
    annex_pages: set[int] | frozenset[int] | None = None,
) -> list[dict[str, Any]]:
    return [
        enrich_api_page_contract(p, annex_pages=annex_pages or frozenset())
        for p in (pages or [])
        if isinstance(p, dict)
    ]


def build_mirror_profile(*, mirror_level: str) -> dict[str, Any]:
    includes = ["logical_tables", "meta.structure", "meta.counts"]
    if mirror_level == "standard":
        includes.extend(["physical_pages", "blocks", "document.identity"])
    elif mirror_level == "forensic":
        includes.extend(["physical_pages", "blocks", "geometry", "annex"])
    return {
        "contract_version": MIRROR_CONTRACT_VERSION,
        "level": mirror_level,
        "includes": includes,
    }


def apply_meta_count_aliases(meta: dict[str, Any], counts: dict[str, Any]) -> None:
    """Populate concise top-level count aliases for mirror metadata."""
    meta["table_count"] = counts["physical_tables"]
    meta["physical_table_count"] = counts["physical_tables"]
    meta["logical_table_count"] = counts["logical_tables_export"]
    meta["row_count"] = counts["physical_data_rows"]


def finalize_structure_spe(
    spe: dict[str, Any],
    *,
    pages: list[dict[str, Any]],
    document: dict[str, Any],
    counts: dict[str, Any],
    quarantine_index: dict[str, Any],
    domain_specific: dict[str, Any] | None,
) -> dict[str, Any]:
    from docmirror.evidence.structure_provenance import apply_page_morphology_spe

    out = apply_page_morphology_spe(
        dict(spe),
        pages=pages,
        domain_specific=domain_specific,
    )
    out["counts"] = dict(counts)
    out["quarantine"] = quarantine_index
    out["physical_table_count"] = counts["physical_tables"]
    out["logical_table_count"] = counts["logical_tables_export"]
    if document.get("morphology_stats"):
        out["morphology_aggregate_ref"] = "document.morphology_stats"
        out.pop("page_morphology_stats", None)
    return out


def filter_identity_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Keep only document-identity fields in properties (Design 21 E5)."""
    drop = {
        "layout_profile_id",
        "layout_profile_id_refined",
        "mirror_ltqg_enabled",
        "mirror_expected_data_rows",
        "mirror_quarantined_physical_count",
        "mirror_quarantined_logical_count",
    }
    return {k: v for k, v in properties.items() if k not in drop and v is not None}


__all__ = [
    "MIRROR_CONTRACT_VERSION",
    "annex_pages_from_logical_tables",
    "apply_meta_count_aliases",
    "build_count_reconciliation",
    "build_document_identity",
    "build_information_architecture",
    "build_mirror_counts",
    "build_mirror_profile",
    "build_morphology_slots",
    "build_quarantine_index",
    "enrich_api_page_contract",
    "enrich_document_pages",
    "enrich_physical_table_dict",
    "filter_identity_properties",
    "finalize_structure_spe",
    "infer_content_role",
    "is_prose_disclaimer_table",
    "link_blocks_to_tables",
    "logical_table_composition",
    "logical_table_role",
    "plugin_domain_hint",
    "serialize_logical_table_dict",
]
