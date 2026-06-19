# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Universal Block Index (UBI) — derive navigation-plane blocks from PCM data slots."""

from __future__ import annotations

import os
from typing import Any

from docmirror.core.ocr.page_canvas.models import PageBlock, PageRegion

MORPHOLOGY_S1 = "S1"
MORPHOLOGY_S2 = "S2"
MORPHOLOGY_S3 = "S3"
MORPHOLOGY_S4 = "S4"
MORPHOLOGY_S5 = "S5"

SCHEMA_CORE_PHYSICAL_TABLE_LEDGER = "core.physical_table.ledger"
SCHEMA_CORE_KEY_VALUE = "core.key_value.header"


def pcm_blocks_enabled() -> bool:
    """Whether to materialize ``pages[n].blocks`` (Design 20 Phase 0)."""
    val = os.environ.get("DOCMIRROR_PCM_BLOCKS", "1")
    return val not in ("0", "false", "False", "")


def pcm_mo_enabled() -> bool:
    """Whether Morphology Orchestrator gate is active (Design 20 Phase 1)."""
    val = os.environ.get("DOCMIRROR_PCM_MO", "1")
    return val not in ("0", "false", "False", "")


def _bbox_from_dict(item: dict[str, Any]) -> list[float]:
    bbox = item.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        return [float(v) for v in bbox]
    return []


def _anchor_from_table(table: dict[str, Any]) -> str:
    headers = table.get("headers") or []
    if headers:
        return "|".join(str(h) for h in headers if h)
    return str(table.get("table_id") or "")


def _schema_hint_for_region(region: PageRegion, *, document_type: str | None = None) -> str:
    hint = getattr(region, "schema_hint", None) or ""
    if hint:
        return str(hint)
    structure = region.structure if isinstance(region.structure, dict) else {}
    try:
        from docmirror.core.ocr.structure_project import infer_schema_hint_v2

        inferred = infer_schema_hint_v2(structure, document_type=document_type, region_kind=region.kind)
        if inferred:
            return inferred
    except Exception:
        pass
    if region.morphology == MORPHOLOGY_S3:
        return "core.micro_grid.matrix"
    if region.morphology == MORPHOLOGY_S4:
        return "core.field_grid.kv_block"
    return ""


def block_from_region(
    region: PageRegion,
    *,
    page_number: int,
    seq: int,
    document_type: str | None = None,
) -> PageBlock:
    return PageBlock(
        block_id=f"blk_p{page_number}_r{seq}",
        morphology=region.morphology,
        kind=region.kind,
        ref=f"region:{region.region_id}",
        bbox=list(region.bbox),
        anchor_text=region.anchor_text,
        schema_hint=_schema_hint_for_region(region, document_type=document_type),
        confidence=region.confidence,
        audit={"source": "region"},
    )


def blocks_from_flow_texts(
    flow_texts: list[dict[str, Any]],
    *,
    page_number: int,
) -> list[PageBlock]:
    blocks: list[PageBlock] = []
    for idx, text in enumerate(flow_texts):
        if not isinstance(text, dict):
            continue
        content = str(text.get("content") or "").strip()
        blocks.append(
            PageBlock(
                block_id=f"blk_p{page_number}_t{idx}",
                morphology=MORPHOLOGY_S1,
                kind="text_flow",
                ref=f"text:{idx}",
                bbox=_bbox_from_dict(text),
                anchor_text=content[:80] if content else "",
                confidence=float(text.get("confidence") or 0.0),
                audit={"source": "flow.texts"},
            )
        )
    return blocks


def blocks_from_flow_key_values(
    flow_key_values: list[dict[str, Any]],
    *,
    page_number: int,
) -> list[PageBlock]:
    blocks: list[PageBlock] = []
    for idx, kv in enumerate(flow_key_values):
        if not isinstance(kv, dict):
            continue
        key = str(kv.get("key") or "").strip()
        blocks.append(
            PageBlock(
                block_id=f"blk_p{page_number}_kv{idx}",
                morphology=MORPHOLOGY_S5,
                kind="key_value",
                ref=f"kv:{idx}",
                bbox=_bbox_from_dict(kv),
                anchor_text=key,
                schema_hint=SCHEMA_CORE_KEY_VALUE,
                confidence=float(kv.get("confidence") or 0.0),
                audit={"source": "flow.key_values"},
            )
        )
    return blocks


def blocks_from_tables(
    tables: list[dict[str, Any]],
    *,
    page_number: int,
) -> list[PageBlock]:
    blocks: list[PageBlock] = []
    for idx, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        table_id = str(table.get("table_id") or f"pt_{page_number}_{idx}")
        blocks.append(
            PageBlock(
                block_id=f"blk_p{page_number}_tbl{idx}",
                morphology=MORPHOLOGY_S2,
                kind="physical_table",
                ref=f"table:{table_id}",
                bbox=_bbox_from_dict(table),
                anchor_text=_anchor_from_table(table),
                schema_hint=SCHEMA_CORE_PHYSICAL_TABLE_LEDGER,
                confidence=float(table.get("confidence") or 1.0),
                audit={"source": "tables", "table_id": table_id},
            )
        )
    return blocks


def morphology_summary_from_blocks(blocks: list[PageBlock]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for block in blocks:
        morph = str(block.morphology or "")
        if morph:
            summary[morph] = summary.get(morph, 0) + 1
    return summary


def _block_sort_key(block: PageBlock) -> tuple[float, float, str]:
    bbox = block.bbox
    if bbox and len(bbox) == 4:
        return (float(bbox[1]), float(bbox[0]), block.block_id)
    return (1_000_000.0, 0.0, block.block_id)


def reading_order_from_blocks(blocks: list[PageBlock]) -> list[str]:
    """Return block_id list sorted by top-left bbox (Design 20 reading_order v2)."""
    ordered = sorted(blocks, key=_block_sort_key)
    return [block.block_id for block in ordered]


def reading_order_v1_from_blocks(blocks: list[PageBlock]) -> list[str]:
    """Legacy reading_order refs (region_id + text:{index}) for compat shim."""
    ordered = sorted(blocks, key=_block_sort_key)
    refs: list[str] = []
    for block in ordered:
        ref = block.ref
        if ref.startswith("region:"):
            refs.append(ref.split(":", 1)[1])
        elif ref.startswith("text:"):
            refs.append(ref)
        elif ref.startswith("table:"):
            refs.append(ref)
        elif ref.startswith("kv:"):
            refs.append(ref)
    return refs


def build_page_blocks(
    page_number: int,
    *,
    regions: list[PageRegion],
    flow_texts: list[dict[str, Any]] | None = None,
    flow_key_values: list[dict[str, Any]] | None = None,
    tables: list[dict[str, Any]] | None = None,
    document_type: str | None = None,
) -> tuple[list[PageBlock], dict[str, int], list[str]]:
    """Derive UBI blocks + morphology summary + reading_order from PCM slots."""
    blocks: list[PageBlock] = []
    for seq, region in enumerate(regions):
        blocks.append(block_from_region(region, page_number=page_number, seq=seq, document_type=document_type))
    blocks.extend(blocks_from_flow_texts(flow_texts or [], page_number=page_number))
    blocks.extend(blocks_from_flow_key_values(flow_key_values or [], page_number=page_number))
    blocks.extend(blocks_from_tables(tables or [], page_number=page_number))
    summary = morphology_summary_from_blocks(blocks)
    reading_order = reading_order_from_blocks(blocks)
    return blocks, summary, reading_order


def document_morphology_stats(pages: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate morphology counts across all pages (Design 20 §3.3)."""
    stats: dict[str, int] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        summary = page.get("morphology_summary")
        if isinstance(summary, dict):
            for morph, count in summary.items():
                stats[str(morph)] = stats.get(str(morph), 0) + int(count or 0)
            continue
        for block in page.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            morph = str(block.get("morphology") or "")
            if morph:
                stats[morph] = stats.get(morph, 0) + 1
    return stats
