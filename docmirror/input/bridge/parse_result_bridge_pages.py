# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""BaseResult block → ParseResult page mapping helpers."""

from __future__ import annotations

from typing import Any

from docmirror.models.entities.physical import BaseResult


def _infer_cell_value(
    text: str,
    *,
    bbox: list[float] | None = None,
    row_index: int | None = None,
    col_index: int | None = None,
    geometry_status: str = "missing",
    geometry_source: str = "",
    geometry_confidence: float | None = None,
    geometry_loss_reason: str | None = None,
    evidence_ids: list[str] | None = None,
    token_ids: list[str] | None = None,
    source_cell_refs: list[dict[str, Any]] | None = None,
) -> CellValue:
    """Infer CellValue type from raw text string.

    Returns CellValue with proper data_type, numeric, and cleaned fields.
    """
    import re

    from docmirror.models.entities.parse_result import CellValue, DataType

    text = str(text).strip()
    if not text:
        return CellValue(
            text=text,
            data_type=DataType.EMPTY,
            bbox=bbox,
            row_index=row_index,
            col_index=col_index,
            geometry_status=geometry_status,
            geometry_source=geometry_source,
            geometry_confidence=geometry_confidence,
            geometry_loss_reason=geometry_loss_reason,
            evidence_ids=evidence_ids or [],
            token_ids=token_ids or [],
            source_cell_refs=source_cell_refs or [],
        )

    def _with_geometry_kwargs(**kwargs):
        kwargs.update(
            bbox=bbox,
            row_index=row_index,
            col_index=col_index,
            geometry_status=geometry_status,
            geometry_source=geometry_source,
            geometry_confidence=geometry_confidence,
            geometry_loss_reason=geometry_loss_reason,
            evidence_ids=evidence_ids or [],
            token_ids=token_ids or [],
            source_cell_refs=source_cell_refs or [],
        )
        return kwargs

    # Date patterns: 2025-03-27, 2025/03/27, 2025年03月27日
    if re.match(r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?$", text):
        return CellValue(**_with_geometry_kwargs(text=text, data_type=DataType.DATE))

    # Time pattern: 14:21:48
    if re.match(r"^\d{2}:\d{2}(:\d{2})?$", text):
        return CellValue(**_with_geometry_kwargs(text=text, data_type=DataType.TEXT))

    # Currency/Number: try parsing
    cleaned = text.replace(",", "").replace("，", "").replace(" ", "")
    # Remove currency symbols
    cleaned = re.sub(r"^[¥$€£]", "", cleaned)

    # Try numeric parse
    try:
        float(cleaned)
        # Long digit-only strings (>10 chars, no decimal) are identifiers
        # (account numbers, ID numbers, invoice codes), not values
        if re.match(r"^\d{10,}$", cleaned):
            return CellValue(**_with_geometry_kwargs(text=text, data_type=DataType.TEXT))
        # Determine if currency (has comma formatting or decimal places typical of money)
        has_comma = "," in text or "，" in text
        has_decimal = "." in cleaned and len(cleaned.split(".")[-1]) == 2
        if has_comma or has_decimal:
            return CellValue(**_with_geometry_kwargs(text=text, data_type=DataType.CURRENCY))
        else:
            return CellValue(**_with_geometry_kwargs(text=text, data_type=DataType.NUMBER))
    except (ValueError, TypeError):
        pass

    return CellValue(**_with_geometry_kwargs(text=text, data_type=DataType.TEXT))


def _matrix_get(matrix: Any, row_idx: int, col_idx: int, default: Any = None) -> Any:
    if not isinstance(matrix, list) or row_idx < 0 or row_idx >= len(matrix):
        return default
    row = matrix[row_idx]
    if not isinstance(row, list) or col_idx < 0 or col_idx >= len(row):
        return default
    return row[col_idx]


def _table_geometry_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    geometry = attrs.get("geometry") if isinstance(attrs.get("geometry"), dict) else {}
    out = dict(geometry)
    for key in (
        "cell_bboxes",
        "cell_geometry_status",
        "cell_geometry_loss_reason",
        "cell_evidence_ids",
        "cell_token_ids",
        "cell_confidences",
        "row_bands",
        "col_bands",
    ):
        if key not in out and key in attrs:
            out[key] = attrs[key]
    if "geometry_source" not in out:
        out["geometry_source"] = attrs.get("geometry_source") or attrs.get("extraction_layer") or ""
    if "geometry_confidence" not in out:
        out["geometry_confidence"] = attrs.get("geometry_confidence") or attrs.get("extraction_confidence")
    if "coordinate_system" not in out:
        out["coordinate_system"] = "pdf_points_top_left"
    return out


def _table_bbox_from_block(block: Any, page_layout: Any) -> tuple[float, float, float, float] | None:
    bbox = getattr(block, "bbox", None)
    if bbox and len(bbox) == 4 and any(float(v) != 0.0 for v in bbox):
        return tuple(float(v) for v in bbox)
    width = float(getattr(page_layout, "width", 0.0) or 0.0)
    height = float(getattr(page_layout, "height", 0.0) or 0.0)
    if width > 0 and height > 0:
        return (0.0, 0.0, width, height)
    return None


def _ensure_table_geometry(
    raw: list[list[Any]],
    attrs: dict[str, Any],
    block: Any,
    page_layout: Any,
    *,
    table_index: int,
) -> dict[str, Any]:
    geometry = _table_geometry_attrs(attrs)
    has_cell_geometry = bool(geometry.get("cell_bboxes"))
    has_bands = bool(geometry.get("row_bands")) and bool(geometry.get("col_bands"))
    if has_cell_geometry and has_bands:
        return geometry

    bbox = _table_bbox_from_block(block, page_layout)
    if bbox is None:
        return geometry

    from docmirror.geometry.table_attrs import build_table_geometry_attrs

    source = (
        geometry.get("geometry_source")
        or attrs.get("geometry_source")
        or attrs.get("extraction_layer")
        or "bridge_estimated"
    )
    conf = geometry.get("geometry_confidence")
    if conf is None:
        conf = attrs.get("geometry_confidence")
    if conf is None:
        conf = attrs.get("extraction_confidence")
    estimated_attrs = build_table_geometry_attrs(
        raw,
        table_bbox=bbox,
        page_number=int(getattr(page_layout, "page_number", 0) or 0),
        table_index=table_index,
        geometry_source=str(source),
        geometry_confidence=float(conf) if conf is not None else None,
    )
    estimated = estimated_attrs.get("geometry") or {}
    merged = dict(estimated)
    merged.update({k: v for k, v in geometry.items() if v not in (None, [], {})})
    for key in (
        "cell_bboxes",
        "cell_geometry_status",
        "cell_geometry_loss_reason",
        "cell_evidence_ids",
        "cell_token_ids",
        "cell_confidences",
        "row_bands",
        "col_bands",
    ):
        if not merged.get(key) and estimated.get(key):
            merged[key] = estimated[key]
    return merged


def _block_evidence_ids(block, *, prefix: str = "ev") -> list[str]:
    """Return stable evidence IDs for a physical block and its text spans."""
    existing = list(getattr(block, "evidence_ids", ()) or ())
    if existing:
        return existing
    block_id = str(getattr(block, "block_id", "") or "block")
    page_no = int(getattr(block, "page", 0) or 0)
    spans = list(getattr(block, "spans", ()) or ())
    if spans:
        return [f"{prefix}_p{page_no}_{block_id}_span{i}" for i, _span in enumerate(spans)]
    return [f"{prefix}_p{page_no}_{block_id}"]


def _blocks_to_pages(base: BaseResult):
    """Convert BaseResult pages/blocks → List[PageContent] for ParseResult.

    Mapping:
        - Block(type=table, raw_content=List[List[str]]) → TableBlock with typed CellValue
        - Block(type=text/title) → TextBlock with heading level
        - Block(type=key_value, raw_content=dict) → KeyValuePair
    """
    from docmirror.models.entities.parse_result import (
        KeyValuePair,
        PageContent,
        RowType,
        TableBlock,
        TableRow,
        TextBlock,
        TextLevel,
    )

    meta = getattr(base, "metadata", None) or {}
    perf = meta.get("perf_breakdown") if isinstance(meta, dict) else {}
    audit = (perf or {}).get("extraction_audit") if isinstance(perf, dict) else {}
    audit_pages: dict[int, dict[str, Any]] = {}
    if isinstance(audit, dict):
        for item in audit.get("pages") or []:
            if isinstance(item, dict):
                try:
                    audit_pages[int(item.get("page") or item.get("page_number") or 0)] = item
                except (TypeError, ValueError):
                    continue
    pages = []
    for page_layout in base.pages:
        tables = []
        texts = []
        key_values = []

        for block in page_layout.blocks:
            if block.block_type == "table" and isinstance(block.raw_content, list):
                raw = block.raw_content
                attrs = dict(getattr(block, "attrs", None) or {})
                page_audit = audit_pages.get(int(page_layout.page_number))
                if page_audit:
                    if not attrs.get("extraction_layer"):
                        attrs["extraction_layer"] = page_audit.get("picked") or page_audit.get("layer") or ""
                    if attrs.get("extraction_confidence") is None:
                        score = page_audit.get("score")
                        if score is not None:
                            attrs["extraction_confidence"] = score
                table_index = len(tables)
                geometry = _ensure_table_geometry(raw, attrs, block, page_layout, table_index=table_index)
                headers = []
                rows = []
                pt_id = f"pt_{page_layout.page_number}_{table_index}"
                if raw:
                    headers = [str(h) for h in raw[0]]
                    for row_idx, row_data in enumerate(raw[1:]):
                        if isinstance(row_data, list):
                            raw_row_idx = row_idx + 1
                            cells = []
                            row_refs = []
                            for col_idx, value in enumerate(row_data):
                                source_ref = {
                                    "page": page_layout.page_number,
                                    "table_id": pt_id,
                                    "row": row_idx,
                                    "raw_row": raw_row_idx,
                                    "col": col_idx,
                                }
                                row_refs.append(source_ref)
                                cells.append(
                                    _infer_cell_value(
                                        value,
                                        bbox=_matrix_get(geometry.get("cell_bboxes"), raw_row_idx, col_idx),
                                        row_index=row_idx,
                                        col_index=col_idx,
                                        geometry_status=str(
                                            _matrix_get(
                                                geometry.get("cell_geometry_status"),
                                                raw_row_idx,
                                                col_idx,
                                                "missing",
                                            )
                                            or "missing"
                                        ),
                                        geometry_source=str(geometry.get("geometry_source") or ""),
                                        geometry_confidence=(
                                            float(
                                                _matrix_get(
                                                    geometry.get("cell_confidences"),
                                                    raw_row_idx,
                                                    col_idx,
                                                    geometry.get("geometry_confidence"),
                                                )
                                            )
                                            if _matrix_get(
                                                geometry.get("cell_confidences"),
                                                raw_row_idx,
                                                col_idx,
                                                geometry.get("geometry_confidence"),
                                            )
                                            is not None
                                            else None
                                        ),
                                        geometry_loss_reason=_matrix_get(
                                            geometry.get("cell_geometry_loss_reason"),
                                            raw_row_idx,
                                            col_idx,
                                        ),
                                        evidence_ids=list(
                                            _matrix_get(geometry.get("cell_evidence_ids"), raw_row_idx, col_idx, [])
                                            or []
                                        ),
                                        token_ids=list(
                                            _matrix_get(geometry.get("cell_token_ids"), raw_row_idx, col_idx, []) or []
                                        ),
                                        source_cell_refs=[source_ref],
                                    )
                                )
                            rows.append(
                                TableRow(
                                    cells=cells,
                                    row_type=RowType.DATA,
                                    source_page=page_layout.page_number,
                                    source_physical_id=pt_id,
                                    source_row_index=row_idx,
                                    source_cell_refs=row_refs,
                                )
                            )
                metadata = dict(attrs)
                if geometry:
                    metadata["geometry"] = geometry
                metadata["raw_rows"] = [[str(c) for c in row] for row in raw]
                tables.append(
                    TableBlock(
                        table_id=pt_id,
                        headers=headers,
                        rows=rows,
                        page=page_layout.page_number,
                        page_span=1,
                        bbox=list(block.bbox) if getattr(block, "bbox", None) else None,
                        confidence=float(attrs.get("extraction_confidence") or 1.0),
                        extraction_layer=str(attrs.get("extraction_layer") or ""),
                        extraction_confidence=(
                            float(attrs["extraction_confidence"])
                            if attrs.get("extraction_confidence") is not None
                            else None
                        ),
                        evidence_ids=_block_evidence_ids(block, prefix="table"),
                        metadata=metadata,
                    )
                )

            elif block.block_type in ("text", "title") and isinstance(block.raw_content, str):
                level = TextLevel.BODY
                if block.block_type == "title" or block.heading_level == 1:
                    level = TextLevel.H1
                elif block.heading_level == 2:
                    level = TextLevel.H2
                elif block.heading_level == 3:
                    level = TextLevel.H3
                texts.append(
                    TextBlock(
                        content=block.raw_content,
                        level=level,
                        bbox=list(block.bbox) if getattr(block, "bbox", None) else None,
                        evidence_ids=_block_evidence_ids(block, prefix="ocr" if page_layout.is_scanned else "text"),
                    )
                )

            elif block.block_type == "key_value" and isinstance(block.raw_content, dict):
                for k, v in block.raw_content.items():
                    key_values.append(
                        KeyValuePair(
                            key=str(k),
                            value=str(v),
                            bbox=list(block.bbox) if getattr(block, "bbox", None) else None,
                            evidence_ids=_block_evidence_ids(block, prefix="kv"),
                        )
                    )

            elif block.block_type == "footer" and isinstance(block.raw_content, str):
                texts.append(
                    TextBlock(
                        content=block.raw_content,
                        level=TextLevel.FOOTER,
                        bbox=list(block.bbox) if getattr(block, "bbox", None) else None,
                        evidence_ids=_block_evidence_ids(block, prefix="text"),
                    )
                )

        pages.append(
            PageContent(
                page_number=page_layout.page_number,
                tables=tables,
                texts=texts,
                key_values=key_values,
                width=int(page_layout.width) if getattr(page_layout, "width", None) else None,
                height=int(page_layout.height) if getattr(page_layout, "height", None) else None,
            )
        )

    return pages
