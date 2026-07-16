# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Conservative table reconstruction for OCR-only scanned statement pages."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import Any

from docmirror.models.entities.domain import Block

_FINANCIAL_KEYWORDS = (
    "资产负债表",
    "利润表",
    "现金流量表",
    "所有者权益变动表",
    "年末余额",
    "年初余额",
    "本年发生额",
    "上年发生额",
    "金额单位",
)
_FINANCIAL_HEADER_LABELS = {
    "项目",
    "附注",
    "年末余额",
    "年初余额",
    "本年发生额",
    "上年发生额",
}
_NOISE_TEXT = {"英", "超", "江", "都", "华", "盖", "身", "品", "凯", "单", "A", "E", "H", "ZV"}
_NUMBER_RE = re.compile(r"\d[\d,，]*(?:\.\d+)?")
_SHORT_NOISE_RE = re.compile(r"^[A-Za-z0-9]{1,3}$")


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
    """Build one page-level table block from OCR tokens when geometry is strong.

    This is intentionally conservative. It targets scanned financial statement
    pages where OCR has produced token-level boxes but the native PDF table
    extractor has no vector/text layer to work with.
    """
    if any(block.block_type == "table" for block in blocks):
        return None
    tokens = [_block_to_token(block) for block in blocks]
    tokens = [token for token in tokens if token is not None and _is_useful_token(token)]
    if len(tokens) < 12:
        return None
    page_text = " ".join(token.text for token in tokens)
    numeric_count = sum(1 for token in tokens if _looks_numeric(token.text))
    keyword_hits = sum(1 for keyword in _FINANCIAL_KEYWORDS if keyword in page_text)
    if keyword_hits == 0 and numeric_count < 12:
        return None

    rows = _cluster_rows(tokens)
    header_index = _find_header_row(rows)
    if header_index is None:
        return None
    table_rows = _trim_table_rows(rows[header_index:])
    if len(table_rows) < 4:
        return None

    header_tokens = _normalize_header_tokens(table_rows[0].tokens)
    anchors = _column_anchors(header_tokens, tokens)
    if len(anchors) < 3:
        return None

    raw, cell_bboxes, cell_evidence_ids, cell_confidences = _materialize_rows(table_rows, anchors)
    if len(raw) < 4 or max((len(row) for row in raw), default=0) < 3:
        return None
    if _non_empty_cells(raw[1:]) < 8:
        return None

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
            "role": "financial_statement",
            "preserve_headers": True,
            "statement_keywords": [kw for kw in _FINANCIAL_KEYWORDS if kw in page_text],
            "source": "scanned_table_reconstructor",
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
    """Reconstruct generic bordered tables from scan lines and OCR token boxes.

    The output is deliberately physical: it records page-local rows, columns,
    cell boxes, spans and token ownership without assigning business meaning or
    assuming that the first row is a semantic header.
    """
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
        x0, y0, x1, y1 = pixel_bbox
        x_lines = _projection_line_positions(vertical[y0:y1, x0:x1], axis=0, offset=x0)
        y_lines = _projection_line_positions(horizontal[y0:y1, x0:x1], axis=1, offset=y0)
        x_lines = _ensure_outer_lines(x_lines, x0, x1)
        y_lines = _ensure_outer_lines(y_lines, y0, y1)
        if len(x_lines) < 3 or len(y_lines) < 3:
            continue
        # Reject explanatory frames and page borders: a physical table needs at
        # least two rows and two columns after line extraction.
        if len(x_lines) - 1 < 2 or len(y_lines) - 1 < 2:
            continue

        groups, merge_diagnostics = _merged_cell_groups(horizontal, vertical, x_lines, y_lines)
        grid_rows = len(y_lines) - 1
        grid_cols = len(x_lines) - 1
        group_tokens: dict[int, list[_Token]] = {index: [] for index in range(len(groups))}
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

        non_empty = sum(1 for row in raw for value in row if value.strip())
        if non_empty < 3:
            continue
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


def _projection_line_positions(mask: Any, *, axis: int, offset: int) -> list[int]:
    import numpy as np

    projection = (mask > 0).mean(axis=axis)
    peak = float(projection.max()) if projection.size else 0.0
    # Faint photocopied horizontal rules often retain only 20-30% support
    # after morphology. Scale to the strongest rule in the same candidate,
    # while keeping an absolute floor so text strokes do not become grid lines.
    threshold = max(0.16, min(0.35, peak * 0.68))
    indices = np.where(projection >= threshold)[0].tolist()
    groups: list[list[int]] = []
    for index in indices:
        if not groups or index - groups[-1][-1] > 3:
            groups.append([index])
        else:
            groups[-1].append(index)
    return [offset + int(round(sum(group) / len(group))) for group in groups]


def _ensure_outer_lines(lines: list[int], _start: int, _end: int) -> list[int]:
    result = sorted(set(lines))
    return [value for index, value in enumerate(result) if index == 0 or value - result[index - 1] >= 6]


def _merged_cell_groups(
    horizontal: Any,
    vertical: Any,
    x_lines: list[int],
    y_lines: list[int],
) -> tuple[list[set[tuple[int, int]]], dict[str, int]]:
    """Return only geometrically valid rectangular merged-cell groups.

    Missing line fragments can connect an L-shaped set of base slots through
    union-find. Converting such a component to its bounding rectangle creates
    overlapping canonical cells, so every candidate is validated against the
    original line masks before it is accepted. Invalid candidates conservatively
    fall back to independent 1x1 cells.
    """
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
    if text in _NOISE_TEXT:
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


def _find_header_row(rows: list[_Row]) -> int | None:
    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(rows[:16]):
        text = row.text
        score = 0
        if "年末余额" in text or "年初余额" in text:
            score += 4
        if "本年发生额" in text or "上年发生额" in text:
            score += 4
        if "附注" in text:
            score += 2
        if "项" in text and "目" in text:
            score += 2
        if len(row.tokens) >= 3:
            score += 1
        if score > best_score:
            best_score = score
            best_index = index
    return best_index if best_score >= 4 else None


def _trim_table_rows(rows: list[_Row]) -> list[_Row]:
    trimmed: list[_Row] = []
    blankish_streak = 0
    for row in rows:
        text = row.text
        has_signal = (
            len(row.tokens) >= 2
            or _looks_numeric(text)
            or any(keyword in text for keyword in _FINANCIAL_KEYWORDS)
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


def _normalize_header_tokens(tokens: list[_Token]) -> list[_Token]:
    useful = [token for token in tokens if token.text not in _NOISE_TEXT]
    out: list[_Token] = []
    i = 0
    while i < len(useful):
        token = useful[i]
        if token.text == "项" and i + 1 < len(useful) and useful[i + 1].text == "目":
            nxt = useful[i + 1]
            out.append(
                _Token(
                    text="项目",
                    bbox=_union_bbox([token.bbox, nxt.bbox]),
                    evidence_id=f"{token.evidence_id}|{nxt.evidence_id}",
                    confidence=min(token.confidence, nxt.confidence),
                )
            )
            i += 2
            continue
        if token.text in {"项", "目"}:
            out.append(
                _Token(
                    text="项目",
                    bbox=token.bbox,
                    evidence_id=token.evidence_id,
                    confidence=token.confidence,
                )
            )
            i += 1
            continue
        out.append(token)
        i += 1
    return [
        token for token in out if token.text in _FINANCIAL_HEADER_LABELS or not _SHORT_NOISE_RE.fullmatch(token.text)
    ]


def _column_anchors(header_tokens: list[_Token], all_tokens: list[_Token]) -> list[tuple[float, str]]:
    anchors = [(token.cx, token.text) for token in header_tokens if token.text.strip()]
    anchors = [(x, text) for x, text in anchors if text not in _NOISE_TEXT]
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
