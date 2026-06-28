# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Table geometry reconstruction from chars, row/column bands, and raw cells."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.geometry.bbox import area, normalize, union
from docmirror.geometry.models import BBox, TableGeometry


def _char_bbox(ch: dict[str, Any]) -> BBox | None:
    if "bbox" in ch and isinstance(ch.get("bbox"), (list, tuple)):
        return normalize(ch.get("bbox"))
    x0 = ch.get("x0")
    x1 = ch.get("x1")
    top = ch.get("top", ch.get("y0"))
    bottom = ch.get("bottom", ch.get("y1"))
    if x0 is None or x1 is None or top is None or bottom is None:
        return None
    return normalize((float(x0), float(top), float(x1), float(bottom)))


def _char_ref(ch: dict[str, Any]) -> str | None:
    for key in ("token_id", "evidence_id", "id", "char_id"):
        value = ch.get(key)
        if value:
            return str(value)
    return None


def _char_confidence(ch: dict[str, Any]) -> float | None:
    value = ch.get("confidence", ch.get("conf"))
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean_confidence(chars: list[dict[str, Any]]) -> float | None:
    vals = [conf for ch in chars if (conf := _char_confidence(ch)) is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _chars_in_bbox(chars: list[dict[str, Any]], bbox: Sequence[float]) -> list[dict[str, Any]]:
    b = normalize(bbox)
    if b is None:
        return []
    out: list[dict[str, Any]] = []
    for ch in chars:
        cb = _char_bbox(ch)
        if cb is None:
            continue
        cx = (cb[0] + cb[2]) / 2.0
        cy = (cb[1] + cb[3]) / 2.0
        if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            out.append(ch)
    return out


def _group_chars_by_row(chars: list[dict[str, Any]], *, tolerance: float = 3.0) -> list[list[dict[str, Any]]]:
    clean = [ch for ch in chars if _char_bbox(ch) is not None and str(ch.get("text", "")).strip()]
    if not clean:
        return []
    clean.sort(key=lambda c: (_char_bbox(c) or (0.0, 0.0, 0.0, 0.0))[1])
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_y: float | None = None
    for ch in clean:
        cb = _char_bbox(ch)
        if cb is None:
            continue
        cy = (cb[1] + cb[3]) / 2.0
        if current_y is None or abs(cy - current_y) <= tolerance:
            current.append(ch)
            current_y = cy if current_y is None else (current_y + cy) / 2.0
        else:
            groups.append(current)
            current = [ch]
            current_y = cy
    if current:
        groups.append(current)
    return groups


def _even_bands(table_bbox: BBox, count: int, *, axis: str) -> list[BBox]:
    if count <= 0:
        return []
    x0, y0, x1, y1 = table_bbox
    bands: list[BBox] = []
    if axis == "y":
        step = (y1 - y0) / count if count else 0
        for i in range(count):
            bands.append((x0, y0 + step * i, x1, y0 + step * (i + 1)))
    else:
        step = (x1 - x0) / count if count else 0
        for i in range(count):
            bands.append((x0 + step * i, y0, x0 + step * (i + 1), y1))
    return bands


def _row_bands(table_bbox: BBox, chars: list[dict[str, Any]], n_rows: int) -> list[BBox]:
    groups = _group_chars_by_row(chars)
    if len(groups) >= n_rows:
        bands = []
        for group in groups[:n_rows]:
            b = union(_char_bbox(ch) for ch in group)
            if b:
                bands.append((table_bbox[0], b[1], table_bbox[2], b[3]))
        if len(bands) == n_rows:
            return bands
    return _even_bands(table_bbox, n_rows, axis="y")


def _col_bands(table_bbox: BBox, _chars: list[dict[str, Any]], n_cols: int) -> list[BBox]:
    # Keep this intentionally conservative: equal bands preserve empty columns
    # and avoid overfitting noisy chars. Native extractor bands can replace this.
    return _even_bands(table_bbox, n_cols, axis="x")


def _band_intersection(row_band: BBox, col_band: BBox) -> BBox:
    return (col_band[0], row_band[1], col_band[2], row_band[3])


def _dominant_chars_by_band(chars: list[dict[str, Any]], row_band: BBox, col_band: BBox) -> list[dict[str, Any]]:
    return _chars_in_bbox(chars, _band_intersection(row_band, col_band))


def _max_cols(table: list[list[Any]]) -> int:
    return max((len(row) for row in table if isinstance(row, list)), default=0)


def _normalize_native_cell_bboxes(
    native_cell_bboxes: list[list[Sequence[float] | None]] | None,
    *,
    n_rows: int,
    n_cols: int,
) -> list[list[BBox | None]] | None:
    if not native_cell_bboxes or len(native_cell_bboxes) < n_rows:
        return None
    out: list[list[BBox | None]] = []
    any_bbox = False
    for ri in range(n_rows):
        row = native_cell_bboxes[ri]
        if not isinstance(row, list) or len(row) < n_cols:
            return None
        out_row: list[BBox | None] = []
        for ci in range(n_cols):
            bbox = normalize(row[ci]) if row[ci] else None
            out_row.append(bbox)
            any_bbox = any_bbox or bool(bbox and area(bbox) > 0)
        out.append(out_row)
    return out if any_bbox else None


def _row_bands_from_native(native: list[list[BBox | None]], fallback: BBox) -> list[BBox]:
    bands: list[BBox] = []
    for idx, row in enumerate(native):
        row_bbox = union(cell for cell in row if cell)
        if row_bbox:
            bands.append((fallback[0], row_bbox[1], fallback[2], row_bbox[3]))
        else:
            bands.append(_even_bands(fallback, len(native), axis="y")[idx])
    return bands


def _col_bands_from_native(native: list[list[BBox | None]], fallback: BBox) -> list[BBox]:
    n_cols = max((len(row) for row in native), default=0)
    even = _even_bands(fallback, n_cols, axis="x")
    bands: list[BBox] = []
    for ci in range(n_cols):
        col_bbox = union(row[ci] for row in native if ci < len(row) and row[ci])
        if col_bbox:
            bands.append((col_bbox[0], fallback[1], col_bbox[2], fallback[3]))
        elif ci < len(even):
            bands.append(even[ci])
    return bands


def build_table_geometry(
    table: list[list[Any]],
    *,
    chars: list[dict[str, Any]] | None = None,
    table_bbox: Sequence[float] | None = None,
    native_cell_bboxes: list[list[Sequence[float] | None]] | None = None,
    page_number: int = 0,
    table_index: int = 0,
    geometry_source: str = "estimated_from_chars",
    geometry_confidence: float | None = None,
) -> TableGeometry:
    """Build a conservative table geometry payload for a raw table matrix."""
    chars = list(chars or [])
    raw_bbox = normalize(table_bbox)
    char_bbox = union(_char_bbox(ch) for ch in chars)
    tb = raw_bbox or char_bbox
    n_rows = len(table)
    n_cols = _max_cols(table)
    if tb is None or n_rows <= 0 or n_cols <= 0:
        return TableGeometry(
            table_bbox=tb,
            geometry_source=geometry_source,
            geometry_confidence=geometry_confidence,
        )

    native = _normalize_native_cell_bboxes(native_cell_bboxes, n_rows=n_rows, n_cols=n_cols)
    rows = _row_bands_from_native(native, tb) if native else _row_bands(tb, chars, n_rows)
    cols = _col_bands_from_native(native, tb) if native else _col_bands(tb, chars, n_cols)
    cell_bboxes: list[list[BBox | None]] = []
    statuses: list[list[str]] = []
    loss_reasons: list[list[str | None]] = []
    evidence: list[list[list[str]]] = []
    token_ids: list[list[list[str]]] = []
    confidences: list[list[float | None]] = []
    for ri in range(n_rows):
        bbox_row: list[BBox | None] = []
        status_row: list[str] = []
        loss_row: list[str | None] = []
        evidence_row: list[list[str]] = []
        token_row: list[list[str]] = []
        confidence_row: list[float | None] = []
        for ci in range(n_cols):
            native_bbox = native[ri][ci] if native else None
            band_bbox = native_bbox or _band_intersection(rows[ri], cols[ci])
            band_chars = _dominant_chars_by_band(chars, rows[ri], cols[ci])
            exact_bbox = union(_char_bbox(ch) for ch in band_chars)
            row_data = table[ri] if ri < len(table) and isinstance(table[ri], list) else []
            text = str(row_data[ci]) if ci < len(row_data) else ""
            if native_bbox and str(text).strip():
                bbox_row.append(native_bbox)
                status_row.append("exact")
                loss_row.append(None)
            elif exact_bbox and str(text).strip():
                bbox_row.append(exact_bbox)
                status_row.append("exact")
                loss_row.append(None)
            else:
                bbox_row.append(band_bbox if area(band_bbox) > 0 else None)
                if area(band_bbox) > 0:
                    status_row.append("estimated")
                    loss_row.append("estimated_from_row_col_bands")
                else:
                    status_row.append("missing")
                    loss_row.append("no_table_or_band_geometry")
            refs = [ref for ch in band_chars if (ref := _char_ref(ch))]
            evidence_row.append(refs or [f"cell_p{page_number}_t{table_index}_r{ri}_c{ci}"])
            token_row.append(refs)
            confidence_row.append(_mean_confidence(band_chars) or geometry_confidence)
        cell_bboxes.append(bbox_row)
        statuses.append(status_row)
        loss_reasons.append(loss_row)
        evidence.append(evidence_row)
        token_ids.append(token_row)
        confidences.append(confidence_row)

    row_roles = ["header"] + ["data"] * max(0, n_rows - 1)
    return TableGeometry(
        table_bbox=tb,
        cell_bboxes=cell_bboxes,
        cell_geometry_status=statuses,
        cell_geometry_loss_reason=loss_reasons,
        cell_evidence_ids=evidence,
        cell_token_ids=token_ids,
        cell_confidences=confidences,
        row_bands=[
            {"index": i, "bbox": list(b), "role": row_roles[i] if i < len(row_roles) else "data"}
            for i, b in enumerate(rows)
        ],
        col_bands=[{"index": i, "bbox": list(b)} for i, b in enumerate(cols)],
        geometry_source=geometry_source,
        geometry_confidence=geometry_confidence,
    )
