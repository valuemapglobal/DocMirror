# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enrich API pages with PCM regions at serialize time."""

from __future__ import annotations

from typing import Any

from docmirror.core.ocr.page_canvas.build import build_regions_from_domain_specific
from docmirror.models.mirror.legacy_project import enrich_api_page_with_canvas


def ocr_refs_by_page_from_pool(
    scanned_ocr_pages: list[dict[str, Any]] | None,
) -> dict[int, str]:
    refs: dict[int, str] = {}
    for item in scanned_ocr_pages or []:
        if not isinstance(item, dict):
            continue
        page = int(item.get("page") or 0)
        ref = str(item.get("ocr_page_id") or "")
        if page and ref:
            refs[page] = ref
    return refs


def enrich_api_pages_with_page_canvas(
    api_pages: list[dict[str, Any]],
    *,
    domain_specific: dict[str, Any] | None,
    mirror_level: str,
    scanned_ocr_pages: list[dict[str, Any]] | None = None,
    source_pages: list[Any] | None = None,
) -> list[dict[str, Any]]:
    refs = ocr_refs_by_page_from_pool(scanned_ocr_pages)
    canvas_by_num: dict[int, Any] = {}
    if source_pages:
        for page in source_pages:
            canvas = getattr(page, "page_canvas", None)
            page_num = int(getattr(page, "page_number", 0) or 0)
            if canvas is not None and page_num > 0:
                canvas_by_num[page_num] = canvas
    regions_by_page = build_regions_from_domain_specific(domain_specific, ocr_refs_by_page=refs)
    by_num: dict[int, dict[str, Any]] = {
        int(p.get("page_number") or 0): p for p in api_pages if int(p.get("page_number") or 0) > 0
    }
    for page_num in set(regions_by_page) | set(canvas_by_num):
        if page_num not in by_num:
            by_num[page_num] = {"page_number": page_num}
    enriched: list[dict[str, Any]] = []
    for page_num in sorted(by_num):
        api_page = by_num[page_num]
        canvas = canvas_by_num.get(page_num)
        if canvas is not None:
            regions = list(canvas.regions)
            flow = canvas.flow
        else:
            regions = regions_by_page.get(page_num, [])
            flow = None
        enriched.append(
            enrich_api_page_with_canvas(
                api_page,
                regions,
                mirror_level=mirror_level,
                ocr_evidence_ref=refs.get(page_num) or getattr(canvas, "ocr_evidence_ref", None),
                flow=flow,
                reading_order=getattr(canvas, "reading_order", None) if canvas is not None else None,
                blocks=getattr(canvas, "blocks", None) if canvas is not None else None,
                morphology_summary=getattr(canvas, "morphology_summary", None) if canvas is not None else None,
                reading_order_v1=getattr(canvas, "reading_order_v1", None) if canvas is not None else None,
            )
        )
    return enriched


def attach_region_refs_to_sections(
    sections: list[Any],
    api_pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add region_refs and page_span to sections from page regions."""
    regions_by_page: dict[int, list[str]] = {}
    for page in api_pages:
        if not isinstance(page, dict):
            continue
        page_num = int(page.get("page_number") or 0)
        ids = [
            str(r.get("region_id"))
            for r in (page.get("regions") or [])
            if isinstance(r, dict) and r.get("region_id")
        ]
        if ids:
            regions_by_page[page_num] = ids
    out: list[dict[str, Any]] = []
    for sec in sections or []:
        if hasattr(sec, "model_dump"):
            item = sec.model_dump()
        elif isinstance(sec, dict):
            item = dict(sec)
        else:
            continue
        page_start = int(item.get("page_start") or 0)
        page_end = int(item.get("page_end") or page_start or 0)
        if page_end < page_start:
            page_end = page_start
        refs: list[str] = list(item.get("region_refs") or [])
        if page_start:
            for page_num in range(page_start, page_end + 1):
                for region_id in regions_by_page.get(page_num, []):
                    if region_id not in refs:
                        refs.append(region_id)
            if refs:
                item["region_refs"] = refs
            if not item.get("page_span"):
                item["page_span"] = [page_start, page_end]
        out.append(item)
    return out
