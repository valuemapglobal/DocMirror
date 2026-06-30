# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""vNext Mirror JSON access helpers.

These helpers are the read-side contract for page-local vNext structures.  They
hide the concrete JSON nesting used by ``_mirror.json`` and give plugins,
quality gates, and evaluators a stable vNext page projection access layer.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


def pages(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return vNext page dictionaries."""
    items = document.get("pages")
    return items if isinstance(items, list) else []


def get_page(document: dict[str, Any], page: int) -> dict[str, Any] | None:
    """Return the page dictionary for a 1-based page number."""
    for item in pages(document):
        if isinstance(item, dict) and int(item.get("page_number") or 0) == page:
            return item
    return None


def iter_regions(
    document: dict[str, Any],
    page: int | None = None,
    *,
    kind: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield vNext regions, optionally restricted by page and kind."""
    page_items = [get_page(document, page)] if page is not None else pages(document)
    for page_item in page_items:
        if not isinstance(page_item, dict):
            continue
        for region in page_item.get("regions") or []:
            if not isinstance(region, dict):
                continue
            if kind is not None and region.get("kind") != kind:
                continue
            yield region


def iter_blocks(
    document: dict[str, Any],
    page: int | None = None,
    *,
    role: str | None = None,
    block_type: str | None = None,
    morphology: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield vNext blocks, optionally restricted by page and block metadata."""
    page_items = [get_page(document, page)] if page is not None else pages(document)
    for page_item in page_items:
        if not isinstance(page_item, dict):
            continue
        for block in page_item.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            if role is not None and block.get("role") != role:
                continue
            if block_type is not None and block.get("type") != block_type:
                continue
            if morphology is not None and block.get("morphology") != morphology:
                continue
            yield block


def iter_structures(
    document: dict[str, Any],
    page: int | None = None,
    *,
    kind: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield region structure payloads from vNext regions."""
    for region in iter_regions(document, page, kind=kind):
        structure = region.get("structure")
        if isinstance(structure, dict):
            yield structure


def iter_flow_texts(document: dict[str, Any], page: int) -> Iterator[dict[str, Any]]:
    """Yield page flow texts from the vNext page shape."""
    page_item = get_page(document, page)
    if not isinstance(page_item, dict):
        return
    flow = page_item.get("flow")
    if isinstance(flow, dict):
        for text in flow.get("texts") or []:
            if isinstance(text, dict):
                yield text


def iter_evidence(
    document: dict[str, Any],
    page: int | None = None,
    *,
    kind: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield evidence atoms from common vNext evidence containers."""
    evidence = document.get("evidence")
    containers: list[Any] = []
    if isinstance(evidence, dict):
        for key in ("atoms", "items", "records"):
            value = evidence.get(key)
            if isinstance(value, list):
                containers.extend(value)
        pages_value = evidence.get("pages")
        if isinstance(pages_value, list):
            for page_value in pages_value:
                if isinstance(page_value, dict):
                    containers.extend(page_value.get("atoms") or [])
    elif isinstance(evidence, list):
        containers.extend(evidence)

    for item in containers:
        if not isinstance(item, dict):
            continue
        if page is not None and int(item.get("page") or item.get("page_number") or 0) != page:
            continue
        if kind is not None and item.get("kind") != kind and item.get("type") != kind:
            continue
        yield item


def find_region_by_id(document: dict[str, Any], region_id: str) -> tuple[int, dict[str, Any]] | None:
    """Find a region and return ``(page_number, region)``."""
    for page_item in pages(document):
        if not isinstance(page_item, dict):
            continue
        page_num = int(page_item.get("page_number") or 0)
        for region in page_item.get("regions") or []:
            if isinstance(region, dict) and str(region.get("region_id") or region.get("id")) == region_id:
                return page_num, region
    return None


def resolve_ref(document: dict[str, Any], page: int, ref: str) -> Any | None:
    """Resolve a vNext block/data reference within a page."""
    if not ref:
        return None
    page_item = get_page(document, page)
    if not isinstance(page_item, dict):
        return None
    if ref.startswith("region:"):
        region_id = ref.split(":", 1)[1]
        for region in page_item.get("regions") or []:
            if isinstance(region, dict) and str(region.get("region_id") or region.get("id")) == region_id:
                return region
        return None
    if ref.startswith("block:"):
        block_id = ref.split(":", 1)[1]
        for block in page_item.get("blocks") or []:
            if isinstance(block, dict) and str(block.get("block_id") or block.get("id")) == block_id:
                return block
        return None
    if ref.startswith("text:"):
        return _resolve_flow_index(page_item, "texts", ref)
    if ref.startswith("kv:"):
        return _resolve_flow_index(page_item, "key_values", ref)
    if ref.startswith("table:"):
        table_id = ref.split(":", 1)[1]
        for table in page_item.get("tables") or []:
            if isinstance(table, dict) and str(table.get("table_id") or table.get("id")) == table_id:
                return table
        return None
    if ref.startswith("evidence:"):
        evidence_id = ref.split(":", 1)[1]
        for item in iter_evidence(document, page):
            if str(item.get("id") or item.get("evidence_id")) == evidence_id:
                return item
    return None


def _resolve_flow_index(page_item: dict[str, Any], key: str, ref: str) -> Any | None:
    try:
        idx = int(ref.split(":", 1)[1])
    except (IndexError, ValueError):
        return None
    flow = page_item.get("flow") or {}
    values = flow.get(key) if isinstance(flow, dict) else None
    if not isinstance(values, list):
        return None
    return values[idx] if 0 <= idx < len(values) else None
