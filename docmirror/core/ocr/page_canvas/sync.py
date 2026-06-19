# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Materialize in-memory PageCanvas on ParseResult pages (PCM runtime SSOT)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from docmirror.core.ocr.page_canvas.block_index import build_page_blocks, pcm_blocks_enabled, pcm_mo_enabled
from docmirror.core.ocr.page_canvas.build import build_regions_from_domain_specific
from docmirror.core.ocr.page_canvas.flow_filter import filter_flow_texts_not_in_regions
from docmirror.core.ocr.page_canvas.models import PageCanvas, PageFlow, PageRegion
from docmirror.core.ocr.page_canvas.morphology_orchestrator import (
    merge_orchestrator_audit_into_bundle,
    orchestrate_page_morphology,
)
from docmirror.models.mirror.page_canvas_export import ocr_refs_by_page_from_pool

if TYPE_CHECKING:
    from docmirror.models.entities.parse_result import PageContent, ParseResult


def _flow_texts_from_page(page: PageContent) -> list[dict[str, Any]]:
    texts: list[dict[str, Any]] = []
    for text in page.texts:
        item: dict[str, Any] = {
            "content": text.content,
            "level": text.level.value,
            "confidence": text.confidence,
        }
        if text.bbox:
            item["bbox"] = list(text.bbox)
        if text.evidence_ids:
            item["evidence_ids"] = list(text.evidence_ids)
        if getattr(text, "slm_entities", None):
            item["slm_entities"] = text.slm_entities
        texts.append(item)
    return texts


def _flow_key_values_from_page(page: PageContent) -> list[dict[str, Any]]:
    return [
        {
            "key": kv.key,
            "value": kv.value,
            "confidence": kv.confidence,
            **({"bbox": list(kv.bbox)} if kv.bbox else {}),
            **({"evidence_ids": list(kv.evidence_ids)} if kv.evidence_ids else {}),
        }
        for kv in page.key_values
    ]


def _tables_from_page(page: PageContent) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for table in page.tables:
        item: dict[str, Any] = {
            "table_id": table.table_id,
            "page": table.page,
            "row_count": table.row_count,
            "headers": list(table.headers),
        }
        if table.bbox:
            item["bbox"] = list(table.bbox)
        if table.page_span is not None:
            item["page_span"] = table.page_span
        tables.append(item)
    return tables


def build_page_canvas_for_page(
    page: PageContent,
    regions: list[PageRegion],
    *,
    ocr_evidence_ref: str | None = None,
    document_type: str | None = None,
    content_type: str | None = None,
    evidence_bundle: dict[str, Any] | None = None,
) -> PageCanvas:
    """Build a PageCanvas dataclass from page content and resolved regions."""
    texts = filter_flow_texts_not_in_regions(_flow_texts_from_page(page), regions)
    key_values = _flow_key_values_from_page(page)
    tables = _tables_from_page(page)
    width = float(page.width) if page.width is not None else None
    height = float(page.height) if page.height is not None else None
    blocks = []
    morphology_summary: dict[str, int] = {}
    reading_order: list[str] = []
    reading_order_v1: list[str] = []
    flow = PageFlow(texts=texts, key_values=key_values)

    if pcm_blocks_enabled():
        if pcm_mo_enabled():
            mo = orchestrate_page_morphology(
                int(page.page_number or 0),
                regions=regions,
                flow_texts=texts,
                flow_key_values=key_values,
                tables=tables,
                evidence_bundle=evidence_bundle,
                content_type=content_type,
                document_type=document_type,
            )
            regions = mo.regions
            blocks = mo.blocks
            morphology_summary = mo.morphology_summary
            reading_order = mo.reading_order
            reading_order_v1 = mo.reading_order_v1
            flow = mo.flow or flow
            if evidence_bundle and mo.audit:
                merge_orchestrator_audit_into_bundle(evidence_bundle, mo.audit)
        else:
            blocks, morphology_summary, reading_order = build_page_blocks(
                int(page.page_number or 0),
                regions=regions,
                flow_texts=texts,
                flow_key_values=key_values,
                tables=tables,
                document_type=document_type,
            )
            from docmirror.core.ocr.page_canvas.block_index import reading_order_v1_from_blocks

            reading_order_v1 = reading_order_v1_from_blocks(blocks)

    return PageCanvas(
        page_number=page.page_number,
        width=width,
        height=height,
        flow=flow,
        tables=tables,
        regions=list(regions),
        blocks=blocks,
        morphology_summary=morphology_summary,
        ocr_evidence_ref=ocr_evidence_ref,
        reading_order=reading_order,
        reading_order_v1=reading_order_v1,
    )


def sync_parse_result_page_canvases(
    parse_result: ParseResult,
    *,
    scanned_ocr_pages: list[dict[str, Any]] | None = None,
) -> None:
    """Attach PageCanvas to each PageContent from domain_specific evidence."""
    domain_specific = parse_result.entities.domain_specific
    refs = ocr_refs_by_page_from_pool(scanned_ocr_pages)
    regions_by_page = build_regions_from_domain_specific(domain_specific, ocr_refs_by_page=refs)
    seen: set[int] = set()
    doc_type = None
    content_type = None
    entities = getattr(parse_result, "entities", None)
    if entities is not None:
        doc_type = getattr(entities, "document_type", None) or (
            (getattr(entities, "domain_specific", None) or {}).get("document_type")
            if isinstance(getattr(entities, "domain_specific", None), dict)
            else None
        )
        content_type = getattr(entities, "content_type", None)
    ds = domain_specific or {}
    bundles_by_page = {
        int(b.get("page") or 0): b
        for b in (ds.get("_page_evidence_bundles") or [])
        if isinstance(b, dict) and int(b.get("page") or 0) > 0
    }
    for page in parse_result.pages:
        page_num = int(page.page_number or 0)
        if page_num <= 0 or page_num in seen:
            continue
        seen.add(page_num)
        regions = regions_by_page.get(page_num, [])
        page.page_canvas = build_page_canvas_for_page(
            page,
            regions,
            ocr_evidence_ref=refs.get(page_num),
            document_type=str(doc_type) if doc_type else None,
            content_type=str(content_type) if content_type else None,
            evidence_bundle=bundles_by_page.get(page_num),
        )
