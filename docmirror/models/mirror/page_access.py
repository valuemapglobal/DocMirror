# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PCM query helpers — SSOT for page-local structure access."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from docmirror.models.mirror.legacy_access import record_legacy_mirror_access


def _document_pages(document: dict[str, Any]) -> list[dict[str, Any]]:
    pages = document.get("pages")
    return pages if isinstance(pages, list) else []


def get_page_canvas(document: dict[str, Any], page: int) -> dict[str, Any] | None:
    for api_page in _document_pages(document):
        if int(api_page.get("page_number") or 0) == page:
            return api_page
    return None


def iter_page_regions(
    document: dict[str, Any],
    page: int,
    *,
    kind: str | None = None,
) -> Iterator[dict[str, Any]]:
    api_page = get_page_canvas(document, page)
    if not api_page:
        return
    for region in api_page.get("regions") or []:
        if not isinstance(region, dict):
            continue
        if kind is not None and region.get("kind") != kind:
            continue
        yield region


def iter_all_regions(document: dict[str, Any], *, kind: str | None = None) -> Iterator[dict[str, Any]]:
    for api_page in _document_pages(document):
        page_num = int(api_page.get("page_number") or 0)
        yield from iter_page_regions(document, page_num, kind=kind)


def find_region_by_id(document: dict[str, Any], region_id: str) -> tuple[int, dict[str, Any]] | None:
    for api_page in _document_pages(document):
        page_num = int(api_page.get("page_number") or 0)
        for region in api_page.get("regions") or []:
            if isinstance(region, dict) and str(region.get("region_id")) == region_id:
                return page_num, region
    return None


def region_structure(document: dict[str, Any], region_id: str) -> dict[str, Any] | None:
    found = find_region_by_id(document, region_id)
    if found is None:
        return None
    _page, region = found
    structure = region.get("structure")
    return structure if isinstance(structure, dict) else None


def micro_grids_from_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer page regions; fall back to legacy document.micro_grids."""
    grids: list[dict[str, Any]] = []
    for region in iter_all_regions(document, kind="micro_grid"):
        structure = region.get("structure")
        if isinstance(structure, dict):
            grids.append(structure)
    if grids:
        return grids
    legacy = document.get("micro_grids")
    if legacy:
        record_legacy_mirror_access("document.micro_grids")
    return list(legacy) if isinstance(legacy, list) else []


def field_grid_structures_from_document(document: dict[str, Any], *, page: int | None = None) -> list[dict[str, Any]]:
    structures: list[dict[str, Any]] = []
    pages = _document_pages(document)
    for api_page in pages:
        page_num = int(api_page.get("page_number") or 0)
        if page is not None and page_num != page:
            continue
        for region in api_page.get("regions") or []:
            if not isinstance(region, dict):
                continue
            if region.get("kind") not in {"field_grid", "label_value_graph"}:
                continue
            structure = region.get("structure")
            if isinstance(structure, dict):
                structures.append(structure)
    if structures:
        return structures
    for evidence in document.get("scanned_local_structure_evidence") or []:
        if not isinstance(evidence, dict):
            continue
        if page is not None and int(evidence.get("page") or 0) != page:
            continue
        record_legacy_mirror_access("document.scanned_local_structure_evidence")
        for structure in evidence.get("structures") or []:
            if isinstance(structure, dict):
                structures.append(structure)
    return structures


def page_flow_texts(document: dict[str, Any], page: int) -> list[dict[str, Any]]:
    api_page = get_page_canvas(document, page)
    if not api_page:
        return []
    flow = api_page.get("flow")
    if isinstance(flow, dict) and flow.get("texts"):
        return list(flow.get("texts") or [])
    texts = api_page.get("texts")
    if texts:
        record_legacy_mirror_access("pages[].texts")
    return list(texts or [])


def iter_page_blocks(
    document: dict[str, Any],
    page: int,
    *,
    morphology: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield UBI blocks for a page (Design 20)."""
    api_page = get_page_canvas(document, page)
    if not api_page:
        return
    for block in api_page.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if morphology is not None and block.get("morphology") != morphology:
            continue
        yield block


def iter_all_blocks(document: dict[str, Any], *, morphology: str | None = None) -> Iterator[dict[str, Any]]:
    for api_page in _document_pages(document):
        page_num = int(api_page.get("page_number") or 0)
        yield from iter_page_blocks(document, page_num, morphology=morphology)


def resolve_block_ref(api_page: dict[str, Any], ref: str) -> Any | None:
    """Resolve a block ref to its data-plane SSOT payload."""
    if not ref or not isinstance(api_page, dict):
        return None
    if ref.startswith("region:"):
        region_id = ref.split(":", 1)[1]
        for region in api_page.get("regions") or []:
            if isinstance(region, dict) and str(region.get("region_id")) == region_id:
                return region
        return None
    if ref.startswith("text:"):
        try:
            idx = int(ref.split(":", 1)[1])
        except (IndexError, ValueError):
            return None
        flow = api_page.get("flow") or {}
        texts = flow.get("texts") or []
        return texts[idx] if 0 <= idx < len(texts) else None
    if ref.startswith("kv:"):
        try:
            idx = int(ref.split(":", 1)[1])
        except (IndexError, ValueError):
            return None
        flow = api_page.get("flow") or {}
        kvs = flow.get("key_values") or []
        return kvs[idx] if 0 <= idx < len(kvs) else None
    if ref.startswith("table:"):
        table_id = ref.split(":", 1)[1]
        for table in api_page.get("tables") or []:
            if isinstance(table, dict) and str(table.get("table_id")) == table_id:
                return table
        return None
    return None


def resolve_block(document: dict[str, Any], page: int, block: dict[str, Any]) -> Any | None:
    api_page = get_page_canvas(document, page)
    if not api_page or not isinstance(block, dict):
        return None
    ref = str(block.get("ref") or "")
    return resolve_block_ref(api_page, ref)


def block_structure(document: dict[str, Any], page: int, block: dict[str, Any]) -> dict[str, Any] | None:
    resolved = resolve_block(document, page, block)
    if not isinstance(resolved, dict):
        return None
    ref = str(block.get("ref") or "")
    if ref.startswith("region:"):
        structure = resolved.get("structure")
        return structure if isinstance(structure, dict) else None
    return None

from enum import Enum
from typing import Any


class PageStatus(Enum):
    """Page-level processing status for partial-result tracking."""

    success = "success"
    partial = "partial"
    failure = "failure"
    skipped = "skipped"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_exception(
        cls, exception: BaseException | None, *, skipped: bool = False
    ) -> PageStatus:
        """Determine PageStatus from an optional exception and skip flag."""
        if skipped:
            return cls.skipped
        if exception is None:
            return cls.success
        return cls.partial

    @property
    def is_ok(self) -> bool:
        """Whether this status allows the page to be counted as successful."""
        return self in (PageStatus.success, PageStatus.partial)

    @property
    def needs_review(self) -> bool:
        """Whether this page status requires human review."""
        return self in (PageStatus.partial, PageStatus.failure)
