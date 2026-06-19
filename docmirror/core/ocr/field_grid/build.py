# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build field-grid structures from OCR block evidence."""

from __future__ import annotations

import re
from typing import Any, Callable

from docmirror.core.ocr.field_grid.assemble import (
    build_field_cell,
    first_dotted_date,
    line_has_mixed_semantics,
    merge_in_column_continuations,
    parse_as_of_date,
    route_semantic_tokens_to_bands,
    score_cell_for_label,
    split_line_into_semantic_tokens,
    _line_char_tokens,
)
from docmirror.core.ocr.field_grid.assign import cell_bbox
from docmirror.core.ocr.grid_materialize import exclusive_assign_tokens_to_grid
from docmirror.core.ocr.field_grid.bands import (
    estimate_col_bands_from_label_rows,
    extract_label_tokens,
    nearest_header_row_for_y,
    segment_field_sections,
    value_row_band,
)
from docmirror.core.ocr.field_grid.models import FieldCell, LabelToken
from docmirror.core.ocr.field_grid.repair import repair_field_cells
from docmirror.core.ocr.field_grid.type_gate import apply_type_gate
from docmirror.core.ocr.field_grid.tokens import expand_tokens_to_char_tokens
from docmirror.core.ocr.local_structure.models import LocalStructure, StructureEdge, StructureNode
from docmirror.core.ocr.local_structure.utils import union_bbox
from docmirror.core.ocr.micro_grid.models import OCRToken


def _collect_section_fragments(
    *,
    section: dict[str, Any],
    section_idx: int,
    tokens: list[OCRToken],
    roi_bbox: tuple[float, float, float, float],
    page: int,
    prefix: str,
    col_index_offset: int = 0,
) -> tuple[list[FieldCell], list[LabelToken], list[dict[str, Any]], int]:
    label_lines = section["label_lines"]
    value_lines = section["value_lines"]
    label_tokens = extract_label_tokens(label_lines, tokens)
    if len(label_tokens) < 1:
        return [], [], [], col_index_offset

    col_bands = estimate_col_bands_from_label_rows(label_lines, tokens, roi_bbox)
    if not col_bands:
        return [], [], [], col_index_offset

    for local_idx, band in enumerate(col_bands):
        band["index"] = col_index_offset + local_idx
    next_offset = col_index_offset + len(col_bands)

    fragments: list[FieldCell] = []
    consumed_token_ids: set[str] = set()
    pending_rows: list[tuple[int, dict[str, Any], dict[str, Any], list[OCRToken]]] = []

    for row_idx, line in enumerate(value_lines):
        row_band = value_row_band(line, index=section_idx * 100 + row_idx)
        line_text = line["text"]

        if line_has_mixed_semantics(line_text):
            semantic = split_line_into_semantic_tokens(line, page=page, prefix=prefix)
            if semantic:
                routed = route_semantic_tokens_to_bands(semantic, col_bands)
                for col_band in col_bands:
                    col_idx = int(col_band["index"])
                    bucket = routed.get(col_idx, [])
                    if not bucket:
                        continue
                    consumed_token_ids.update(token.token_id for token in bucket)
                    cell = build_field_cell(
                        cell_id=f"{prefix}_cell_s{section_idx}_r{row_idx}_c{col_idx}",
                        row_band=row_band,
                        col_band=col_band,
                        tokens=bucket,
                        line_ids=(line["line_id"],),
                        label_text=str(col_band.get("header") or ""),
                        assignment_method_override="semantic:type_route",
                    )
                    if cell.text:
                        fragments.append(cell)
                continue

        line_tokens = [
            token
            for token in tokens
            if token.token_id not in consumed_token_ids
            and line["bbox"][0] - 4.0 <= token.center[0] <= line["bbox"][2] + 4.0
            and line["bbox"][1] - 6.0 <= token.center[1] <= line["bbox"][3] + 6.0
        ]
        if not line_tokens:
            semantic = split_line_into_semantic_tokens(line, page=page, prefix=prefix)
            if semantic:
                line_tokens = [token for token in semantic if token.token_id not in consumed_token_ids]
            if not line_tokens:
                line_tokens = expand_tokens_to_char_tokens(
                    [
                        OCRToken(
                            token_id=f"{prefix}_ls_{line['line_id']}",
                            text=line["text"],
                            bbox=line["bbox"],
                            confidence=line.get("confidence", 1.0),
                            page=page,
                            source="ocr_line_fallback",
                        )
                    ]
                )

        consumed_token_ids.update(token.token_id for token in line_tokens)
        pending_rows.append((row_idx, line, row_band, line_tokens))

    if pending_rows:
        row_bands = [row_band for _row_idx, _line, row_band, _tokens in pending_rows]
        section_tokens = [token for *_rest, row_tokens in pending_rows for token in row_tokens]
        assignments = exclusive_assign_tokens_to_grid(section_tokens, row_bands, col_bands)
        for row_idx, line, row_band, _line_tokens in pending_rows:
            for col_band in col_bands:
                col_idx = int(col_band["index"])
                bucket = assignments.get((int(row_band["index"]), col_idx), [])
                if not bucket:
                    bucket = _line_char_tokens(line, col_band, page=page, prefix=prefix)
                if not bucket:
                    continue
                cell = build_field_cell(
                    cell_id=f"{prefix}_cell_s{section_idx}_r{row_idx}_c{col_idx}",
                    row_band=row_band,
                    col_band=col_band,
                    tokens=bucket,
                    line_ids=(line["line_id"],),
                    label_text=str(col_band.get("header") or ""),
                )
                if cell.text:
                    fragments.append(cell)

    return fragments, label_tokens, col_bands, next_offset


def _find_as_of_date(block_lines: list[dict[str, Any]]) -> str | None:
    for line in block_lines:
        parsed = parse_as_of_date(line["text"])
        if parsed:
            return parsed
    return None


def _fill_missing_due_date(
    merged_cells: list[FieldCell],
    *,
    col_bands: list[dict[str, Any]],
    cell_by_label: dict[str, FieldCell],
    as_of_date: str | None,
    prefix: str,
    page: int,
) -> list[FieldCell]:
    due_band = next(
        (band for band in col_bands if "到期日期" in str(band.get("header") or "")),
        None,
    )
    if due_band is None:
        return merged_cells

    due_label = str(due_band.get("header") or "")
    due_cell = cell_by_label.get(due_label)
    if due_cell is not None and str(due_cell.text or "").strip():
        return merged_cells

    fill_value = as_of_date
    if not fill_value:
        close_cell = next(
            (cell for label, cell in cell_by_label.items() if "关闭日期" in label),
            None,
        )
        if close_cell is not None:
            fill_value = first_dotted_date(str(close_cell.text or ""))

    if not fill_value:
        return merged_cells

    row_band = {
        "index": 999,
        "bbox": list(due_band["bbox"]),
        "role": "value",
        "source_line_id": f"{prefix}_due_inferred",
        "geometry_status": "estimated",
    }
    inferred = FieldCell(
        cell_id=f"{prefix}_cell_due_inferred",
        row_index=999,
        col_index=int(due_band["index"]),
        label_text=due_label,
        text=fill_value,
        raw_text=fill_value,
        bbox=cell_bbox(row_band, due_band),
        token_ids=(),
        line_ids=(),
        confidence=0.75,
        assignment_confidence=0.75,
        assignment_method="inferred:as_of_or_close_date",
        geometry_status="estimated",
        inferred_types=("date",),
        audit={"inferred_from": "as_of_date" if as_of_date else "close_date"},
    )
    inferred = apply_type_gate(inferred)
    cell_by_label[due_label] = inferred
    return [*merged_cells, inferred]


def build_field_grid_from_block(
    block_lines: list[dict[str, Any]],
    *,
    structure_id: str,
    tokens: list[OCRToken],
    page: int,
    prefix: str,
    anchors: tuple[str, ...],
    candidate_id: str,
    candidate_score: float,
    is_label_line: Callable[[dict[str, Any]], bool],
    page_image: Any | None = None,
    page_width: float | None = None,
    page_height: float | None = None,
    enable_repair: bool = False,
) -> LocalStructure | None:
    if len(block_lines) < 3:
        return None

    anchor_line = block_lines[0]
    anchor_display = str(anchors[0]) if anchors and not re.search(r"账户\s*\d+", anchor_line["text"]) else anchor_line["text"]
    roi_bbox = union_bbox(line["bbox"] for line in block_lines)
    sections = segment_field_sections(block_lines, is_label_line=is_label_line)
    if not sections:
        return None

    all_fragments: list[FieldCell] = []
    all_label_tokens: list[LabelToken] = []
    all_col_bands: list[dict[str, Any]] = []
    band_offset = 0

    for section_idx, section in enumerate(sections):
        fragments, label_tokens, col_bands, band_offset = _collect_section_fragments(
            section=section,
            section_idx=section_idx,
            tokens=tokens,
            roi_bbox=roi_bbox,
            page=page,
            prefix=prefix,
            col_index_offset=band_offset,
        )
        all_fragments.extend(fragments)
        all_label_tokens.extend(label_tokens)
        all_col_bands.extend(col_bands)

    if not all_fragments or len(all_label_tokens) < 2:
        return None

    merged_cells = merge_in_column_continuations(all_fragments)
    if enable_repair and page_image is not None and page_width and page_height:
        merged_cells = repair_field_cells(
            merged_cells,
            page_image=page_image,
            page_width=float(page_width),
            page_height=float(page_height),
        )

    as_of_date = _find_as_of_date(block_lines)
    cell_by_label: dict[str, FieldCell] = {}
    for cell in merged_cells:
        label_key = str(cell.label_text or "")
        existing = cell_by_label.get(label_key)
        if existing is None or score_cell_for_label(cell, label_key) > score_cell_for_label(existing, label_key):
            cell_by_label[label_key] = cell
    merged_cells = _fill_missing_due_date(
        merged_cells,
        col_bands=all_col_bands,
        cell_by_label=cell_by_label,
        as_of_date=as_of_date,
        prefix=prefix,
        page=page,
    )

    nodes: list[StructureNode] = [
        StructureNode(
            node_id=f"{prefix}_anchor",
            role="anchor",
            text=anchor_display,
            bbox=anchor_line["bbox"],
            page=page,
            line_ids=(anchor_line["line_id"],),
            confidence=anchor_line.get("confidence", 1.0),
        )
    ]
    edges: list[StructureEdge] = []
    label_nodes: list[StructureNode] = []

    for idx, label in enumerate(all_label_tokens):
        node = StructureNode(
            node_id=f"{prefix}_label_{idx}",
            role="label",
            text=label.text,
            bbox=label.bbox,
            page=page,
            token_ids=label.token_ids,
            line_ids=(label.line_id,),
            confidence=label.confidence,
        )
        label_nodes.append(node)
        nodes.append(node)

    for idx, label in enumerate(all_label_tokens):
        cell = cell_by_label.get(label.text)
        if cell is None:
            continue
        value_node = StructureNode(
            node_id=f"{prefix}_value_{idx}",
            role="value",
            text=cell.text,
            bbox=cell.bbox,
            page=page,
            token_ids=cell.token_ids,
            line_ids=cell.line_ids,
            confidence=cell.confidence,
            audit={
                "cell_id": cell.cell_id,
                "assignment_method": cell.assignment_method,
                "geometry_status": cell.geometry_status,
                **({"quarantine_reason": cell.quarantine_reason} if cell.quarantine_reason else {}),
            },
        )
        nodes.append(value_node)
        edges.append(
            StructureEdge(
                edge_id=f"{prefix}_edge_{idx}",
                source_node_id=label_nodes[idx].node_id,
                target_node_id=value_node.node_id,
                relation="label_of",
                confidence=cell.assignment_confidence,
                reason_codes=("field_grid_col_projection", "in_column_merge"),
            )
        )

    row_bands = tuple(
        {
            "index": idx,
            "bbox": list(line["bbox"]),
            "role": "anchor" if idx == 0 else ("label" if is_label_line(line) else "value"),
            "source_line_id": line["line_id"],
        }
        for idx, line in enumerate(block_lines)
    )

    return LocalStructure(
        structure_id=structure_id,
        page=page,
        bbox=roi_bbox,
        structure_kind="field_grid",
        anchors=anchors,
        row_bands=row_bands,
        col_bands=tuple(all_col_bands),
        nodes=tuple(nodes),
        edges=tuple(edges),
        cells=tuple(merged_cells),
        confidence=min(candidate_score, 0.92),
        audit={
            "candidate_id": candidate_id,
            "label_count": len(all_label_tokens),
            "cell_count": len(merged_cells),
            "section_count": len(sections),
            "builder": "field_grid",
        },
    )
