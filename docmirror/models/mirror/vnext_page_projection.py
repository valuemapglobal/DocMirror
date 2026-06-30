# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""vNext-native page projection helpers."""

from __future__ import annotations

from typing import Any

from docmirror.models.mirror.domain_access import (
    micro_grid_structures_from_domain_specific,
    raw_local_structure_evidence_from_domain_specific,
)

_STANDARD_FIELD_CELL_KEYS = frozenset(
    {
        "cell_id",
        "row_index",
        "col_index",
        "label_text",
        "text",
        "bbox",
        "confidence",
        "geometry_status",
        "assignment_method",
        "assignment_confidence",
        "inferred_types",
    }
)
_STANDARD_MICRO_GRID_KEYS = frozenset(
    {
        "grid_id",
        "page",
        "bbox",
        "grid_type_hint",
        "anchor_text",
        "coordinate_system",
        "geometry_source",
        "confidence",
        "row_bands",
        "col_bands",
        "cells",
    }
)
_STANDARD_MICRO_GRID_CELL_KEYS = frozenset(
    {
        "row_index",
        "col_index",
        "bbox",
        "text",
        "confidence",
        "geometry_status",
        "geometry_loss_reason",
        "assignment_confidence",
        "assignment_method",
        "recognition_source",
        "role",
    }
)


def ocr_refs_by_page_from_pool(scanned_ocr_pages: list[dict[str, Any]] | None) -> dict[int, str]:
    refs: dict[int, str] = {}
    for item in scanned_ocr_pages or []:
        if not isinstance(item, dict):
            continue
        page = int(item.get("page") or 0)
        ref = str(item.get("ocr_page_id") or "")
        if page and ref:
            refs[page] = ref
    return refs


def project_vnext_pages(
    api_pages: list[dict[str, Any]],
    *,
    domain_specific: dict[str, Any] | None,
    mirror_level: str,
    scanned_ocr_pages: list[dict[str, Any]] | None = None,
    include_text: bool | None = None,
    document_type: str | None = None,
) -> list[dict[str, Any]]:
    """Project vNext pages into topology, regions, blocks, and flow."""
    refs = ocr_refs_by_page_from_pool(scanned_ocr_pages)
    regions_by_page = build_vnext_regions_from_domain_specific(domain_specific, ocr_refs_by_page=refs)
    by_num: dict[int, dict[str, Any]] = {
        int(p.get("page_number") or 0): p for p in api_pages if int(p.get("page_number") or 0) > 0
    }
    out: list[dict[str, Any]] = []
    for page_num in sorted(set(by_num) | set(regions_by_page)):
        page = dict(by_num.get(page_num) or {"page_number": page_num})
        regions = regions_by_page.get(page_num, [])
        if regions or page.get("texts") or page.get("key_values"):
            page = enrich_vnext_page_with_regions(
                page,
                regions,
                mirror_level=mirror_level,
                ocr_evidence_ref=refs.get(page_num),
                document_type=document_type,
            )
        elif include_text is False:
            page.pop("texts", None)
        out.append(page)
    return out


def enrich_api_pages_with_projection(
    api_pages: list[dict[str, Any]],
    *,
    domain_specific: dict[str, Any] | None,
    mirror_level: str,
    scanned_ocr_pages: list[dict[str, Any]] | None = None,
    source_pages: list[Any] | None = None,
) -> list[dict[str, Any]]:
    _ = source_pages
    return project_vnext_pages(
        api_pages,
        domain_specific=domain_specific,
        mirror_level=mirror_level,
        scanned_ocr_pages=scanned_ocr_pages,
    )


def build_vnext_regions_from_domain_specific(
    domain_specific: dict[str, Any] | None,
    *,
    ocr_refs_by_page: dict[int, str] | None = None,
) -> dict[int, list[dict[str, Any]]]:
    ds = domain_specific or {}
    refs = ocr_refs_by_page or {}
    regions: dict[int, list[dict[str, Any]]] = {}
    seen: dict[int, set[str]] = {}

    for grid in micro_grid_structures_from_domain_specific(ds):
        page = int(grid.get("page") or 0) if isinstance(grid, dict) else 0
        region = _region_from_micro_grid(grid, ocr_evidence_ref=refs.get(page))
        if page and region:
            _append_unique_region(regions, seen, page, region)

    for evidence in raw_local_structure_evidence_from_domain_specific(ds):
        if not isinstance(evidence, dict):
            continue
        page = int(evidence.get("page") or 0)
        ref = str(evidence.get("ocr_page_ref") or refs.get(page) or "") or None
        for structure in evidence.get("structures") or []:
            region = _region_from_local_structure(structure, ocr_evidence_ref=ref)
            if page and region:
                _append_unique_region(regions, seen, page, region)

    for bundle in ds.get("_page_evidence_bundles") or []:
        if isinstance(bundle, dict) and int(bundle.get("page") or 0) > 0:
            regions.setdefault(int(bundle["page"]), [])

    for page_regions in regions.values():
        page_regions.sort(key=lambda item: _bbox_sort_key(item.get("bbox")))
    return regions


def enrich_vnext_page_with_regions(
    api_page: dict[str, Any],
    regions: list[dict[str, Any]],
    *,
    mirror_level: str = "standard",
    ocr_evidence_ref: str | None = None,
    document_type: str | None = None,
) -> dict[str, Any]:
    forensic = mirror_level == "forensic"
    page = dict(api_page)
    original_texts = list(page.get("texts") or [])
    original_kvs = list(page.get("key_values") or [])
    flow_texts = _filter_flow_texts_not_in_regions(original_texts, regions)
    page["flow"] = {"texts": flow_texts, "key_values": original_kvs}
    page.pop("texts", None)
    page.pop("key_values", None)
    page["coordinate_system"] = "pdf_points_top_left"
    if ocr_evidence_ref:
        page["ocr_evidence_ref"] = ocr_evidence_ref
    page["regions"] = [_compact_region(region, forensic=forensic) for region in regions]

    page_num = int(page.get("page_number") or 0)
    blocks, summary, reading_order = _build_page_blocks(
        page_num,
        regions=page["regions"],
        flow_texts=flow_texts,
        flow_key_values=original_kvs,
        tables=list(page.get("tables") or []),
        document_type=document_type,
    )
    if blocks:
        page["blocks"] = blocks
        page["morphology_summary"] = summary
        page["reading_order"] = reading_order
        page["reading_order_refs"] = _reading_order_refs_from_blocks(blocks)
    else:
        page["reading_order"] = _reading_order_for_regions_and_texts(page["regions"], flow_texts)
    return page


def attach_region_refs_to_sections(sections: list[Any], api_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add region_refs and page_span to sections from page regions."""
    regions_by_page: dict[int, list[str]] = {}
    for page in api_pages:
        if not isinstance(page, dict):
            continue
        page_num = int(page.get("page_number") or 0)
        ids = [
            str(r.get("region_id")) for r in (page.get("regions") or []) if isinstance(r, dict) and r.get("region_id")
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


def document_morphology_stats(pages: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate vNext page morphology counts from summaries or blocks."""
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


def _append_unique_region(
    regions: dict[int, list[dict[str, Any]]],
    seen: dict[int, set[str]],
    page: int,
    region: dict[str, Any],
) -> None:
    region_id = str(region.get("region_id") or "")
    page_seen = seen.setdefault(page, set())
    if not region_id or region_id in page_seen:
        return
    page_seen.add(region_id)
    regions.setdefault(page, []).append(region)


def _region_id(source_id: str) -> str:
    if source_id.startswith(("mg_", "ls_")):
        return "rg_" + source_id[3:]
    return f"rg_{source_id}"


def _region_from_micro_grid(grid: Any, *, ocr_evidence_ref: str | None = None) -> dict[str, Any] | None:
    if not isinstance(grid, dict):
        return None
    grid_id = str(grid.get("grid_id") or "")
    bbox = _bbox(grid.get("bbox"))
    if not grid_id or not bbox:
        return None
    out = {
        "region_id": _region_id(grid_id),
        "kind": "micro_grid",
        "morphology": "S3",
        "bbox": bbox,
        "anchor_text": str(grid.get("anchor_text") or ""),
        "structure": dict(grid),
        "confidence": float(grid.get("confidence") or 0.0),
        "audit": {"source": "micro_grid", "grid_id": grid_id},
    }
    if ocr_evidence_ref:
        out["ocr_evidence_ref"] = ocr_evidence_ref
    return out


def _region_from_local_structure(structure: Any, *, ocr_evidence_ref: str | None = None) -> dict[str, Any] | None:
    if not isinstance(structure, dict):
        return None
    structure_id = str(structure.get("structure_id") or "")
    bbox = _bbox(structure.get("bbox"))
    if not structure_id or not bbox:
        return None
    structure_kind = str(structure.get("structure_kind") or "local_structure")
    kind = structure_kind if structure_kind in {"field_grid", "label_value_graph"} else structure_kind
    anchors = structure.get("anchors") or ()
    anchor_text = " ".join(str(a) for a in anchors if a)
    if not anchor_text:
        nodes = structure.get("nodes") or []
        anchor_text = " ".join(
            str(node.get("text") or "") for node in nodes if isinstance(node, dict) and node.get("role") == "anchor"
        )
    out = {
        "region_id": _region_id(structure_id),
        "kind": kind,
        "morphology": "S4",
        "bbox": bbox,
        "anchor_text": anchor_text.strip(),
        "structure": dict(structure),
        "confidence": float(structure.get("confidence") or 0.0),
        "audit": {"source": "local_structure", "structure_id": structure_id, "structure_kind": structure_kind},
    }
    if ocr_evidence_ref:
        out["ocr_evidence_ref"] = ocr_evidence_ref
    return out


def _compact_region(region: dict[str, Any], *, forensic: bool) -> dict[str, Any]:
    out = dict(region)
    out["structure"] = _compact_region_structure(out, forensic=forensic)
    return out


def _compact_region_structure(region: dict[str, Any], *, forensic: bool = False) -> dict[str, Any]:
    if forensic or not isinstance(region, dict):
        return region.get("structure", region) if isinstance(region, dict) else {}
    kind = region.get("kind")
    structure = region.get("structure")
    if not isinstance(structure, dict):
        return structure or {}
    if kind == "micro_grid":
        compact = {key: value for key, value in structure.items() if key in _STANDARD_MICRO_GRID_KEYS}
        rows: list[list[dict[str, Any]]] = []
        for row in structure.get("cells") or []:
            if not isinstance(row, list):
                continue
            rows.append(
                [
                    {key: value for key, value in cell.items() if key in _STANDARD_MICRO_GRID_CELL_KEYS}
                    for cell in row
                    if isinstance(cell, dict)
                ]
            )
        if rows:
            compact["cells"] = rows
        return compact
    if kind in {"field_grid", "label_value_graph"}:
        compact = {
            key: value
            for key, value in structure.items()
            if key
            in {
                "structure_id",
                "structure_kind",
                "page",
                "bbox",
                "anchors",
                "confidence",
                "col_bands",
                "row_bands",
                "audit",
            }
        }
        cells = [
            {key: value for key, value in cell.items() if key in _STANDARD_FIELD_CELL_KEYS}
            for cell in structure.get("cells") or []
            if isinstance(cell, dict)
        ]
        if cells:
            compact["cells"] = cells
        return compact
    return structure


def _build_page_blocks(
    page_number: int,
    *,
    regions: list[dict[str, Any]],
    flow_texts: list[dict[str, Any]],
    flow_key_values: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    document_type: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    _ = document_type
    blocks: list[dict[str, Any]] = []
    for seq, region in enumerate(regions):
        blocks.append(
            {
                "block_id": f"blk_p{page_number}_r{seq}",
                "morphology": str(region.get("morphology") or ""),
                "kind": str(region.get("kind") or ""),
                "ref": f"region:{region.get('region_id')}",
                "bbox": _bbox(region.get("bbox")),
                "anchor_text": str(region.get("anchor_text") or ""),
                "schema_hint": _schema_hint_for_region(region),
                "confidence": float(region.get("confidence") or 0.0),
                "audit": {"source": "region"},
            }
        )
    for idx, text in enumerate(flow_texts):
        blocks.append(
            {
                "block_id": f"blk_p{page_number}_t{idx}",
                "morphology": "S1",
                "kind": "text_flow",
                "ref": f"text:{idx}",
                "bbox": _bbox(text.get("bbox")),
                "anchor_text": str(text.get("content") or "").strip()[:80],
                "confidence": float(text.get("confidence") or 0.0),
                "audit": {"source": "flow.texts"},
            }
        )
    for idx, kv in enumerate(flow_key_values):
        blocks.append(
            {
                "block_id": f"blk_p{page_number}_kv{idx}",
                "morphology": "S5",
                "kind": "key_value",
                "ref": f"kv:{idx}",
                "bbox": _bbox(kv.get("bbox")),
                "anchor_text": str(kv.get("key") or "").strip(),
                "schema_hint": "core.key_value.header",
                "confidence": float(kv.get("confidence") or 0.0),
                "audit": {"source": "flow.key_values"},
            }
        )
    for idx, table in enumerate(tables):
        table_id = str(table.get("table_id") or f"pt_{page_number}_{idx}")
        headers = table.get("headers") or []
        anchor = "|".join(str(h) for h in headers if h) if headers else table_id
        blocks.append(
            {
                "block_id": f"blk_p{page_number}_tbl{idx}",
                "morphology": "S2",
                "kind": "physical_table",
                "ref": f"table:{table_id}",
                "bbox": _bbox(table.get("bbox")),
                "anchor_text": anchor,
                "schema_hint": "core.physical_table.ledger",
                "confidence": float(table.get("confidence") or 1.0),
                "audit": {"source": "tables", "table_id": table_id},
            }
        )
    blocks = [_drop_empty(block) for block in blocks]
    summary: dict[str, int] = {}
    for block in blocks:
        morphology = str(block.get("morphology") or "")
        if morphology:
            summary[morphology] = summary.get(morphology, 0) + 1
    return blocks, summary, [block["block_id"] for block in sorted(blocks, key=_block_sort_key)]


def _schema_hint_for_region(region: dict[str, Any]) -> str:
    hint = str(region.get("schema_hint") or "")
    if hint:
        return hint
    if region.get("morphology") == "S3":
        return "core.micro_grid.matrix"
    if region.get("morphology") == "S4":
        return "core.field_grid.kv_block"
    return ""


def _reading_order_refs_from_blocks(blocks: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for block in sorted(blocks, key=_block_sort_key):
        ref = str(block.get("ref") or "")
        if ref.startswith("region:"):
            refs.append(ref.split(":", 1)[1])
        elif ref.startswith(("text:", "table:", "kv:")):
            refs.append(ref)
    return refs


def _reading_order_for_regions_and_texts(
    regions: list[dict[str, Any]],
    flow_texts: list[dict[str, Any]],
) -> list[str]:
    entries: list[tuple[float, float, str]] = []
    for region in regions:
        entries.append((*_bbox_sort_key(region.get("bbox")), str(region.get("region_id") or "")))
    for idx, text in enumerate(flow_texts):
        entries.append((*_bbox_sort_key(text.get("bbox"), fallback=1_000_000.0 + idx), f"text:{idx}"))
    return [entry[2] for entry in sorted(entries)]


def _filter_flow_texts_not_in_regions(
    texts: list[dict[str, Any]],
    regions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    region_boxes = [_bbox(region.get("bbox")) for region in regions]
    for text in texts:
        if not isinstance(text, dict):
            continue
        bbox = _bbox(text.get("bbox"))
        if bbox and any(_mostly_inside(bbox, region_bbox) for region_bbox in region_boxes if region_bbox):
            continue
        out.append(text)
    return out


def _mostly_inside(inner: list[float], outer: list[float], threshold: float = 0.8) -> bool:
    ix0 = max(inner[0], outer[0])
    iy0 = max(inner[1], outer[1])
    ix1 = min(inner[2], outer[2])
    iy1 = min(inner[3], outer[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area = max(0.0, inner[2] - inner[0]) * max(0.0, inner[3] - inner[1])
    return bool(area and inter / area >= threshold)


def _bbox(value: Any) -> list[float]:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return []
    return []


def _bbox_sort_key(value: Any, *, fallback: float = 1_000_000.0) -> tuple[float, float]:
    bbox = _bbox(value)
    if bbox:
        return (bbox[1], bbox[0])
    return (fallback, 0.0)


def _block_sort_key(block: dict[str, Any]) -> tuple[float, float, str]:
    y, x = _bbox_sort_key(block.get("bbox"))
    return (y, x, str(block.get("block_id") or ""))


def _drop_empty(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if value not in (None, "", [], {})}
