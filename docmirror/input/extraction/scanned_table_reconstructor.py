# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Conservative table reconstruction for OCR-only scanned statement pages."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any

import yaml

from docmirror.models.entities.domain import Block

_NUMBER_RE = re.compile(r"\d[\d,，]*(?:\.\d+)?")
_SHORT_NOISE_RE = re.compile(r"^[A-Za-z0-9]{1,3}$")


@lru_cache(maxsize=1)
def _statement_profile() -> dict[str, Any]:
    """Load the installed plugin-owned scanned statement extraction profile."""
    plugin_root = files("docmirror").joinpath("plugins")
    for plugin_dir in sorted(plugin_root.iterdir(), key=lambda item: item.name):
        manifest_path = plugin_dir.joinpath("plugin.yaml")
        if not plugin_dir.is_dir() or not manifest_path.is_file():
            continue
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        relative_text = str(((manifest.get("resources") or {}).get("scanned_statement_profile")) or "").strip()
        relative_path = PurePosixPath(relative_text)
        if not relative_text or relative_path.is_absolute() or ".." in relative_path.parts:
            continue
        resource_path = plugin_dir.joinpath(*relative_path.parts)
        if resource_path.is_file():
            payload = yaml.safe_load(resource_path.read_text(encoding="utf-8")) or {}
            if isinstance(payload.get("profile"), dict):
                return dict(payload["profile"])
    return {}


@dataclass(frozen=True)
class _Token:
    text: str
    bbox: tuple[float, float, float, float]
    evidence_id: str
    confidence: float

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2.0

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2.0

    @property
    def h(self) -> float:
        return max(1.0, self.bbox[3] - self.bbox[1])


@dataclass
class _Row:
    tokens: list[_Token]

    @property
    def cy(self) -> float:
        return statistics.median(token.cy for token in self.tokens)

    @property
    def h(self) -> float:
        return statistics.median(token.h for token in self.tokens)

    @property
    def text(self) -> str:
        return " ".join(token.text for token in sorted(self.tokens, key=lambda t: t.bbox[0])).strip()


def reconstruct_scanned_statement_table(
    blocks: list[Block],
    *,
    page_number: int,
    page_width: float,
    page_height: float,
    start_order: int = 0,
) -> Block | None:
    """Conservatively build one statement table from strong OCR geometry."""
    if any(block.block_type == "table" for block in blocks):
        return None
    tokens = [_block_to_token(block) for block in blocks]
    tokens = [token for token in tokens if token is not None and _is_useful_token(token)]
    if len(tokens) < 12:
        return None
    profile = _statement_profile()
    keywords = tuple(str(value) for value in profile.get("keywords") or [])
    page_text = " ".join(token.text for token in tokens)
    numeric_count = sum(1 for token in tokens if _looks_numeric(token.text))
    keyword_hits = sum(1 for keyword in keywords if keyword in page_text)
    if keyword_hits == 0 and numeric_count < 12:
        return None

    rows = _cluster_rows(tokens)
    header_index = _find_header_row(rows, profile)
    if header_index is None:
        return None
    table_rows = _trim_table_rows(rows[header_index:], keywords)
    if len(table_rows) < 4:
        return None

    header_tokens = _normalize_header_tokens(table_rows[0].tokens, profile)
    anchors = _column_anchors(header_tokens, tokens)
    if len(anchors) < 3:
        return None

    raw, cell_bboxes, cell_evidence_ids, cell_confidences = _materialize_rows(table_rows, anchors)
    if len(raw) < 4 or max((len(row) for row in raw), default=0) < 3:
        return None
    if _non_empty_cells(raw[1:]) < 8:
        return None

    correction_mode = _ocr_correction_mode(blocks)
    correction_scope = _ocr_correction_scope(blocks)
    raw, correction_events, correction_processed_count = _correct_table_grid(
        raw,
        cell_evidence_ids=cell_evidence_ids,
        cell_confidences=cell_confidences,
        domain=str(profile.get("correction_domain") or "") or None,
        first_column_role=str(profile.get("first_column_role") or "") or None,
        mode=correction_mode,
        **correction_scope,
        page_number=page_number,
        table_index=0,
    )
    owned_ids = {eid for row in cell_evidence_ids for cell in row for eid in cell}
    correction_events = [*_source_correction_events(blocks, owned_ids), *correction_events]

    bbox = _union_bbox([token.bbox for row in table_rows for token in row.tokens])
    geometry = {
        "geometry_source": "scanned_ocr_statement_grid",
        "geometry_confidence": _grid_confidence(raw, keyword_hits=keyword_hits),
        "coordinate_system": "pdf_points_top_left",
        "cell_bboxes": cell_bboxes,
        "cell_geometry_status": [["exact" if cell else "missing" for cell in row] for row in raw],
        "cell_geometry_loss_reason": [[None if cell else "empty_ocr_cell" for cell in row] for row in raw],
        "cell_evidence_ids": cell_evidence_ids,
        "cell_token_ids": cell_evidence_ids,
        "cell_confidences": cell_confidences,
        "row_bands": _row_bands(table_rows),
        "col_bands": _col_bands(anchors, bbox),
    }
    orientation_attrs = _ocr_orientation_attrs(blocks)
    block_id = f"scanned_table:p{page_number:04d}:0000"
    return Block(
        block_id=block_id,
        block_type="table",
        bbox=bbox,
        reading_order=start_order,
        page=page_number,
        raw_content=raw,
        attrs={
            "extraction_layer": "scanned_ocr_statement_grid",
            "extraction_confidence": geometry["geometry_confidence"],
            "geometry": geometry,
            "role": str(profile.get("role") or "statement"),
            "preserve_headers": True,
            "statement_keywords": [kw for kw in keywords if kw in page_text],
            "source": "scanned_table_reconstructor",
            "ocr_correction_mode": correction_mode,
            "ocr_correction_processed_count": correction_processed_count,
            **({"ocr_corrections": correction_events} if correction_events else {}),
            "page_width": page_width,
            "page_height": page_height,
            **orientation_attrs,
        },
        evidence_ids=tuple(sorted({eid for row in cell_evidence_ids for cell in row for eid in cell})),
    )


def reconstruct_scanned_bordered_tables(
    page_image: Any,
    blocks: list[Block],
    *,
    page_number: int,
    page_width: float,
    page_height: float,
    start_order: int = 0,
) -> list[Block]:
    """Reconstruct physical bordered tables without assigning business meaning."""
    if page_image is None or getattr(page_image, "size", 0) == 0:
        return []
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []

    image = page_image
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if len(image.shape) == 3 else image
    height_px, width_px = gray.shape[:2]
    if width_px < 80 or height_px < 80 or page_width <= 0 or page_height <= 0:
        return []
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        11,
    )
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(18, width_px // 28), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(18, height_px // 36)))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
    line_mask = cv2.dilate(cv2.bitwise_or(horizontal, vertical), np.ones((3, 3), np.uint8), iterations=1)

    contours, _hierarchy = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width < width_px * 0.22 or height < height_px * 0.035:
            continue
        if width * height < width_px * height_px * 0.012:
            continue
        candidates.append((x, y, x + width, y + height))
    candidates = _merge_nested_table_candidates(candidates)

    sx = page_width / float(width_px)
    sy = page_height / float(height_px)
    tokens = [token for block in blocks if (token := _block_to_token(block)) is not None]
    out: list[Block] = []
    for table_index, pixel_bbox in enumerate(sorted(candidates, key=lambda value: (value[1], value[0]))):
        original_x0 = pixel_bbox[0]
        pixel_bbox = _extend_open_left_candidate(pixel_bbox, tokens, sx=sx, sy=sy, width_px=width_px)
        open_left_column = pixel_bbox[0] < original_x0 - 3
        x0, y0, x1, y1 = pixel_bbox
        x_lines = _projection_line_positions(vertical[y0:y1, x0:x1], axis=0, offset=x0)
        y_lines = _projection_line_positions(horizontal[y0:y1, original_x0:x1], axis=1, offset=y0)
        x_lines = _ensure_outer_lines(x_lines, x0, x1)
        y_lines = _ensure_outer_lines(y_lines, y0, y1)
        if len(x_lines) < 3 or len(y_lines) < 3:
            continue
        if len(x_lines) - 1 < 2 or len(y_lines) - 1 < 2:
            continue

        groups, merge_diagnostics = _merged_cell_groups(
            horizontal,
            vertical,
            x_lines,
            y_lines,
            preserve_left_column_rows=open_left_column,
        )
        grid_rows = len(y_lines) - 1
        grid_cols = len(x_lines) - 1
        group_tokens: dict[int, list[_Token]] = {index: [] for index in range(len(groups))}
        numeric_columns_by_row: dict[int, set[int]] = {index: set() for index in range(grid_rows)}
        table_bbox_points = (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
        for token in tokens:
            if not _center_in_bbox(token.cx, token.cy, table_bbox_points):
                continue
            row_index = _band_index(token.cy / sy, y_lines)
            col_index = _band_index(token.cx / sx, x_lines)
            if row_index is None or col_index is None:
                continue
            group_index = next(
                (idx for idx, cells in enumerate(groups) if (row_index, col_index) in cells),
                None,
            )
            if group_index is not None:
                group_tokens[group_index].append(token)
                if _looks_numeric(token.text):
                    numeric_columns_by_row[row_index].add(col_index)

        raw = [["" for _col in range(grid_cols)] for _row in range(grid_rows)]
        cell_bboxes: list[list[list[float] | None]] = [[None for _col in range(grid_cols)] for _row in range(grid_rows)]
        cell_evidence_ids: list[list[list[str]]] = [[[] for _col in range(grid_cols)] for _row in range(grid_rows)]
        cell_confidences: list[list[float | None]] = [[None for _col in range(grid_cols)] for _row in range(grid_rows)]
        cell_geometry_status = [["derived" for _col in range(grid_cols)] for _row in range(grid_rows)]
        cell_geometry_loss_reason: list[list[str | None]] = [
            ["covered_by_merged_cell" for _col in range(grid_cols)] for _row in range(grid_rows)
        ]
        cell_spans: list[dict[str, Any]] = []
        owned_ids: set[str] = set()
        token_split_vertical_merge_count = 0
        for group_index, cells in enumerate(groups):
            rows = sorted({cell[0] for cell in cells})
            cols = sorted({cell[1] for cell in cells})
            anchor_row, anchor_col = rows[0], cols[0]
            bbox = [
                round(x_lines[anchor_col] * sx, 4),
                round(y_lines[anchor_row] * sy, 4),
                round(x_lines[cols[-1] + 1] * sx, 4),
                round(y_lines[rows[-1] + 1] * sy, 4),
            ]
            assigned = sorted(group_tokens[group_index], key=lambda token: (token.cy, token.cx))
            row_buckets: dict[int, list[_Token]] = {row: [] for row in rows}
            for token in assigned:
                token_row = _band_index(token.cy / sy, y_lines)
                if token_row in row_buckets:
                    row_buckets[token_row].append(token)
            populated_buckets = [bucket for bucket in row_buckets.values() if bucket]
            populated_rows = [row for row, bucket in row_buckets.items() if bucket]
            numeric_rows_in_group = [
                row for row, bucket in row_buckets.items() if any(_looks_numeric(token.text) for token in bucket)
            ]
            aligned_numeric_rows = [
                row for row in populated_rows if numeric_columns_by_row.get(row, set()).difference(cols)
            ]
            numeric_rows_aligned_elsewhere = set(numeric_rows_in_group).intersection(aligned_numeric_rows)
            split_vertical_merge = bool(
                len(rows) > 1
                and len(cols) == 1
                and len(populated_buckets) >= 2
                and (
                    len(numeric_rows_in_group) >= 2
                    or len(aligned_numeric_rows) >= 2
                    or bool(numeric_rows_aligned_elsewhere)
                )
            )
            if split_vertical_merge:
                token_split_vertical_merge_count += 1
                for row, bucket in row_buckets.items():
                    if not bucket:
                        continue
                    bucket = sorted(bucket, key=lambda token: token.cx)
                    bucket_evidence_ids = [token.evidence_id for token in bucket]
                    bucket_confidence = sum(token.confidence * max(1, len(token.text)) for token in bucket) / sum(
                        max(1, len(token.text)) for token in bucket
                    )
                    raw[row][anchor_col] = " ".join(token.text for token in bucket).strip()
                    cell_bboxes[row][anchor_col] = [
                        round(x_lines[anchor_col] * sx, 4),
                        round(y_lines[row] * sy, 4),
                        round(x_lines[anchor_col + 1] * sx, 4),
                        round(y_lines[row + 1] * sy, 4),
                    ]
                    cell_evidence_ids[row][anchor_col] = bucket_evidence_ids
                    cell_confidences[row][anchor_col] = round(float(bucket_confidence), 4)
                    cell_geometry_status[row][anchor_col] = "exact"
                    cell_geometry_loss_reason[row][anchor_col] = None
                    owned_ids.update(bucket_evidence_ids)
                continue
            text = " ".join(token.text for token in assigned).strip()
            evidence_ids = [token.evidence_id for token in assigned]
            confidence = (
                sum(token.confidence * max(1, len(token.text)) for token in assigned)
                / sum(max(1, len(token.text)) for token in assigned)
                if assigned
                else None
            )
            raw[anchor_row][anchor_col] = text
            cell_bboxes[anchor_row][anchor_col] = bbox
            cell_evidence_ids[anchor_row][anchor_col] = evidence_ids
            cell_confidences[anchor_row][anchor_col] = round(float(confidence), 4) if confidence is not None else None
            cell_geometry_status[anchor_row][anchor_col] = "exact"
            cell_geometry_loss_reason[anchor_row][anchor_col] = None
            owned_ids.update(evidence_ids)
            if len(rows) > 1 or len(cols) > 1:
                cell_spans.append(
                    {
                        "row": anchor_row,
                        "col": anchor_col,
                        "row_span": len(rows),
                        "col_span": len(cols),
                        "bbox": bbox,
                        "evidence_ids": evidence_ids,
                    }
                )
        merge_diagnostics["token_split_vertical_merge_count"] = token_split_vertical_merge_count

        non_empty = sum(1 for row in raw for value in row if value.strip())
        if non_empty < 3:
            continue
        correction_mode = _ocr_correction_mode(blocks)
        correction_scope = _ocr_correction_scope(blocks)
        page_text = " ".join(str(block.raw_content or "") for block in blocks)
        correction_domain, first_column_role = _infer_correction_policy(page_text)
        raw, correction_events, correction_processed_count = _correct_table_grid(
            raw,
            cell_evidence_ids=cell_evidence_ids,
            cell_confidences=cell_confidences,
            domain=correction_domain,
            first_column_role=first_column_role,
            mode=correction_mode,
            **correction_scope,
            page_number=page_number,
            table_index=table_index,
        )
        correction_events = [*_source_correction_events(blocks, owned_ids), *correction_events]
        h_strength = _line_projection_strength(horizontal, x0, y0, x1, y1, axis=1, positions=y_lines)
        v_strength = _line_projection_strength(vertical, x0, y0, x1, y1, axis=0, positions=x_lines)
        assignment_ratio = len(owned_ids) / max(
            1, sum(1 for token in tokens if _center_in_bbox(token.cx, token.cy, table_bbox_points))
        )
        geometry_confidence = round(
            max(0.0, min(1.0, 0.45 * h_strength + 0.45 * v_strength + 0.10 * assignment_ratio)), 4
        )
        bbox_points = tuple(round(value, 4) for value in table_bbox_points)
        out.append(
            Block(
                block_id=f"scanned_grid:p{page_number:04d}:{table_index:04d}",
                block_type="table",
                bbox=bbox_points,
                reading_order=start_order + table_index,
                page=page_number,
                raw_content=raw,
                attrs={
                    "extraction_layer": "scanned_image_line_grid",
                    "extraction_confidence": geometry_confidence,
                    "confidence": geometry_confidence,
                    "geometry": {
                        "geometry_source": "scanned_image_line_grid",
                        "geometry_confidence": geometry_confidence,
                        "coordinate_system": "pdf_points_top_left",
                        "cell_bboxes": cell_bboxes,
                        "cell_geometry_status": cell_geometry_status,
                        "cell_geometry_loss_reason": cell_geometry_loss_reason,
                        "cell_evidence_ids": cell_evidence_ids,
                        "cell_token_ids": cell_evidence_ids,
                        "cell_confidences": cell_confidences,
                        "cell_spans": cell_spans,
                        "row_bands": [
                            {
                                "index": index,
                                "y0": round(y_lines[index] * sy, 4),
                                "y1": round(y_lines[index + 1] * sy, 4),
                            }
                            for index in range(grid_rows)
                        ],
                        "col_bands": [
                            {
                                "index": index,
                                "x0": round(x_lines[index] * sx, 4),
                                "x1": round(x_lines[index + 1] * sx, 4),
                            }
                            for index in range(grid_cols)
                        ],
                        "horizontal_lines": [round(value * sy, 4) for value in y_lines],
                        "vertical_lines": [round(value * sx, 4) for value in x_lines],
                        "merge_diagnostics": merge_diagnostics,
                    },
                    "role": "physical_table",
                    "preserve_headers": False,
                    "source": "scanned_bordered_table_reconstructor",
                    "ocr_correction_mode": correction_mode,
                    "ocr_correction_processed_count": correction_processed_count,
                    **({"ocr_corrections": correction_events} if correction_events else {}),
                    "page_width": page_width,
                    "page_height": page_height,
                },
                evidence_ids=tuple(sorted(owned_ids)),
            )
        )
    return out


def _merge_nested_table_candidates(candidates: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    ordered = sorted(candidates, key=lambda value: (-(value[2] - value[0]) * (value[3] - value[1]), value[1]))
    kept: list[tuple[int, int, int, int]] = []
    for candidate in ordered:
        if any(
            outer[0] <= candidate[0]
            and outer[1] <= candidate[1]
            and outer[2] >= candidate[2]
            and outer[3] >= candidate[3]
            for outer in kept
        ):
            continue
        kept.append(candidate)
    return kept


def _extend_open_left_candidate(
    candidate: tuple[int, int, int, int],
    tokens: list[_Token],
    *,
    sx: float,
    sy: float,
    width_px: int,
) -> tuple[int, int, int, int]:
    """Include an unruled first label column adjacent to a detected numeric grid."""
    x0, y0, x1, y1 = candidate
    x0_points, y0_points, y1_points = x0 * sx, y0 * sy, y1 * sy
    max_extension = min(110.0, width_px * sx * 0.18)
    left_tokens = [
        token
        for token in tokens
        if x0_points - max_extension <= token.cx < x0_points and y0_points <= token.cy <= y1_points
    ]
    has_project_header = any(re.sub(r"\s+", "", token.text) in {"项", "目", "项目"} for token in left_tokens)
    row_centers = {int(round(token.cy / max(3.0, token.h))) for token in left_tokens}
    if not has_project_header or len(left_tokens) < 2 or len(row_centers) < 2:
        return candidate
    extended_x0 = max(0, int((min(token.bbox[0] for token in left_tokens) - 2.0) / sx))
    return (extended_x0, y0, x1, y1)


def _projection_line_positions(mask: Any, *, axis: int, offset: int) -> list[int]:
    import numpy as np

    projection = (mask > 0).mean(axis=axis)
    peak = float(projection.max()) if projection.size else 0.0
    threshold = max(0.16, min(0.35, peak * 0.68))
    indices = np.where(projection >= threshold)[0].tolist()
    groups: list[list[int]] = []
    for index in indices:
        if not groups or index - groups[-1][-1] > 3:
            groups.append([index])
        else:
            groups[-1].append(index)
    return [offset + int(round(sum(group) / len(group))) for group in groups]


def _ensure_outer_lines(lines: list[int], start: int, end: int) -> list[int]:
    """Deduplicate detected rules and restore open table outer boundaries."""
    result = sorted({int(value) for value in lines if start <= int(value) <= end})
    if not result:
        return [start, end] if end - start >= 12 else []
    if result[0] - start >= 6:
        result.insert(0, start)
    else:
        result[0] = start
    if end - result[-1] >= 6:
        result.append(end)
    else:
        result[-1] = end
    return [value for index, value in enumerate(result) if index == 0 or value - result[index - 1] >= 6]


def _merged_cell_groups(
    horizontal: Any,
    vertical: Any,
    x_lines: list[int],
    y_lines: list[int],
    *,
    preserve_left_column_rows: bool = False,
) -> tuple[list[set[tuple[int, int]]], dict[str, int]]:
    """Return rectangular merged-cell groups validated against original masks."""
    rows, cols = len(y_lines) - 1, len(x_lines) - 1
    parent = list(range(rows * cols))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for row in range(rows):
        for col in range(cols - 1):
            x = x_lines[col + 1]
            y0, y1 = y_lines[row], y_lines[row + 1]
            pad = max(1, int((y1 - y0) * 0.12))
            strength = float((vertical[y0 + pad : max(y0 + pad + 1, y1 - pad), max(0, x - 1) : x + 2] > 0).mean())
            if strength < 0.30:
                union(row * cols + col, row * cols + col + 1)
    for row in range(rows - 1):
        for col in range(cols):
            if preserve_left_column_rows and col == 0:
                continue
            y = y_lines[row + 1]
            x0, x1 = x_lines[col], x_lines[col + 1]
            pad = max(1, int((x1 - x0) * 0.08))
            strength = float((horizontal[max(0, y - 1) : y + 2, x0 + pad : max(x0 + pad + 1, x1 - pad)] > 0).mean())
            if strength < 0.30:
                union(row * cols + col, (row + 1) * cols + col)

    candidates: dict[int, set[tuple[int, int]]] = {}
    for row in range(rows):
        for col in range(cols):
            candidates.setdefault(find(row * cols + col), set()).add((row, col))

    accepted: list[set[tuple[int, int]]] = []
    diagnostics = {
        "merge_candidate_count": 0,
        "accepted_merge_count": 0,
        "rejected_non_rectangular_count": 0,
        "rejected_internal_divider_count": 0,
        "rejected_full_table_count": 0,
        "fallback_unit_cell_count": 0,
    }
    for cells in candidates.values():
        if len(cells) == 1:
            accepted.append(cells)
            continue
        diagnostics["merge_candidate_count"] += 1
        row_values = sorted({row for row, _col in cells})
        col_values = sorted({col for _row, col in cells})
        rectangle = {(row, col) for row in row_values for col in col_values}
        if cells != rectangle:
            diagnostics["rejected_non_rectangular_count"] += 1
            accepted.extend({cell} for cell in sorted(cells))
            diagnostics["fallback_unit_cell_count"] += len(cells)
            continue
        if len(cells) == rows * cols and rows > 1 and cols > 1:
            diagnostics["rejected_full_table_count"] += 1
            accepted.extend({cell} for cell in sorted(cells))
            diagnostics["fallback_unit_cell_count"] += len(cells)
            continue
        if _merged_rectangle_has_internal_divider(
            horizontal,
            vertical,
            x_lines,
            y_lines,
            row_values=row_values,
            col_values=col_values,
        ):
            diagnostics["rejected_internal_divider_count"] += 1
            accepted.extend({cell} for cell in sorted(cells))
            diagnostics["fallback_unit_cell_count"] += len(cells)
            continue
        accepted.append(cells)
        diagnostics["accepted_merge_count"] += 1
    return accepted, diagnostics


def _merged_rectangle_has_internal_divider(
    horizontal: Any,
    vertical: Any,
    x_lines: list[int],
    y_lines: list[int],
    *,
    row_values: list[int],
    col_values: list[int],
) -> bool:
    """Whether a candidate rectangle still contains a material internal rule."""
    for col in range(col_values[0] + 1, col_values[-1] + 1):
        x = x_lines[col]
        for row in row_values:
            y0, y1 = y_lines[row], y_lines[row + 1]
            pad = max(1, int((y1 - y0) * 0.12))
            segment = vertical[y0 + pad : max(y0 + pad + 1, y1 - pad), max(0, x - 1) : x + 2]
            if segment.size and float((segment > 0).mean()) >= 0.30:
                return True
    for row in range(row_values[0] + 1, row_values[-1] + 1):
        y = y_lines[row]
        for col in col_values:
            x0, x1 = x_lines[col], x_lines[col + 1]
            pad = max(1, int((x1 - x0) * 0.08))
            segment = horizontal[max(0, y - 1) : y + 2, x0 + pad : max(x0 + pad + 1, x1 - pad)]
            if segment.size and float((segment > 0).mean()) >= 0.30:
                return True
    return False


def _center_in_bbox(x: float, y: float, bbox: tuple[float, float, float, float]) -> bool:
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def _band_index(value: float, lines: list[int]) -> int | None:
    for index, (start, end) in enumerate(zip(lines, lines[1:], strict=False)):
        if start <= value <= end:
            return index
    return None


def _line_projection_strength(
    mask: Any,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    *,
    axis: int,
    positions: list[int],
) -> float:
    values: list[float] = []
    for position in positions:
        if axis == 1:
            values.append(float((mask[max(0, position - 1) : position + 2, x0:x1] > 0).mean()))
        else:
            values.append(float((mask[y0:y1, max(0, position - 1) : position + 2] > 0).mean()))
    return sum(values) / len(values) if values else 0.0


def _block_to_token(block: Block) -> _Token | None:
    text = str(block.raw_content or "").strip()
    if not text:
        return None
    bbox = tuple(float(v) for v in (block.bbox or (0.0, 0.0, 0.0, 0.0)))
    if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    confidence = float((block.attrs or {}).get("confidence") or 1.0)
    evidence_ids = list(block.evidence_ids or ())
    return _Token(
        text=text, bbox=bbox, evidence_id=evidence_ids[0] if evidence_ids else block.block_id, confidence=confidence
    )


def _ocr_correction_mode(blocks: list[Block]) -> str:
    for block in blocks:
        mode = str((block.attrs or {}).get("ocr_correction_mode") or "")
        if mode in {"off", "safe", "suggest"}:
            return mode
    return "safe"


def _ocr_correction_scope(blocks: list[Block]) -> dict[str, Any]:
    for block in blocks:
        attrs = block.attrs or {}
        if attrs.get("ocr_correction_processed"):
            return {
                "language": str(attrs.get("ocr_correction_language") or "") or None,
                "country": str(attrs.get("ocr_correction_country") or "") or None,
                "locale": str(attrs.get("ocr_correction_locale") or "") or None,
                "pack_ids": tuple(str(value) for value in attrs.get("ocr_correction_pack_ids") or []),
            }
    return {"language": None, "country": None, "locale": None, "pack_ids": ()}


def _infer_correction_policy(text: str) -> tuple[str | None, str | None]:
    from docmirror.configs.scene.loader import get_scene_aliases, get_scene_evidence_specs
    from docmirror.layout.scene.scene_resolver import resolve_document_scene

    resolution = resolve_document_scene(str(text or ""))
    if resolution.scene in {"unknown", "generic"}:
        return None, None
    spec = get_scene_evidence_specs().get(resolution.scene) or {}
    domain = str(spec.get("ocr_domain") or get_scene_aliases().get(resolution.scene, resolution.scene))
    first_column_role = str(spec.get("ocr_first_column_role") or "") or None
    return domain or None, first_column_role


def _correct_table_grid(
    raw: list[list[str]],
    *,
    cell_evidence_ids: list[list[list[str]]],
    cell_confidences: list[list[float | None]],
    domain: str | None,
    first_column_role: str | None,
    mode: str,
    language: str | None,
    country: str | None,
    locale: str | None,
    pack_ids: tuple[str, ...],
    page_number: int,
    table_index: int,
) -> tuple[list[list[str]], list[dict[str, Any]], int]:
    from docmirror.ocr.correction import CorrectionContext, SafeOCRCorrector

    if not raw:
        return raw, [], 0
    corrector = SafeOCRCorrector()
    headers = [str(value or "") for value in raw[0]]
    out = [list(row) for row in raw]
    events: list[dict[str, Any]] = []
    processed_count = 0
    for row_index, row in enumerate(out):
        for col_index, value in enumerate(row):
            text = str(value or "").strip()
            if not text:
                continue
            role = _table_cell_role(
                row_index=row_index,
                col_index=col_index,
                headers=headers,
                first_column_role=first_column_role,
            )
            if role == "data":
                continue
            processed_count += 1
            evidence_ids = (
                cell_evidence_ids[row_index][col_index]
                if row_index < len(cell_evidence_ids) and col_index < len(cell_evidence_ids[row_index])
                else []
            )
            confidence = (
                cell_confidences[row_index][col_index]
                if row_index < len(cell_confidences) and col_index < len(cell_confidences[row_index])
                else None
            )
            source_ref = (
                evidence_ids[0] if evidence_ids else f"table:p{page_number}:t{table_index}:r{row_index}:c{col_index}"
            )
            decision = corrector.correct(
                text,
                CorrectionContext(
                    role=role,
                    domain=domain,
                    source_ref=source_ref,
                    ocr_confidence=confidence,
                    mode=mode if mode in {"off", "safe", "suggest"} else "safe",
                    language=language,
                    country=country,
                    locale=locale,
                    pack_ids=pack_ids,
                    metadata={"field_type": role if role in {"date", "amount"} else ""},
                ),
            )
            row[col_index] = decision.output_text
            if decision.action != "unchanged":
                event = decision.to_dict()
                event["target"] = {
                    "kind": "table_cell",
                    "page": page_number,
                    "table": table_index,
                    "row": row_index,
                    "column": col_index,
                }
                events.append(event)
    return out, events, processed_count


def _table_cell_role(
    *,
    row_index: int,
    col_index: int,
    headers: list[str],
    first_column_role: str | None,
) -> str:
    if row_index == 0:
        return "table_header"
    if col_index == 0 and first_column_role:
        return first_column_role
    header = headers[col_index] if col_index < len(headers) else ""
    if re.search(r"日期|时间|期限|年月日", header):
        return "date"
    if re.search(r"金额|余额|价款|合计|总计|收入|支出|借方|贷方", header):
        return "amount"
    if re.search(r"代码|编号|证号|税号|账号|卡号", header):
        return "code"
    return "data"


def _source_correction_events(blocks: list[Block], owned_ids: set[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in blocks:
        if not (_block_evidence_ids(block) & owned_ids):
            continue
        event = (block.attrs or {}).get("ocr_correction")
        if isinstance(event, dict):
            events.append(dict(event))
    return events


def _block_evidence_ids(block: Block) -> set[str]:
    return set(block.evidence_ids or ()) or ({block.block_id} if block.block_id else set())


def _ocr_orientation_attrs(blocks: list[Block]) -> dict[str, Any]:
    """Summarize page-level OCR orientation metadata from source token blocks."""
    rotations: dict[int, int] = {}
    scores: list[float] = []
    normalized_width: float | None = None
    normalized_height: float | None = None
    for block in blocks:
        attrs = block.attrs or {}
        if "ocr_rotation" in attrs:
            try:
                rotation = int(attrs["ocr_rotation"]) % 360
            except (TypeError, ValueError):
                rotation = 0
            rotations[rotation] = rotations.get(rotation, 0) + 1
        if attrs.get("ocr_orientation_score") is not None:
            try:
                scores.append(float(attrs["ocr_orientation_score"]))
            except (TypeError, ValueError):
                pass
        if normalized_width is None and attrs.get("normalized_page_width") is not None:
            try:
                normalized_width = float(attrs["normalized_page_width"])
            except (TypeError, ValueError):
                normalized_width = None
        if normalized_height is None and attrs.get("normalized_page_height") is not None:
            try:
                normalized_height = float(attrs["normalized_page_height"])
            except (TypeError, ValueError):
                normalized_height = None

    out: dict[str, Any] = {}
    if rotations:
        out["ocr_rotation"] = max(rotations.items(), key=lambda item: (item[1], -item[0]))[0]
    if scores:
        out["ocr_orientation_score"] = max(scores)
    if normalized_width is not None:
        out["normalized_page_width"] = normalized_width
    if normalized_height is not None:
        out["normalized_page_height"] = normalized_height
    return out


def _is_useful_token(token: _Token) -> bool:
    text = token.text.strip()
    if not text:
        return False
    noise_text = {str(value) for value in _statement_profile().get("noise_text") or []}
    if text in noise_text:
        return False
    if len(text) == 1 and not text.isdigit() and text not in {"项", "目"}:
        return False
    return True


def _looks_numeric(text: str) -> bool:
    return bool(_NUMBER_RE.search(text.replace("，", ",")))


def _cluster_rows(tokens: list[_Token]) -> list[_Row]:
    rows: list[_Row] = []
    for token in sorted(tokens, key=lambda item: (item.cy, item.bbox[0])):
        placed = False
        for row in rows[-5:]:
            tolerance = max(4.0, min(12.0, max(row.h, token.h) * 0.65))
            if abs(token.cy - row.cy) <= tolerance:
                row.tokens.append(token)
                placed = True
                break
        if not placed:
            rows.append(_Row(tokens=[token]))
    for row in rows:
        row.tokens.sort(key=lambda item: item.bbox[0])
    return rows


def _find_header_row(rows: list[_Row], profile: dict[str, Any]) -> int | None:
    primary = tuple(str(value) for value in profile.get("primary_header_labels") or [])
    secondary = tuple(str(value) for value in profile.get("secondary_header_labels") or [])
    split_label = tuple(str(value) for value in profile.get("split_header_label") or [])
    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(rows[:16]):
        text = row.text
        score = 0
        if any(label in text for label in primary):
            score += 4
        if any(label in text for label in secondary):
            score += 2
        if split_label and all(label in text for label in split_label):
            score += 2
        if len(row.tokens) >= 3:
            score += 1
        if score > best_score:
            best_score = score
            best_index = index
    return best_index if best_score >= 4 else None


def _trim_table_rows(rows: list[_Row], keywords: tuple[str, ...]) -> list[_Row]:
    trimmed: list[_Row] = []
    blankish_streak = 0
    for row in rows:
        text = row.text
        has_signal = (
            len(row.tokens) >= 2
            or _looks_numeric(text)
            or any(keyword in text for keyword in keywords)
            or any(_is_cjk(char) for char in text)
        )
        if has_signal:
            blankish_streak = 0
            trimmed.append(row)
            continue
        blankish_streak += 1
        if blankish_streak >= 3 and len(trimmed) >= 4:
            break
        trimmed.append(row)
    return trimmed


def _normalize_header_tokens(tokens: list[_Token], profile: dict[str, Any]) -> list[_Token]:
    noise_text = {str(value) for value in profile.get("noise_text") or []}
    header_labels = {str(value) for value in profile.get("header_labels") or []}
    split_label = tuple(str(value) for value in profile.get("split_header_label") or [])
    merged_label = str(profile.get("merged_header_label") or "")
    useful = [token for token in tokens if token.text not in noise_text]
    out: list[_Token] = []
    i = 0
    while i < len(useful):
        token = useful[i]
        if (
            len(split_label) == 2
            and token.text == split_label[0]
            and i + 1 < len(useful)
            and useful[i + 1].text == split_label[1]
        ):
            nxt = useful[i + 1]
            out.append(
                _Token(
                    text=merged_label,
                    bbox=_union_bbox([token.bbox, nxt.bbox]),
                    evidence_id=f"{token.evidence_id}|{nxt.evidence_id}",
                    confidence=min(token.confidence, nxt.confidence),
                )
            )
            i += 2
            continue
        if token.text in split_label:
            out.append(
                _Token(
                    text=merged_label,
                    bbox=token.bbox,
                    evidence_id=token.evidence_id,
                    confidence=token.confidence,
                )
            )
            i += 1
            continue
        out.append(token)
        i += 1
    return [token for token in out if token.text in header_labels or not _SHORT_NOISE_RE.fullmatch(token.text)]


def _column_anchors(header_tokens: list[_Token], all_tokens: list[_Token]) -> list[tuple[float, str]]:
    anchors = [(token.cx, token.text) for token in header_tokens if token.text.strip()]
    noise_text = {str(value) for value in _statement_profile().get("noise_text") or []}
    anchors = [(x, text) for x, text in anchors if text not in noise_text]
    if len(anchors) >= 3:
        return sorted(anchors, key=lambda item: item[0])
    xs = sorted(token.cx for token in all_tokens)
    if len(xs) < 12:
        return []
    clusters: list[list[float]] = [[xs[0]]]
    gaps = [b - a for a, b in zip(xs, xs[1:]) if b > a]
    median_gap = statistics.median(gaps) if gaps else 16.0
    threshold = max(36.0, median_gap * 3.0)
    for x in xs[1:]:
        if x - clusters[-1][-1] > threshold:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    centers = [statistics.median(cluster) for cluster in clusters if len(cluster) >= 2]
    return [(center, f"col_{index + 1}") for index, center in enumerate(centers)]


def _materialize_rows(
    rows: list[_Row],
    anchors: list[tuple[float, str]],
) -> tuple[list[list[str]], list[list[list[float] | None]], list[list[list[str]]], list[list[float | None]]]:
    centers = [x for x, _label in anchors]
    labels = [label for _x, label in anchors]
    col_count = len(centers)
    raw: list[list[str]] = []
    bboxes: list[list[list[float] | None]] = []
    evidence_ids: list[list[list[str]]] = []
    confidences: list[list[float | None]] = []
    for row_index, row in enumerate(rows):
        buckets: list[list[_Token]] = [[] for _ in range(col_count)]
        for token in row.tokens:
            col_index = _nearest_column(token.cx, centers)
            buckets[col_index].append(token)
        if row_index == 0:
            texts = labels
        else:
            texts = [_join_cell_tokens(bucket) for bucket in buckets]
        raw.append(texts)
        bboxes.append([_union_bbox([token.bbox for token in bucket]) if bucket else None for bucket in buckets])
        evidence_ids.append(
            [[part for token in bucket for part in token.evidence_id.split("|") if part] for bucket in buckets]
        )
        confidences.append(
            [
                round(sum(token.confidence for token in bucket) / len(bucket), 4) if bucket else None
                for bucket in buckets
            ]
        )
    return raw, bboxes, evidence_ids, confidences


def _nearest_column(x: float, centers: list[float]) -> int:
    return min(range(len(centers)), key=lambda index: abs(x - centers[index]))


def _join_cell_tokens(tokens: list[_Token]) -> str:
    parts = [token.text for token in sorted(tokens, key=lambda item: item.bbox[0])]
    text = ""
    for part in parts:
        if not text:
            text = part
            continue
        if text[-1].isdigit() and part[0].isdigit():
            text += part
        elif _is_cjk(text[-1]) or _is_cjk(part[0]):
            text += part
        else:
            text += " " + part
    return text.strip()


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _non_empty_cells(rows: list[list[str]]) -> int:
    return sum(1 for row in rows for cell in row if str(cell or "").strip())


def _grid_confidence(raw: list[list[str]], *, keyword_hits: int) -> float:
    populated = _non_empty_cells(raw)
    total = sum(len(row) for row in raw) or 1
    density = populated / total
    numeric_rows = sum(1 for row in raw[1:] if any(_looks_numeric(cell) for cell in row))
    score = 0.55 + min(0.2, density * 0.2) + min(0.15, numeric_rows / max(1, len(raw) - 1) * 0.15)
    if keyword_hits:
        score += 0.08
    return round(min(0.92, score), 4)


def _row_bands(rows: list[_Row]) -> list[dict[str, Any]]:
    bands: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        bbox = _union_bbox([token.bbox for token in row.tokens])
        bands.append({"index": index, "bbox": list(bbox), "y0": bbox[1], "y1": bbox[3]})
    return bands


def _col_bands(anchors: list[tuple[float, str]], table_bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    centers = [x for x, _label in anchors]
    labels = [label for _x, label in anchors]
    dividers = [table_bbox[0]]
    for left, right in zip(centers, centers[1:]):
        dividers.append((left + right) / 2.0)
    dividers.append(table_bbox[2])
    return [
        {
            "index": index,
            "header": labels[index],
            "bbox": [dividers[index], table_bbox[1], dividers[index + 1], table_bbox[3]],
            "x0": dividers[index],
            "x1": dividers[index + 1],
        }
        for index in range(len(labels))
    ]


def _union_bbox(bboxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    if not bboxes:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    )
