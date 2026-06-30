# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""vNext page query helpers."""

from __future__ import annotations

from collections.abc import Iterator
from enum import Enum
from typing import Any

from docmirror.models.mirror.vnext_access import (
    find_region_by_id as vnext_find_region_by_id,
)
from docmirror.models.mirror.vnext_access import (
    get_page as vnext_get_page,
)
from docmirror.models.mirror.vnext_access import (
    iter_blocks as vnext_iter_blocks,
)
from docmirror.models.mirror.vnext_access import (
    iter_flow_texts as vnext_iter_flow_texts,
)
from docmirror.models.mirror.vnext_access import (
    iter_regions as vnext_iter_regions,
)
from docmirror.models.mirror.vnext_access import (
    iter_structures as vnext_iter_structures,
)
from docmirror.models.mirror.vnext_access import (
    pages as vnext_pages,
)
from docmirror.models.mirror.vnext_access import (
    resolve_ref as vnext_resolve_ref,
)


def _document_pages(document: dict[str, Any]) -> list[dict[str, Any]]:
    return vnext_pages(document)


def get_page_projection(document: dict[str, Any], page: int) -> dict[str, Any] | None:
    """Return a vNext page projection by 1-based page number."""
    return vnext_get_page(document, page)


def iter_page_regions(
    document: dict[str, Any],
    page: int,
    *,
    kind: str | None = None,
) -> Iterator[dict[str, Any]]:
    yield from vnext_iter_regions(document, page, kind=kind)


def iter_all_regions(document: dict[str, Any], *, kind: str | None = None) -> Iterator[dict[str, Any]]:
    yield from vnext_iter_regions(document, kind=kind)


def find_region_by_id(document: dict[str, Any], region_id: str) -> tuple[int, dict[str, Any]] | None:
    return vnext_find_region_by_id(document, region_id)


def region_structure(document: dict[str, Any], region_id: str) -> dict[str, Any] | None:
    found = find_region_by_id(document, region_id)
    if found is None:
        return None
    _page, region = found
    structure = region.get("structure")
    return structure if isinstance(structure, dict) else None


def micro_grid_structures_from_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return micro-grid structures from vNext page regions."""
    grids: list[dict[str, Any]] = []
    for region in iter_all_regions(document, kind="micro_grid"):
        structure = region.get("structure")
        if isinstance(structure, dict):
            grids.append(structure)
    return grids


def field_grid_structures_from_document(document: dict[str, Any], *, page: int | None = None) -> list[dict[str, Any]]:
    structures = [
        *vnext_iter_structures(document, page, kind="field_grid"),
        *vnext_iter_structures(document, page, kind="label_value_graph"),
    ]
    return structures


def page_flow_texts(document: dict[str, Any], page: int) -> list[dict[str, Any]]:
    flow_texts = list(vnext_iter_flow_texts(document, page))
    if flow_texts:
        return flow_texts
    return []


def iter_page_blocks(
    document: dict[str, Any],
    page: int,
    *,
    morphology: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield UBI blocks for a page (Design 20)."""
    yield from vnext_iter_blocks(document, page, morphology=morphology)


def iter_all_blocks(document: dict[str, Any], *, morphology: str | None = None) -> Iterator[dict[str, Any]]:
    yield from vnext_iter_blocks(document, morphology=morphology)


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
    if not isinstance(block, dict):
        return None
    ref = str(block.get("ref") or "")
    return vnext_resolve_ref(document, page, ref)


def block_structure(document: dict[str, Any], page: int, block: dict[str, Any]) -> dict[str, Any] | None:
    resolved = resolve_block(document, page, block)
    if not isinstance(resolved, dict):
        return None
    ref = str(block.get("ref") or "")
    if ref.startswith("region:"):
        structure = resolved.get("structure")
        return structure if isinstance(structure, dict) else None
    return None


class PageStatus(Enum):
    """Page-level processing status for partial-result tracking."""

    success = "success"
    partial = "partial"
    failure = "failure"
    skipped = "skipped"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_exception(cls, exception: BaseException | None, *, skipped: bool = False) -> PageStatus:
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
