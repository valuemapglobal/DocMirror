# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build generic local label/value structure graphs from OCR lines."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from typing import Any

from docmirror.core.ocr.local_structure.detect import detect_local_structure_candidates
from docmirror.core.ocr.local_structure.models import (
    BBox,
    LocalStructure,
    LocalStructureCandidate,
    StructureEdge,
    StructureNode,
)
from docmirror.core.ocr.local_structure.utils import line_items, union_bbox
from docmirror.core.ocr.micro_grid.models import OCRToken

_LABEL_SUFFIX_RE = re.compile(r"(机构|标识|日期|币种|金额|种类|方式|状态|编号|名称|期限|频率|责任|类型|余额|用途|利率)")
_NUMBERED_HEADING_RE = re.compile(r"^[^\W\d_]{1,8}\s*\d{1,3}$", re.UNICODE)

ENABLE_FIELD_GRID = os.environ.get("DOCMIRROR_SLSR_FIELD_GRID", "1") not in {"0", "false", "False"}


def _center(bbox: BBox) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _interpolate_segments(line: dict[str, Any]) -> list[tuple[str, BBox]]:
    text = line["text"]
    suffixes = list(_LABEL_SUFFIX_RE.finditer(text))
    if len(suffixes) > 1:
        x0, y0, x1, y1 = line["bbox"]
        width = max(x1 - x0, 1.0)
        text_len = max(len(text), 1)
        segments: list[tuple[str, BBox]] = []
        start = 0
        for match in suffixes:
            end = match.end()
            part = text[start:end].strip()
            if part:
                segments.append(
                    (
                        part,
                        (
                            x0 + width * (start / text_len),
                            y0,
                            x0 + width * (end / text_len),
                            y1,
                        ),
                    )
                )
            start = end
        tail = text[start:].strip()
        if tail and not segments:
            return [(text, line["bbox"])]
        return segments
    parts = [p for p in re.split(r"\s+", text.strip()) if p]
    if len(parts) <= 1:
        return [(text, line["bbox"])]
    x0, y0, x1, y1 = line["bbox"]
    total_chars = sum(max(len(p), 1) for p in parts)
    cursor = x0
    out: list[tuple[str, BBox]] = []
    width = max(x1 - x0, 1.0)
    for part in parts:
        part_w = width * (max(len(part), 1) / max(total_chars, 1))
        out.append((part, (cursor, y0, cursor + part_w, y1)))
        cursor += part_w
    return out


def _is_label_line(line: dict[str, Any]) -> bool:
    text = line["text"]
    return bool(_LABEL_SUFFIX_RE.search(text)) and not _NUMBERED_HEADING_RE.match(text.replace(" ", ""))


def _line_tokens(tokens: list[OCRToken], bbox: BBox) -> tuple[str, ...]:
    x0, y0, x1, y1 = bbox
    ids = [
        token.token_id for token in tokens if x0 <= token.center[0] <= x1 and y0 - 4.0 <= token.center[1] <= y1 + 4.0
    ]
    return tuple(ids)


def _x_overlap_ratio(a: BBox, b: BBox) -> float:
    ax0, _ay0, ax1, _ay1 = a
    bx0, _by0, bx1, _by1 = b
    overlap = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    denom = max(min(ax1 - ax0, bx1 - bx0), 1.0)
    return overlap / denom


def _split_value_line_against_labels(
    value_line: dict[str, Any],
    labels: list[StructureNode],
    tokens: list[OCRToken],
) -> list[tuple[StructureNode, str, BBox, tuple[str, ...], float]]:
    if not labels:
        return []
    line_bbox = value_line["bbox"]
    line_tokens = [
        token
        for token in tokens
        if line_bbox[0] - 2.0 <= token.center[0] <= line_bbox[2] + 2.0
        and line_bbox[1] - 4.0 <= token.center[1] <= line_bbox[3] + 4.0
    ]
    labels_sorted = sorted(labels, key=lambda label: label.center[0])
    out: list[tuple[StructureNode, str, BBox, tuple[str, ...], float]] = []
    if line_tokens:
        for label in labels_sorted:
            lx0, _ly0, lx1, _ly1 = label.bbox
            margin = max((lx1 - lx0) * 0.55, 12.0)
            bucket = [token for token in line_tokens if lx0 - margin <= token.center[0] <= lx1 + margin]
            if not bucket:
                continue
            bucket = sorted(bucket, key=lambda token: token.bbox[0])
            text = "".join(token.text for token in bucket).strip()
            if not text:
                continue
            out.append(
                (
                    label,
                    text,
                    union_bbox(token.bbox for token in bucket),
                    tuple(token.token_id for token in bucket),
                    min(token.confidence for token in bucket),
                )
            )
        if out:
            return out

    segments = _interpolate_segments(value_line)
    if len(segments) <= 1:
        return [
            (labels_sorted[0], value_line["text"], line_bbox, _line_tokens(tokens, line_bbox), value_line["confidence"])
        ]

    for idx, (text, bbox) in enumerate(segments[: len(labels_sorted)]):
        if not text.strip():
            continue
        out.append((labels_sorted[idx], text.strip(), bbox, _line_tokens(tokens, bbox), value_line["confidence"]))
    return out


def _nearest_values_for_labels(
    *,
    labels: list[StructureNode],
    value_lines: list[dict[str, Any]],
    tokens: list[OCRToken],
    page: int,
    prefix: str,
) -> tuple[list[StructureNode], list[StructureEdge]]:
    values: list[StructureNode] = []
    edges: list[StructureEdge] = []
    used_lines: set[str] = set()
    labels_by_line: dict[str, list[StructureNode]] = {}
    for label in labels:
        if label.line_ids:
            labels_by_line.setdefault(label.line_ids[0], []).append(label)
    value_by_y = sorted(value_lines, key=lambda line: line["bbox"][1])

    edge_idx = 0
    for label_line_id, line_labels in labels_by_line.items():
        label_y = min(label.bbox[3] for label in line_labels)
        below = [line for line in value_by_y if line["line_id"] not in used_lines and line["bbox"][1] >= label_y - 1.0]
        if not below:
            continue
        value_line = min(below, key=lambda line: line["bbox"][1] - label_y)
        if value_line["bbox"][1] - label_y > 80.0:
            continue
        paired = _split_value_line_against_labels(value_line, line_labels, tokens)
        if len(paired) < 2:
            continue
        used_lines.add(value_line["line_id"])
        for label, text, bbox, token_ids, confidence in paired:
            value_node = StructureNode(
                node_id=f"{prefix}_value_{len(values)}",
                role="value",
                text=text,
                bbox=bbox,
                page=page,
                token_ids=token_ids,
                line_ids=(value_line["line_id"],),
                confidence=confidence,
            )
            values.append(value_node)
            edges.append(
                StructureEdge(
                    edge_id=f"{prefix}_edge_{edge_idx}",
                    source_node_id=label.node_id,
                    target_node_id=value_node.node_id,
                    relation="label_of",
                    confidence=0.84,
                    reason_codes=("paired_label_value_rows", "x_band_alignment"),
                )
            )
            edge_idx += 1

    for idx, label in enumerate(labels):
        if any(edge.source_node_id == label.node_id for edge in edges):
            continue
        lx, _ly = label.center
        candidates: list[tuple[float, dict[str, Any]]] = []
        for line in value_lines:
            if line["line_id"] in used_lines:
                continue
            vx, vy = _center(line["bbox"])
            if vy < label.bbox[1]:
                continue
            x_dist = abs(vx - lx)
            y_dist = max(0.0, line["bbox"][1] - label.bbox[3])
            candidates.append((x_dist + y_dist * 0.35, line))
        if not candidates:
            continue
        _score, value_line = min(candidates, key=lambda item: item[0])
        used_lines.add(value_line["line_id"])
        value_node = StructureNode(
            node_id=f"{prefix}_value_{len(values)}",
            role="value",
            text=value_line["text"],
            bbox=value_line["bbox"],
            page=page,
            token_ids=_line_tokens(tokens, value_line["bbox"]),
            line_ids=(value_line["line_id"],),
            confidence=value_line["confidence"],
        )
        values.append(value_node)
        edges.append(
            StructureEdge(
                edge_id=f"{prefix}_edge_{edge_idx}",
                source_node_id=label.node_id,
                target_node_id=value_node.node_id,
                relation="label_of",
                confidence=0.72,
                reason_codes=("nearest_below", "x_alignment"),
            )
        )
        edge_idx += 1
    return values, edges


def _append_continuation_values(
    *,
    values: list[StructureNode],
    edges: list[StructureEdge],
    value_lines: list[dict[str, Any]],
    tokens: list[OCRToken],
    page: int,
    prefix: str,
) -> None:
    used_line_ids = {line_id for value in values for line_id in value.line_ids}
    edge_idx = len(edges)
    for line in sorted(value_lines, key=lambda item: item["bbox"][1]):
        if line["line_id"] in used_line_ids:
            continue
        best: tuple[float, StructureNode] | None = None
        for value in values:
            if value.bbox[3] > line["bbox"][1]:
                continue
            y_gap = line["bbox"][1] - value.bbox[3]
            max_gap = max(22.0, (value.bbox[3] - value.bbox[1]) * 1.8)
            if y_gap > max_gap:
                continue
            x_overlap = _x_overlap_ratio(value.bbox, line["bbox"])
            value_cx, _value_cy = value.center
            line_cx, _line_cy = _center(line["bbox"])
            x_tolerance = max(value.bbox[2] - value.bbox[0], line["bbox"][2] - line["bbox"][0], 20.0) * 0.65
            if x_overlap < 0.35 and abs(value_cx - line_cx) > x_tolerance:
                continue
            score = y_gap + (1.0 - x_overlap) * 12.0 + abs(value_cx - line_cx) * 0.02
            if best is None or score < best[0]:
                best = (score, value)
        if best is None:
            continue
        _score, previous = best
        node = StructureNode(
            node_id=f"{prefix}_value_{len(values)}",
            role="value",
            text=line["text"],
            bbox=line["bbox"],
            page=page,
            token_ids=_line_tokens(tokens, line["bbox"]),
            line_ids=(line["line_id"],),
            confidence=line["confidence"],
            audit={"continuation_of": previous.node_id},
        )
        values.append(node)
        used_line_ids.add(line["line_id"])
        edges.append(
            StructureEdge(
                edge_id=f"{prefix}_edge_{edge_idx}",
                source_node_id=previous.node_id,
                target_node_id=node.node_id,
                relation="continuation",
                confidence=0.68,
                reason_codes=("same_col_band", "small_y_gap", "no_label_signal"),
            )
        )
        edge_idx += 1


def _prefers_field_grid(
    block_lines: list[dict[str, Any]],
    *,
    is_label_line: Callable[[dict[str, Any]], bool],
) -> bool:
    """Use field_grid for multi-row values or glued labels; keep ideal single-row on graph."""
    from docmirror.core.ocr.field_grid.bands import segment_field_sections

    sections = segment_field_sections(block_lines, is_label_line=is_label_line)
    if not sections:
        return False
    if any(len(section.get("value_lines") or []) > 2 for section in sections):
        return True
    for line in block_lines[1:]:
        if not is_label_line(line):
            continue
        compact = line["text"].replace(" ", "")
        if len(compact) > 12 and sum(1 for _ in _LABEL_SUFFIX_RE.finditer(compact)) >= 2:
            if " " not in line["text"].strip():
                return True
    return False


def build_local_structures(
    lines: Iterable[Any],
    *,
    tokens: Iterable[Any] | None = None,
    page: int,
    candidates: Iterable[LocalStructureCandidate] | None = None,
    page_image: Any | None = None,
    page_width: float | None = None,
    page_height: float | None = None,
    enable_repair: bool = False,
) -> list[LocalStructure]:
    from docmirror.core.ocr.field_grid.bands import align_col_bands_across_structures
    from docmirror.core.ocr.field_grid.build import build_field_grid_from_block
    from docmirror.core.ocr.local_structure.utils import coerce_tokens

    items = line_items(lines, page=page)
    token_list = coerce_tokens(tokens, page=page)
    from docmirror.core.ocr.local_structure.candidate_supplement import supplement_local_structure_candidates
    from docmirror.core.ocr.local_structure.detect import detect_local_structure_candidates
    from docmirror.core.ocr.page_canvas.page_segment import grid_anchor_top_from_lines, is_lattice_content_line

    candidate_list = (
        list(candidates)
        if candidates is not None
        else detect_local_structure_candidates(items, tokens=token_list, page=page)
    )
    candidate_list.extend(
        supplement_local_structure_candidates(
            items,
            tokens=token_list,
            page=page,
            page_width=page_width,
            page_height=page_height,
            existing=candidate_list,
        )
    )
    candidate_list.sort(key=lambda c: (c.bbox[1], c.bbox[0]))
    structures: list[LocalStructure] = []

    for cand_idx, candidate in enumerate(candidate_list):
        cbox = candidate.bbox
        block_lines = [
            line
            for line in items
            if cbox[0] - 1 <= line["bbox"][0]
            and line["bbox"][2] <= cbox[2] + 1
            and cbox[1] - 1 <= line["bbox"][1] <= cbox[3] + 1
        ]
        force_field_grid = any(
            code in (candidate.reason_codes or ())
            for code in (
                "credit_closed_account_block",
                "geometric_field_block_pre_grid",
                "geometric_pre_grid_window",
            )
        )
        if force_field_grid:
            grid_top = grid_anchor_top_from_lines(items)
            if grid_top is not None:
                cutoff = grid_top - 4.0
                block_lines = [
                    line
                    for line in block_lines
                    if float(line["bbox"][3]) <= cutoff and not is_lattice_content_line(str(line.get("text") or ""))
                ]
        if not block_lines:
            continue
        structure_id = f"ls_p{page}_{cand_idx}"
        prefix = structure_id

        field_grid: LocalStructure | None = None
        if ENABLE_FIELD_GRID and (force_field_grid or _prefers_field_grid(block_lines, is_label_line=_is_label_line)):
            field_grid = build_field_grid_from_block(
                block_lines,
                structure_id=structure_id,
                tokens=token_list,
                page=page,
                prefix=prefix,
                anchors=candidate.anchors,
                candidate_id=candidate.candidate_id,
                candidate_score=candidate.score,
                is_label_line=_is_label_line,
                page_image=page_image,
                page_width=page_width,
                page_height=page_height,
                enable_repair=enable_repair,
            )

        if field_grid is not None:
            structures.append(field_grid)
            continue

        structures.append(
            _build_label_value_graph_structure(
                block_lines,
                page=page,
                prefix=prefix,
                structure_id=structure_id,
                candidate=candidate,
                token_list=token_list,
                audit_extra={"fallback_from": "field_grid_failed"},
            )
        )

    if ENABLE_FIELD_GRID and len(structures) > 1:
        dicts = [s.to_dict() for s in structures if s.structure_kind == "field_grid"]
        if dicts:
            align_col_bands_across_structures(dicts)
            by_id = {d["structure_id"]: d for d in dicts}
            rebuilt: list[LocalStructure] = []
            for structure in structures:
                if structure.structure_id in by_id:
                    data = by_id[structure.structure_id]
                    rebuilt.append(
                        LocalStructure(
                            structure_id=structure.structure_id,
                            page=structure.page,
                            bbox=structure.bbox,
                            structure_kind=structure.structure_kind,
                            anchors=structure.anchors,
                            row_bands=tuple(data.get("row_bands") or structure.row_bands),
                            col_bands=tuple(data.get("col_bands") or structure.col_bands),
                            nodes=structure.nodes,
                            edges=structure.edges,
                            cells=structure.cells,
                            confidence=structure.confidence,
                            audit={**structure.audit, "schema_aligned": True},
                        )
                    )
                else:
                    rebuilt.append(structure)
            structures = rebuilt

    return structures


def _build_label_value_graph_structure(
    block_lines: list[dict[str, Any]],
    *,
    page: int,
    prefix: str,
    structure_id: str,
    candidate: LocalStructureCandidate,
    token_list: list[OCRToken],
    audit_extra: dict[str, Any] | None = None,
) -> LocalStructure:
    anchor_line = block_lines[0]
    nodes: list[StructureNode] = [
        StructureNode(
            node_id=f"{prefix}_anchor",
            role="anchor",
            text=anchor_line["text"],
            bbox=anchor_line["bbox"],
            page=page,
            token_ids=_line_tokens(token_list, anchor_line["bbox"]),
            line_ids=(anchor_line["line_id"],),
            confidence=anchor_line["confidence"],
        )
    ]
    label_lines = [line for line in block_lines[1:] if _is_label_line(line)]
    value_lines = [line for line in block_lines[1:] if not _is_label_line(line)]
    labels: list[StructureNode] = []
    label_idx = 0
    for line in label_lines:
        for part_text, part_bbox in _interpolate_segments(line):
            labels.append(
                StructureNode(
                    node_id=f"{prefix}_label_{label_idx}",
                    role="label",
                    text=part_text,
                    bbox=part_bbox,
                    page=page,
                    token_ids=_line_tokens(token_list, part_bbox),
                    line_ids=(line["line_id"],),
                    confidence=line["confidence"],
                )
            )
            label_idx += 1
    values, edges = _nearest_values_for_labels(
        labels=labels, value_lines=value_lines, tokens=token_list, page=page, prefix=prefix
    )
    _append_continuation_values(
        values=values,
        edges=edges,
        value_lines=value_lines,
        tokens=token_list,
        page=page,
        prefix=prefix,
    )
    nodes.extend(labels)
    nodes.extend(values)
    row_bands = tuple(
        {
            "index": idx,
            "bbox": list(line["bbox"]),
            "role": "anchor" if idx == 0 else ("label" if _is_label_line(line) else "value"),
            "source_line_id": line["line_id"],
        }
        for idx, line in enumerate(block_lines)
    )
    col_bands = tuple(
        {
            "index": idx,
            "bbox": list(label.bbox),
            "role": "label_column",
            "label_node_id": label.node_id,
        }
        for idx, label in enumerate(labels)
    )
    audit = {
        "candidate_id": candidate.candidate_id,
        "label_count": len(labels),
        "value_count": len(values),
        "edge_count": len(edges),
        "builder": "label_value_graph",
    }
    if audit_extra:
        audit.update(audit_extra)
    return LocalStructure(
        structure_id=structure_id,
        page=page,
        bbox=union_bbox(line["bbox"] for line in block_lines),
        structure_kind="label_value_graph",
        anchors=candidate.anchors,
        row_bands=row_bands,
        col_bands=col_bands,
        nodes=tuple(nodes),
        edges=tuple(edges),
        confidence=min(candidate.score, 0.9),
        audit=audit,
    )


def extract_local_structure_evidence(
    lines: Iterable[Any],
    *,
    tokens: Iterable[Any] | None = None,
    page: int,
    page_width: float | None = None,
    page_height: float | None = None,
    page_image: Any | None = None,
    enable_region_ocr: bool = False,
) -> dict[str, Any]:
    token_list = list(tokens or [])
    candidates = detect_local_structure_candidates(
        lines,
        tokens=token_list,
        page=page,
        page_width=page_width,
        page_height=page_height,
    )
    structures = build_local_structures(
        lines,
        tokens=token_list,
        page=page,
        candidates=candidates,
        page_image=page_image,
        page_width=page_width,
        page_height=page_height,
        enable_repair=enable_region_ocr,
    )
    structure_dicts = [structure.to_dict() for structure in structures]
    if enable_region_ocr and page_image is not None and page_width and page_height:
        _attach_region_crop_ocr(
            structure_dicts,
            page_image=page_image,
            page_width=float(page_width),
            page_height=float(page_height),
        )
    return {
        "candidates": [candidate.to_dict() for candidate in candidates],
        "structures": structure_dicts,
    }


def _attach_region_crop_ocr(
    structures: list[dict[str, Any]],
    *,
    page_image: Any,
    page_width: float,
    page_height: float,
    max_regions_per_structure: int = 24,
) -> None:
    from docmirror.core.ocr.local_structure.repair import recognize_structure_region_from_image

    for structure in structures:
        attempts = 0
        hits = 0
        skipped = 0
        for node in structure.get("nodes") or []:
            if not isinstance(node, dict) or node.get("role") != "value":
                continue
            if attempts >= max_regions_per_structure:
                skipped += 1
                continue
            bbox = node.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            attempts += 1
            rec = recognize_structure_region_from_image(
                page_image,
                tuple(float(v) for v in bbox),
                page_width=page_width,
                page_height=page_height,
            )
            audit = dict(node.get("audit") or {})
            audit["region_crop_ocr"] = rec.to_dict()
            node["audit"] = audit
            if rec.text:
                hits += 1
        audit = dict(structure.get("audit") or {})
        audit["region_crop_ocr"] = {
            "enabled": True,
            "attempts": attempts,
            "hits": hits,
            "skipped": skipped,
            "max_regions_per_structure": max_regions_per_structure,
            "mode": "audit_only",
        }
        structure["audit"] = audit
