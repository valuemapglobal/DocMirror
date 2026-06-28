# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fold legacy mirror JSON into page-centric regions (offline migration tool)."""

from __future__ import annotations

from typing import Any

from docmirror.structure.ocr.page_canvas.block_index import build_page_blocks, pcm_blocks_enabled
from docmirror.structure.ocr.page_canvas.build import (
    build_page_regions_for_page,
    compact_region_structure,
    reading_order_for_page,
    region_from_local_structure,
    region_from_micro_grid,
)
from docmirror.structure.ocr.page_canvas.flow_filter import filter_flow_texts_not_in_regions
from docmirror.structure.ocr.page_canvas.models import PageFlow, PageRegion


def _ocr_ref_for_page(document: dict[str, Any], page: int) -> str | None:
    for item in document.get("scanned_ocr_pages") or []:
        if isinstance(item, dict) and int(item.get("page") or 0) == page:
            return str(item.get("ocr_page_id") or "") or None
    for evidence in document.get("scanned_micro_grid_evidence") or []:
        if isinstance(evidence, dict) and int(evidence.get("page") or 0) == page:
            ref = evidence.get("ocr_page_ref")
            if ref:
                return str(ref)
    for evidence in document.get("scanned_local_structure_evidence") or []:
        if isinstance(evidence, dict) and int(evidence.get("page") or 0) == page:
            ref = evidence.get("ocr_page_ref")
            if ref:
                return str(ref)
    return None


def collect_legacy_sources(document: dict[str, Any], page: int) -> tuple[list[dict], list[dict]]:
    micro_grids = [
        g for g in (document.get("micro_grids") or []) if isinstance(g, dict) and int(g.get("page") or 0) == page
    ]
    structures: list[dict] = []
    for evidence in document.get("scanned_local_structure_evidence") or []:
        if not isinstance(evidence, dict) or int(evidence.get("page") or 0) != page:
            continue
        for structure in evidence.get("structures") or []:
            if isinstance(structure, dict):
                structures.append(structure)
    return micro_grids, structures


def fold_page_regions_from_legacy_document(
    document: dict[str, Any],
    page: int,
) -> list[PageRegion]:
    micro_grids, structures = collect_legacy_sources(document, page)
    ocr_ref = _ocr_ref_for_page(document, page)
    regions = build_page_regions_for_page(
        page,
        micro_grids=micro_grids,
        local_structure_evidence=[{"page": page, "structures": structures}] if structures else [],
        ocr_evidence_ref=ocr_ref,
    )
    if regions:
        return regions
    out: list[PageRegion] = []
    seen: set[str] = set()
    for grid in micro_grids:
        region = region_from_micro_grid(grid, ocr_evidence_ref=ocr_ref)
        if region and region.region_id not in seen:
            seen.add(region.region_id)
            out.append(region)
    for structure in structures:
        region = region_from_local_structure(structure, ocr_evidence_ref=ocr_ref)
        if region and region.region_id not in seen:
            seen.add(region.region_id)
            out.append(region)
    out.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
    return out


def enrich_api_page_with_canvas(
    api_page: dict[str, Any],
    regions: list[PageRegion],
    *,
    mirror_level: str = "standard",
    ocr_evidence_ref: str | None = None,
    flow: PageFlow | None = None,
    reading_order: list[str] | None = None,
    blocks: list[Any] | None = None,
    morphology_summary: dict[str, int] | None = None,
    reading_order_v1: list[str] | None = None,
    document_type: str | None = None,
) -> dict[str, Any]:
    forensic = mirror_level == "forensic"
    page = dict(api_page)
    original_texts = list(page.get("texts") or [])
    original_kvs = list(page.get("key_values") or [])
    if flow is not None:
        flow_dict = flow.to_dict()
        if forensic:
            for idx, text in enumerate(flow_dict.get("texts") or []):
                if idx < len(original_texts) and original_texts[idx].get("evidence_ids"):
                    text["evidence_ids"] = list(original_texts[idx]["evidence_ids"])
                if idx < len(original_texts) and original_texts[idx].get("slm_entities"):
                    text["slm_entities"] = original_texts[idx]["slm_entities"]
            for idx, kv in enumerate(flow_dict.get("key_values") or []):
                if idx < len(original_kvs) and original_kvs[idx].get("evidence_ids"):
                    kv["evidence_ids"] = list(original_kvs[idx]["evidence_ids"])
        page["flow"] = flow_dict
    else:
        texts = list(original_texts)
        key_values = list(original_kvs)
        texts = filter_flow_texts_not_in_regions(texts, regions)
        page["flow"] = {"texts": texts, "key_values": key_values}
    page.pop("texts", None)
    page.pop("key_values", None)
    page["coordinate_system"] = "pdf_points_top_left"
    if ocr_evidence_ref:
        page["ocr_evidence_ref"] = ocr_evidence_ref
    flow_dict = page.get("flow") or {}
    flow_texts = (flow.texts if flow is not None else flow_dict.get("texts")) or []
    flow_kvs = (flow.key_values if flow is not None else flow_dict.get("key_values")) or []
    tables = list(page.get("tables") or [])
    region_dicts: list[dict[str, Any]] = []
    for region in regions:
        rd = region.to_dict()
        rd["structure"] = compact_region_structure(rd, forensic=forensic)
        region_dicts.append(rd)
    page["regions"] = region_dicts
    page_num = int(page.get("page_number") or 0)
    if pcm_blocks_enabled():
        if blocks is None:
            built_blocks, built_summary, built_order = build_page_blocks(
                page_num,
                regions=regions,
                flow_texts=list(flow_texts),
                flow_key_values=list(flow_kvs),
                tables=tables,
                document_type=document_type,
            )
            page["blocks"] = [b.to_dict() for b in built_blocks]
            page["morphology_summary"] = built_summary
            page["reading_order"] = list(reading_order or built_order)
            from docmirror.structure.ocr.page_canvas.block_index import reading_order_v1_from_blocks

            page["reading_order_v1"] = list(reading_order_v1 or reading_order_v1_from_blocks(built_blocks))
        else:
            page["blocks"] = [b.to_dict() if hasattr(b, "to_dict") else b for b in blocks]
            if morphology_summary is not None:
                page["morphology_summary"] = dict(morphology_summary)
            if reading_order is not None:
                page["reading_order"] = list(reading_order)
            if reading_order_v1 is not None:
                page["reading_order_v1"] = list(reading_order_v1)
    elif reading_order is not None:
        page["reading_order"] = list(reading_order)
    else:
        page["reading_order"] = reading_order_for_page(regions, list(flow_texts))
    return page


def fold_legacy_mirror_document(document: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of document with pages[].regions populated from legacy fields."""
    doc = dict(document)
    pages = [dict(p) for p in (doc.get("pages") or []) if isinstance(p, dict)]
    page_numbers = {int(p.get("page_number") or 0) for p in pages}
    for grid in doc.get("micro_grids") or []:
        if isinstance(grid, dict) and grid.get("page"):
            page_numbers.add(int(grid["page"]))
    for evidence in doc.get("scanned_local_structure_evidence") or []:
        if isinstance(evidence, dict) and evidence.get("page"):
            page_numbers.add(int(evidence["page"]))
    enriched: list[dict[str, Any]] = []
    by_num = {int(p.get("page_number") or 0): p for p in pages}
    for page_num in sorted(n for n in page_numbers if n > 0):
        api_page = by_num.get(page_num, {"page_number": page_num})
        regions = fold_page_regions_from_legacy_document(doc, page_num)
        enriched.append(
            enrich_api_page_with_canvas(
                api_page,
                regions,
                mirror_level="forensic",
                ocr_evidence_ref=_ocr_ref_for_page(doc, page_num),
            )
        )
    doc["pages"] = enriched
    return doc
