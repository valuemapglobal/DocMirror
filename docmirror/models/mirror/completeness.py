# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror Completeness Profile builder."""

from __future__ import annotations

from typing import Any


def _level(count: int, total: int) -> str:
    if total <= 0:
        return "missing"
    if count <= 0:
        return "missing"
    if count == total:
        return "full"
    return "partial"


def build_mirror_completeness(result: Any) -> dict[str, Any]:
    pages = list(getattr(result, "pages", []) or [])
    text_blocks = []
    tables = []
    cells = []
    page_with_geometry = 0
    for page in pages:
        text_blocks.extend(list(getattr(page, "texts", []) or []))
        page_tables = list(getattr(page, "tables", []) or [])
        tables.extend(page_tables)
        if getattr(page, "width", None) or getattr(page, "height", None) or getattr(page, "bbox", None):
            page_with_geometry += 1
        for table in page_tables:
            for row in list(getattr(table, "rows", []) or []) + list(getattr(table, "data_rows", []) or []):
                cells.extend(list(getattr(row, "cells", []) or []))

    text_present = bool((getattr(result, "full_text", "") or "").strip() or text_blocks)
    table_count = len(tables)
    bbox_items = 0
    token_items = 0
    source_ref_items = 0
    evidence_items = 0
    total_items = len(text_blocks) + len(cells)
    for item in [*text_blocks, *cells]:
        if getattr(item, "bbox", None) or getattr(item, "bbox_norm", None):
            bbox_items += 1
        if getattr(item, "token_ids", None):
            token_items += 1
        if getattr(item, "source_cell_refs", None):
            source_ref_items += 1
        if getattr(item, "evidence_ids", None):
            evidence_items += 1

    if token_items:
        bbox_level = "token" if bbox_items == total_items else "block"
    elif bbox_items:
        bbox_level = "block"
    elif page_with_geometry:
        bbox_level = "page"
    else:
        bbox_level = "none"

    quality = "basic"
    if getattr(result, "trust", None) is not None:
        quality = "full"
    elif getattr(result, "confidence", None) is not None:
        quality = "basic"

    limitations: list[str] = []
    transport = ""
    capability_id = ""
    if getattr(result, "provenance", None) is not None:
        transport = str(getattr(result.provenance, "file_type", "") or "")
        capability_id = str(getattr(result.provenance, "capability_id", "") or "")
    if bbox_level in {"none", "page"}:
        limitations.append("Token/block-level geometry is not complete for this parse result.")
    if _level(source_ref_items + evidence_items, max(total_items, 1)) != "full":
        limitations.append("Source reference coverage is partial.")

    return {
        "version": 1,
        "transport": transport,
        "capability_id": capability_id,
        "text": "full" if text_present else "missing",
        "blocks": _level(len(text_blocks) + table_count, max(len(pages), 1)),
        "tables": "full" if table_count else "missing",
        "bbox": bbox_level,
        "tokens": _level(token_items, max(total_items, 1)),
        "source_refs": _level(source_ref_items + evidence_items, max(total_items, 1)),
        "quality": quality,
        "forensic_ready": bbox_level in {"block", "token"} and (source_ref_items or evidence_items) > 0,
        "counts": {
            "pages": len(pages),
            "text_blocks": len(text_blocks),
            "tables": table_count,
            "cells": len(cells),
            "items_with_bbox": bbox_items,
            "items_with_source_refs": source_ref_items + evidence_items,
        },
        "limitations": limitations,
    }


def compact_mirror_completeness(profile: dict[str, Any]) -> dict[str, Any]:
    """Return the lightweight completeness contract suitable for standard Mirror meta."""
    keys = (
        "transport",
        "capability_id",
        "text",
        "blocks",
        "tables",
        "bbox",
        "tokens",
        "source_refs",
        "quality",
        "forensic_ready",
    )
    return {key: profile[key] for key in keys if key in profile and profile[key] not in ("", None)}
