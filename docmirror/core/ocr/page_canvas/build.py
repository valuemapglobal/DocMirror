# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build page regions from domain-specific mirror evidence."""

from __future__ import annotations

from typing import Any

from docmirror.core.ocr.page_canvas.models import PageRegion

_STANDARD_FIELD_CELL_KEYS = frozenset({
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
})


def _grid_id_to_region_id(grid_id: str) -> str:
    if grid_id.startswith("mg_"):
        return "rg_" + grid_id[3:]
    if grid_id.startswith("ls_"):
        return "rg_" + grid_id[3:]
    return f"rg_{grid_id}"


def _structure_id_to_region_id(structure_id: str) -> str:
    return _grid_id_to_region_id(structure_id)


def region_from_micro_grid(grid: dict[str, Any], *, ocr_evidence_ref: str | None = None) -> PageRegion | None:
    if not isinstance(grid, dict):
        return None
    grid_id = str(grid.get("grid_id") or "")
    bbox = grid.get("bbox")
    if not grid_id or not isinstance(bbox, list) or len(bbox) != 4:
        return None
    return PageRegion(
        region_id=_grid_id_to_region_id(grid_id),
        kind="micro_grid",
        morphology="S3",
        bbox=[float(v) for v in bbox],
        anchor_text=str(grid.get("anchor_text") or ""),
        structure=dict(grid),
        confidence=float(grid.get("confidence") or 0.0),
        ocr_evidence_ref=ocr_evidence_ref,
        audit={"source": "micro_grid", "grid_id": grid_id},
    )


def region_from_local_structure(
    structure: dict[str, Any],
    *,
    ocr_evidence_ref: str | None = None,
) -> PageRegion | None:
    if not isinstance(structure, dict):
        return None
    structure_id = str(structure.get("structure_id") or "")
    bbox = structure.get("bbox")
    if not structure_id or not isinstance(bbox, list) or len(bbox) != 4:
        return None
    structure_kind = str(structure.get("structure_kind") or "local_structure")
    if structure_kind == "field_grid":
        kind = "field_grid"
        morphology = "S4"
    elif structure_kind == "label_value_graph":
        kind = "label_value_graph"
        morphology = "S4"
    else:
        kind = structure_kind
        morphology = "S4"
    anchors = structure.get("anchors") or ()
    anchor_text = " ".join(str(a) for a in anchors if a)
    nodes = structure.get("nodes") or []
    if not anchor_text and nodes:
        anchor_nodes = [n for n in nodes if isinstance(n, dict) and n.get("role") == "anchor"]
        anchor_text = " ".join(str(n.get("text") or "") for n in anchor_nodes)
    return PageRegion(
        region_id=_structure_id_to_region_id(structure_id),
        kind=kind,
        morphology=morphology,
        bbox=[float(v) for v in bbox],
        anchor_text=anchor_text.strip(),
        structure=dict(structure),
        confidence=float(structure.get("confidence") or 0.0),
        ocr_evidence_ref=ocr_evidence_ref,
        audit={"source": "local_structure", "structure_id": structure_id, "structure_kind": structure_kind},
    )


def compact_region_structure(region: dict[str, Any], *, forensic: bool = False) -> dict[str, Any]:
    """Compact region structure for standard mirror projection."""
    if forensic or not isinstance(region, dict):
        return region.get("structure", region) if isinstance(region, dict) else {}
    kind = region.get("kind")
    structure = region.get("structure")
    if not isinstance(structure, dict):
        return structure or {}
    if kind == "micro_grid":
        return _compact_micro_grid_structure(structure)
    if kind in {"field_grid", "label_value_graph"}:
        compact = {k: v for k, v in structure.items() if k in {
            "structure_id",
            "structure_kind",
            "page",
            "bbox",
            "anchors",
            "confidence",
            "col_bands",
            "row_bands",
            "audit",
        }}
        cells = structure.get("cells") or []
        compact_cells = []
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            compact_cells.append({k: v for k, v in cell.items() if k in _STANDARD_FIELD_CELL_KEYS})
        if compact_cells:
            compact["cells"] = compact_cells
        return compact
    return structure


_STANDARD_MICRO_GRID_KEYS = frozenset({
    "grid_id", "page", "bbox", "grid_type_hint", "anchor_text", "coordinate_system",
    "geometry_source", "confidence", "row_bands", "col_bands", "cells",
})
_STANDARD_MICRO_GRID_CELL_KEYS = frozenset({
    "row_index", "col_index", "bbox", "text", "confidence", "geometry_status",
    "geometry_loss_reason", "assignment_confidence", "assignment_method",
    "recognition_source", "role",
})


def _compact_micro_grid_structure(grid: dict[str, Any]) -> dict[str, Any]:
    compact = {k: v for k, v in grid.items() if k in _STANDARD_MICRO_GRID_KEYS}
    rows: list[list[dict[str, Any]]] = []
    for row in grid.get("cells") or []:
        if not isinstance(row, list):
            continue
        cells = [
            {k: v for k, v in cell.items() if k in _STANDARD_MICRO_GRID_CELL_KEYS}
            for cell in row
            if isinstance(cell, dict)
        ]
        rows.append(cells)
    if rows:
        compact["cells"] = rows
    return compact


def _lines_and_dims_for_page(
    domain_specific: dict[str, Any],
    page: int,
) -> tuple[list[Any], list[Any], float | None, float | None]:
    from docmirror.models.mirror.domain_access import (
        raw_local_structure_evidence_from_domain_specific,
        raw_micro_grid_evidence_from_domain_specific,
    )

    lines: list[Any] = []
    tokens: list[Any] = []
    page_width: float | None = None
    page_height: float | None = None
    for bundle in domain_specific.get("_page_evidence_bundles") or []:
        if not isinstance(bundle, dict) or int(bundle.get("page") or 0) != page:
            continue
        if bundle.get("page_width") is not None:
            page_width = float(bundle["page_width"])
        if bundle.get("page_height") is not None:
            page_height = float(bundle["page_height"])
    for evidence in (
        raw_micro_grid_evidence_from_domain_specific(domain_specific)
        + raw_local_structure_evidence_from_domain_specific(domain_specific)
    ):
        if int(evidence.get("page") or 0) != page:
            continue
        lines.extend(evidence.get("lines") or [])
        tokens.extend(evidence.get("tokens") or [])
        if page_width is None and evidence.get("page_width") is not None:
            page_width = float(evidence["page_width"])
        if page_height is None and evidence.get("page_height") is not None:
            page_height = float(evidence["page_height"])
    return lines, tokens, page_width, page_height


def _apply_detect_audit_for_page(
    regions: list[PageRegion],
    *,
    domain_specific: dict[str, Any] | None,
    page: int,
) -> None:
    if not regions:
        return
    if not domain_specific:
        from docmirror.core.ocr.page_canvas.detect import annotate_region_nested_in_audit

        annotate_region_nested_in_audit(regions)
        return
    lines, tokens, page_width, page_height = _lines_and_dims_for_page(domain_specific, page)
    if lines:
        from docmirror.core.ocr.page_canvas.detect import (
            annotate_regions_with_detect_candidates,
            detect_page_region_candidates,
        )
        from docmirror.core.ocr.micro_grid.models import OCRToken

        token_objs: list[OCRToken] = []
        for token in tokens:
            if isinstance(token, OCRToken):
                token_objs.append(token)
            elif isinstance(token, dict):
                bbox = token.get("bbox") or token.get("raw_bbox")
                if bbox and len(bbox) == 4:
                    token_objs.append(
                        OCRToken(
                            token_id=str(token.get("token_id") or ""),
                            text=str(token.get("text") or ""),
                            bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
                            confidence=float(token.get("confidence") or 0.0),
                            page=page,
                            source=str(token.get("source") or ""),
                        )
                    )
        candidates = detect_page_region_candidates(
            lines,
            tokens=token_objs or None,
            page=page,
            page_width=page_width,
            page_height=page_height,
        )
        annotate_regions_with_detect_candidates(regions, candidates)
        return
    from docmirror.core.ocr.page_canvas.detect import annotate_region_nested_in_audit

    annotate_region_nested_in_audit(regions)


def build_page_regions_for_page(
    page: int,
    *,
    micro_grids: list[dict[str, Any]] | None = None,
    local_structure_evidence: list[dict[str, Any]] | None = None,
    ocr_evidence_ref: str | None = None,
    domain_specific: dict[str, Any] | None = None,
) -> list[PageRegion]:
    regions: list[PageRegion] = []
    seen_ids: set[str] = set()

    for grid in micro_grids or []:
        if not isinstance(grid, dict) or int(grid.get("page") or 0) != page:
            continue
        region = region_from_micro_grid(grid, ocr_evidence_ref=ocr_evidence_ref)
        if region is None or region.region_id in seen_ids:
            continue
        seen_ids.add(region.region_id)
        regions.append(region)

    for evidence in local_structure_evidence or []:
        if not isinstance(evidence, dict) or int(evidence.get("page") or 0) != page:
            continue
        ref = str(evidence.get("ocr_page_ref") or ocr_evidence_ref or "") or None
        for structure in evidence.get("structures") or []:
            region = region_from_local_structure(structure, ocr_evidence_ref=ref)
            if region is None or region.region_id in seen_ids:
                continue
            seen_ids.add(region.region_id)
            regions.append(region)

    _apply_detect_audit_for_page(regions, domain_specific=domain_specific, page=page)
    regions.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
    return regions


def build_regions_from_domain_specific(
    domain_specific: dict[str, Any] | None,
    *,
    ocr_refs_by_page: dict[int, str] | None = None,
) -> dict[int, list[PageRegion]]:
    from docmirror.core.ocr.page_canvas.evidence_bundles import micro_grid_structures_from_bundles
    from docmirror.models.mirror.domain_access import raw_local_structure_evidence_from_domain_specific

    ds = domain_specific or {}
    micro_grids = micro_grid_structures_from_bundles(ds)
    local_evidence = raw_local_structure_evidence_from_domain_specific(ds)
    pages: set[int] = set()
    for grid in micro_grids:
        if isinstance(grid, dict) and grid.get("page"):
            pages.add(int(grid["page"]))
    for evidence in local_evidence:
        if isinstance(evidence, dict) and evidence.get("page"):
            pages.add(int(evidence["page"]))
    for bundle in ds.get("_page_evidence_bundles") or []:
        if isinstance(bundle, dict) and bundle.get("page"):
            pages.add(int(bundle["page"]))
    out: dict[int, list[PageRegion]] = {}
    refs = ocr_refs_by_page or {}
    for page in sorted(pages):
        out[page] = build_page_regions_for_page(
            page,
            micro_grids=micro_grids,
            local_structure_evidence=local_evidence,
            ocr_evidence_ref=refs.get(page),
            domain_specific=ds,
        )
    return out


def reading_order_for_regions(regions: list[PageRegion]) -> list[str]:
    return [region.region_id for region in sorted(regions, key=lambda r: (r.bbox[1], r.bbox[0]))]


def reading_order_for_page(
    regions: list[PageRegion],
    flow_texts: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Merge region ids and flow text refs (`text:{index}`) by vertical position.

    Deprecated for export — prefer ``reading_order_v2`` / block_index (Design 20).
    """
    if not flow_texts:
        return reading_order_for_regions(regions)
    entries: list[tuple[float, float, str]] = []
    for region in regions:
        entries.append((region.bbox[1], region.bbox[0], region.region_id))
    for idx, text in enumerate(flow_texts):
        if not isinstance(text, dict):
            continue
        bbox = text.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            y0, x0 = float(bbox[1]), float(bbox[0])
        else:
            y0, x0 = 1_000_000.0 + float(idx), float(idx)
        entries.append((y0, x0, f"text:{idx}"))
    entries.sort(key=lambda item: (item[0], item[1]))
    return [entry[2] for entry in entries]


def reading_order_v2(
    page_number: int,
    *,
    regions: list[PageRegion],
    flow_texts: list[dict[str, Any]] | None = None,
    flow_key_values: list[dict[str, Any]] | None = None,
    tables: list[dict[str, Any]] | None = None,
    document_type: str | None = None,
) -> tuple[list[str], list[str]]:
    """Full-morphology reading order via UBI blocks (Design 20)."""
    from docmirror.core.ocr.page_canvas.block_index import (
        build_page_blocks,
        reading_order_v1_from_blocks,
    )

    blocks, _summary, reading_order = build_page_blocks(
        page_number,
        regions=regions,
        flow_texts=flow_texts,
        flow_key_values=flow_key_values,
        tables=tables,
        document_type=document_type,
    )
    return reading_order, reading_order_v1_from_blocks(blocks)
