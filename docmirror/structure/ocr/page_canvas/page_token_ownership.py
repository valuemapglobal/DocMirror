# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Page line ownership SSOT (Design 19 axiom A — P0).

Each OCR line index maps to at most one owner: ``prose_flow`` or a structure
element inside a region. ``flow.texts`` is the complement of owned lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docmirror.structure.ocr.page_canvas.models import PageRegion
from docmirror.structure.ocr.page_canvas.structure_coverage import text_mostly_inside_bbox

_REGION_KINDS = frozenset({"micro_grid", "field_grid", "label_value_graph"})

_DEFAULT_Y_THRESHOLD = 0.7
_DEFAULT_X_THRESHOLD = 0.7


@dataclass(frozen=True)
class StructureElement:
    region_id: str
    region_kind: str
    element_type: str
    element_ref: str
    bbox: tuple[float, float, float, float]
    priority: int


@dataclass(frozen=True)
class LineOwnership:
    line_index: int
    owner: str
    element_ref: str | None = None
    region_kind: str | None = None


def _bbox_tuple(raw: Any) -> tuple[float, float, float, float] | None:
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    return None


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = bbox
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _element_priority(element_type: str) -> int:
    return {
        "cell": 0,
        "row_band": 1,
        "col_band": 1,
        "node": 2,
        "region_envelope": 3,
    }.get(element_type, 4)


def iter_structure_elements(region: PageRegion) -> list[StructureElement]:
    """Collect typed structure elements for a region (cells preferred over envelope)."""
    structure = region.structure if isinstance(region.structure, dict) else {}
    out: list[StructureElement] = []

    for band_key, element_type in (("row_bands", "row_band"), ("col_bands", "col_band")):
        for idx, band in enumerate(structure.get(band_key) or []):
            if not isinstance(band, dict):
                continue
            bbox = _bbox_tuple(band.get("bbox"))
            if bbox is None:
                continue
            out.append(
                StructureElement(
                    region_id=region.region_id,
                    region_kind=region.kind,
                    element_type=element_type,
                    element_ref=f"{element_type}:{idx}",
                    bbox=bbox,
                    priority=_element_priority(element_type),
                )
            )

    cells = structure.get("cells") or []
    if cells and isinstance(cells[0], list):
        for row_idx, row in enumerate(cells):
            if not isinstance(row, list):
                continue
            for col_idx, cell in enumerate(row):
                if not isinstance(cell, dict):
                    continue
                bbox = _bbox_tuple(cell.get("bbox"))
                if bbox is None:
                    continue
                row_index = cell.get("row_index", row_idx)
                col_index = cell.get("col_index", col_idx)
                out.append(
                    StructureElement(
                        region_id=region.region_id,
                        region_kind=region.kind,
                        element_type="cell",
                        element_ref=f"cell:{row_index}:{col_index}",
                        bbox=bbox,
                        priority=_element_priority("cell"),
                    )
                )
    else:
        for idx, cell in enumerate(cells):
            if not isinstance(cell, dict):
                continue
            bbox = _bbox_tuple(cell.get("bbox"))
            if bbox is None:
                continue
            row_index = cell.get("row_index", idx)
            col_index = cell.get("col_index", 0)
            out.append(
                StructureElement(
                    region_id=region.region_id,
                    region_kind=region.kind,
                    element_type="cell",
                    element_ref=f"cell:{row_index}:{col_index}",
                    bbox=bbox,
                    priority=_element_priority("cell"),
                )
            )

    for idx, node in enumerate(structure.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        bbox = _bbox_tuple(node.get("bbox"))
        if bbox is None:
            continue
        out.append(
            StructureElement(
                region_id=region.region_id,
                region_kind=region.kind,
                element_type="node",
                element_ref=f"node:{idx}",
                bbox=bbox,
                priority=_element_priority("node"),
            )
        )

    if not out:
        envelope = _bbox_tuple(region.bbox)
        if envelope is not None:
            out.append(
                StructureElement(
                    region_id=region.region_id,
                    region_kind=region.kind,
                    element_type="region_envelope",
                    element_ref="region_envelope",
                    bbox=envelope,
                    priority=_element_priority("region_envelope"),
                )
            )
    return out


def _overlap_min_axis_ratio(
    text_bbox: list[float],
    target_bbox: tuple[float, float, float, float],
    *,
    y_threshold: float,
    x_threshold: float,
) -> float | None:
    if not text_mostly_inside_bbox(
        text_bbox,
        list(target_bbox),
        y_threshold=y_threshold,
        x_threshold=x_threshold,
    ):
        return None
    tx0, ty0, tx1, ty1 = (float(v) for v in text_bbox)
    rx0, ry0, rx1, ry1 = target_bbox
    text_h = max(ty1 - ty0, 1e-6)
    text_w = max(tx1 - tx0, 1e-6)
    iy0, iy1 = max(ty0, ry0), min(ty1, ry1)
    ix0, ix1 = max(tx0, rx0), min(tx1, rx1)
    y_ratio = (iy1 - iy0) / text_h
    x_ratio = (ix1 - ix0) / text_w
    return min(y_ratio, x_ratio)


def _best_element_for_line(
    text_bbox: list[float],
    elements: list[StructureElement],
    *,
    y_threshold: float = _DEFAULT_Y_THRESHOLD,
    x_threshold: float = _DEFAULT_X_THRESHOLD,
) -> StructureElement | None:
    best: StructureElement | None = None
    best_key: tuple[float, float, float] | None = None
    for element in elements:
        score = _overlap_min_axis_ratio(
            text_bbox,
            element.bbox,
            y_threshold=y_threshold,
            x_threshold=x_threshold,
        )
        if score is None:
            continue
        key = (score, float(-element.priority), -_bbox_area(element.bbox))
        if best_key is None or key > best_key:
            best = element
            best_key = key
    return best


def collect_structure_elements(regions: list[PageRegion]) -> list[StructureElement]:
    """Flatten structure elements from all structural regions on a page."""
    elements: list[StructureElement] = []
    for region in regions:
        if region.kind not in _REGION_KINDS:
            continue
        elements.extend(iter_structure_elements(region))
    return elements


def assign_line_ownership(
    texts: list[dict[str, Any]],
    regions: list[PageRegion],
    *,
    y_threshold: float = _DEFAULT_Y_THRESHOLD,
    x_threshold: float = _DEFAULT_X_THRESHOLD,
) -> list[LineOwnership]:
    """Assign each line index to prose_flow or exactly one structure element."""
    elements = collect_structure_elements(regions)
    ownership: list[LineOwnership] = []
    for idx, text in enumerate(texts):
        if not isinstance(text, dict):
            ownership.append(LineOwnership(line_index=idx, owner="prose_flow"))
            continue
        bbox = text.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            ownership.append(LineOwnership(line_index=idx, owner="prose_flow"))
            continue
        winner = _best_element_for_line(
            bbox,
            elements,
            y_threshold=y_threshold,
            x_threshold=x_threshold,
        )
        if winner is None:
            ownership.append(LineOwnership(line_index=idx, owner="prose_flow"))
            continue
        ownership.append(
            LineOwnership(
                line_index=idx,
                owner=winner.region_id,
                element_ref=winner.element_ref,
                region_kind=winner.region_kind,
            )
        )
    return ownership


def flow_texts_complement(
    texts: list[dict[str, Any]],
    ownership: list[LineOwnership],
) -> list[dict[str, Any]]:
    """Return lines whose owner is prose_flow (flow SSOT complement)."""
    owned_indices = {item.line_index for item in ownership if item.owner != "prose_flow"}
    return [text for idx, text in enumerate(texts) if idx not in owned_indices]


def filter_flow_by_ownership(
    texts: list[dict[str, Any]],
    regions: list[PageRegion],
    *,
    y_threshold: float = _DEFAULT_Y_THRESHOLD,
    x_threshold: float = _DEFAULT_X_THRESHOLD,
) -> list[dict[str, Any]]:
    """Build flow.texts from line ownership (single assign pass)."""
    if not texts or not regions:
        return list(texts)
    ownership = assign_line_ownership(
        texts,
        regions,
        y_threshold=y_threshold,
        x_threshold=x_threshold,
    )
    return flow_texts_complement(texts, ownership)


def owned_line_indices(ownership: list[LineOwnership]) -> set[int]:
    return {item.line_index for item in ownership if item.owner != "prose_flow"}


def assert_no_flow_structure_dual_assign(
    texts: list[dict[str, Any]],
    regions: list[PageRegion],
    *,
    y_threshold: float = _DEFAULT_Y_THRESHOLD,
    x_threshold: float = _DEFAULT_X_THRESHOLD,
) -> None:
    """Contract helper: owned lines must not appear in flow complement."""
    ownership = assign_line_ownership(
        texts,
        regions,
        y_threshold=y_threshold,
        x_threshold=x_threshold,
    )
    owned = owned_line_indices(ownership)
    flow_indices = {idx for idx, _ in enumerate(texts) if idx not in owned}
    overlap = owned & flow_indices
    if overlap:
        raise AssertionError(f"lines owned by structure also in flow: {sorted(overlap)}")
