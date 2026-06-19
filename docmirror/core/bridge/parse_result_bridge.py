# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
ParseResult bridge — maps frozen BaseResult to public ParseResult entities.

Purpose: Assembles pages, blocks, tables, and metadata from the internal
``BaseResult`` representation into the framework ``ParseResult`` model,
including logical-table composition hooks.

Main components: ``ParseResultBridge``, ``_blocks_to_pages``,
``_compose_logical_tables``.

Upstream: ``extraction.extractor`` (``BaseResult``), ``table.compose``,
``table.merge``.

Downstream: ``entry.factory``, ``output`` exporters, plugins.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


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

    from docmirror.core.geometry.table_attrs import build_table_geometry_attrs

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
                                            _matrix_get(geometry.get("cell_token_ids"), raw_row_idx, col_idx, [])
                                            or []
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


class ParseResultBridge:
    """Unified converter between ParseResult and Core-internal BaseResult.

    Primary methods:
        - ``from_base_result(base)`` → BaseResult → ParseResult (Core boundary)
        - ``to_base_result(pr)``     → ParseResult → BaseResult (legacy Excel fallback)
    """

    # ══════════════════════════════════════════════════════════════════════
    # BaseResult → ParseResult (for adapters that extract to BaseResult)
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def from_base_result(base: BaseResult) -> ParseResult:
        """
        Convert BaseResult → ParseResult.

        Used by adapters (e.g. PDFAdapter) that extract to BaseResult
        and need to convert to ParseResult before the middleware pipeline.

        Mapping:
            - Block(type=table) → TableBlock with CellValue per cell
            - Block(type=text/title) → TextBlock with appropriate level
            - Block(type=key_value) → KeyValuePair
        """
        from docmirror.models.entities.parse_result import (
            ParseResult,
            ParserInfo,
        )

        pages = _blocks_to_pages(base)
        meta = base.metadata or {}
        structure = meta.get("structure")
        if isinstance(structure, dict):
            structure = dict(structure)
            structure.setdefault("raw_full_text_length", len(getattr(base, "full_text", "") or ""))
        pr = ParseResult(
            pages=pages,
            raw_text=getattr(base, "full_text", "") or "",
            parser_info=ParserInfo(
                parser=meta.get("parser", ""),
                elapsed_ms=meta.get("elapsed_ms", 0),
                page_count=len(base.pages),
                structure=structure,
                options={
                    "parse_control": meta.get("parse_control"),
                    "parse_control_fingerprint": meta.get("parse_control_fingerprint"),
                    "selected_pages": meta.get("selected_pages"),
                    "doc_type_hint": meta.get("doc_type_hint"),
                    "doc_type_hint_strength": meta.get("doc_type_hint_strength"),
                },
            ),
            sections=meta.get("sections", []),
        )
        if (
            meta.get("micro_grids")
            or meta.get("page_evidence_bundles")
            or meta.get("scanned_micro_grid_evidence")
            or meta.get("scanned_local_structure_evidence")
        ):
            ds = dict(getattr(pr.entities, "domain_specific", None) or {})
            if meta.get("micro_grids"):
                from docmirror.core.ocr.page_canvas.evidence_bundles import merge_micro_grid_structures_into_bundles

                merge_micro_grid_structures_into_bundles(ds, list(meta.get("micro_grids") or []))
            if meta.get("page_evidence_bundles"):
                ds["_page_evidence_bundles"] = list(meta.get("page_evidence_bundles") or [])
            else:
                if meta.get("scanned_micro_grid_evidence") or meta.get("scanned_local_structure_evidence"):
                    from docmirror.core.ocr.page_canvas.evidence_bundles import bundles_from_legacy_extractor_meta

                    bundles = bundles_from_legacy_extractor_meta(
                        scanned_micro_grid_evidence=list(meta.get("scanned_micro_grid_evidence") or []),
                        scanned_local_structure_evidence=list(meta.get("scanned_local_structure_evidence") or []),
                    )
                    if bundles:
                        ds["_page_evidence_bundles"] = bundles
            pr.entities.domain_specific = ds
            from docmirror.core.ocr.page_canvas.sync import sync_parse_result_page_canvases

            sync_parse_result_page_canvases(pr)

        # ── Compose logical tables (from extractor metadata or physical pages) ──
        _compose_logical_tables(pr, base_metadata=meta, page_layouts=list(base.pages))
        doc_type_hint = meta.get("doc_type_hint")
        if doc_type_hint:
            ds = dict(getattr(pr.entities, "domain_specific", None) or {})
            ds["user_doc_type_hint"] = str(doc_type_hint)
            ds["user_doc_type_hint_strength"] = str(meta.get("doc_type_hint_strength") or "prefer")
            ds["doc_type_hint_source"] = "user"
            pr.entities.domain_specific = ds

        scene = meta.get("document_scene")
        scene_conf = float(meta.get("scene_confidence") or 0.0)
        if scene and scene not in ("unknown", "generic"):
            ds = dict(getattr(pr.entities, "domain_specific", None) or {})
            ds["extractor_scene_hint"] = scene
            ds["extractor_scene_confidence"] = scene_conf
            pre = meta.get("pre_analysis") or {}
            if isinstance(pre, dict) and pre.get("scene_hint"):
                ds["pre_analyzer_scene_hint"] = pre.get("scene_hint")
            file_name = meta.get("file_name")
            if file_name:
                ds["source_file_name"] = str(file_name)
            pr.entities.domain_specific = ds
        perf = meta.get("perf_breakdown")
        if isinstance(perf, dict) and perf.get("extraction_audit"):
            from docmirror.models.ehl import attach_pipeline_debug

            attach_pipeline_debug(pr, "extraction_audit", perf.get("extraction_audit"))
        try:
            from docmirror.models.ehl import ensure_mirror_annex

            ensure_mirror_annex(pr)
        except Exception:
            pass
        return pr

    @staticmethod
    def to_base_result(pr: ParseResult) -> BaseResult:
        """
        Convert ParseResult → BaseResult for middleware pipeline consumption.

        Mapping:
            - PageContent → PageLayout (1:1)
            - TableBlock.rows → Block(block_type="table", raw_content=List[List[str]])
            - TextBlock → Block(block_type="text"/"title")
            - KeyValuePair → Block(block_type="key_value", raw_content={key: value})
        """
        from docmirror.models.entities.domain import BaseResult, Block, PageLayout

        pages = []
        reading_order = 0

        for page_content in pr.pages:
            blocks = []

            for text in page_content.texts:
                from docmirror.models.entities.parse_result import TextLevel

                block_type = "title" if text.level in (TextLevel.TITLE, TextLevel.H1) else "text"
                blocks.append(
                    Block(
                        block_type=block_type,
                        raw_content=text.content,
                        page=page_content.page_number,
                        reading_order=reading_order,
                        heading_level=(
                            1
                            if text.level == TextLevel.TITLE
                            else 1
                            if text.level == TextLevel.H1
                            else 2
                            if text.level == TextLevel.H2
                            else 3
                            if text.level == TextLevel.H3
                            else None
                        ),
                    )
                )
                reading_order += 1

            for kv in page_content.key_values:
                blocks.append(
                    Block(
                        block_type="key_value",
                        raw_content={kv.key: kv.value},
                        page=page_content.page_number,
                        reading_order=reading_order,
                    )
                )
                reading_order += 1

            for table in page_content.tables:
                # Convert CellValue rows to List[List[str]]
                raw_rows = []
                if table.headers:
                    raw_rows.append(table.headers)
                for row in table.rows:
                    raw_rows.append([c.text for c in row.cells])

                blocks.append(
                    Block(
                        block_type="table",
                        raw_content=raw_rows,
                        page=page_content.page_number,
                        reading_order=reading_order,
                    )
                )
                reading_order += 1

            pages.append(
                PageLayout(
                    page_number=page_content.page_number,
                    blocks=tuple(blocks),
                )
            )

        # Build full text from ParseResult
        full_text = pr.full_text

        # Build metadata from entities + parser_info
        metadata: dict[str, Any] = {
            "source_format": pr.provenance.file_type if pr.provenance else "unknown",
        }
        # Carry entities into metadata for downstream middleware access
        if pr.entities.organization:
            metadata["organization"] = pr.entities.organization
        if pr.entities.subject_name:
            metadata["subject_name"] = pr.entities.subject_name

        return BaseResult(
            pages=tuple(pages),
            full_text=full_text,
            metadata=metadata,
        )


def _deserialize_logical_table_payload(raw: dict) -> LogicalTable:
    """Rebuild a LogicalTable from serialize_logical_tables_for_metadata payload."""
    from docmirror.models.entities.parse_result import (
        CellValue,
        DataType,
        LogicalTable,
        RowProvenance,
        RowType,
        TableRow,
    )

    rows = []
    provenance = []
    table_source_pages = list(raw.get("source_pages") or [])
    table_source_phys = list(raw.get("source_physical_ids") or [])
    fallback_page = int(table_source_pages[0]) if table_source_pages else 1
    fallback_phys = str(table_source_phys[0]) if table_source_phys else f"pt_{fallback_page}_0"
    for ri, raw_row in enumerate(raw.get("rows", [])):
        cells = []
        src_page = int(raw_row.get("source_page") or fallback_page)
        src_phys = str(raw_row.get("source_physical_id") or fallback_phys)
        src_idx = int(raw_row.get("source_row_index") if raw_row.get("source_row_index") is not None else ri)
        if src_idx < 0:
            src_idx = ri
        raw_cells = list(raw_row.get("cells", []) or [])
        row_refs = list(raw_row.get("source_cell_refs") or [])
        if not row_refs:
            row_refs = [
                {"page": src_page, "table_id": src_phys, "row": src_idx, "raw_row": src_idx + 1, "col": ci}
                for ci, _rc in enumerate(raw_cells)
            ]
        for ci, rc in enumerate(raw_cells):
            text = rc.get("text", "")
            dt_str = rc.get("data_type", "text")
            try:
                dt = DataType(dt_str)
            except ValueError:
                dt = DataType.TEXT
            cell_refs = rc.get("source_cell_refs") or ([row_refs[ci]] if ci < len(row_refs) else [])
            cells.append(
                CellValue(
                    text=text,
                    data_type=dt,
                    bbox=rc.get("bbox"),
                    row_index=rc.get("row_index"),
                    col_index=rc.get("col_index"),
                    geometry_status=rc.get("geometry_status", "missing"),
                    geometry_source=rc.get("geometry_source", ""),
                    geometry_confidence=rc.get("geometry_confidence"),
                    geometry_loss_reason=rc.get("geometry_loss_reason"),
                    evidence_ids=list(rc.get("evidence_ids") or []),
                    token_ids=list(rc.get("token_ids") or []),
                    source_cell_refs=list(cell_refs or []),
                )
            )
        rows.append(
            TableRow(
                cells=cells,
                row_type=RowType.DATA,
                source_page=src_page,
                source_physical_id=src_phys,
                source_row_index=src_idx,
                source_cell_refs=row_refs,
            )
        )
        provenance.append(
            RowProvenance(
                source_page=src_page,
                source_table_id=src_phys,
                source_row_index=src_idx,
            )
        )

    sp = raw.get("source_pages", [])
    ps = raw.get("page_span", [1, 1])
    lid = raw.get("logical_id") or raw.get("table_id", "logical_0")
    return LogicalTable(
        table_id=lid,
        logical_id=lid,
        headers=raw.get("headers", []),
        rows=rows,
        row_count=raw.get("row_count", len(rows)),
        source_physical_ids=raw.get("source_physical_ids", []),
        source_pages=sp,
        page_span=(ps[0], ps[1]) if len(ps) >= 2 else (1, 1),
        confidence=raw.get("confidence", 1.0),
        merge_method=raw.get("merge_method", "cross_page_continuation"),
        merge_confidence=raw.get("merge_confidence", raw.get("confidence", 1.0)),
        provenance=provenance,
        merge_log=raw.get("merge_log", []),
        merge_audit=raw.get("merge_audit", []),
        quality_score=float(raw.get("quality_score", 1.0)),
        quality_passed=bool(raw.get("quality_passed", True)),
        quality_skip_reason=raw.get("quality_skip_reason"),
        data_row_estimate=(
            0
            if not raw.get("quality_passed", True)
            else int(raw.get("data_row_estimate") or raw.get("row_count") or len(rows))
        ),
        quality_signals=raw.get("quality_signals") or {},
    )


def _compose_logical_tables(
    pr,
    base_metadata: dict | None = None,
    *,
    page_layouts: list | None = None,
):
    """Compose logical tables from physical pages and set ParseResult.logical_tables.

    Priority:
      1. Pre-composed logical tables from extractor metadata (most accurate —
         composed before destructive merge, preserves cross-page provenance).
      2. Live composition from PageLayout list (same path as extractor Step 4.5).
    """
    from docmirror.core.table.compose.composer import build_table_operations

    # Priority 1: Pre-composed from extractor metadata
    raw_tables = None
    if base_metadata:
        raw_tables = base_metadata.get("_logical_tables")

    if raw_tables:
        export_logical = [_deserialize_logical_table_payload(raw) for raw in raw_tables]
        quarantined_raw = (base_metadata or {}).get("quarantined_logical_tables") or []
        quarantined_logical = [_deserialize_logical_table_payload(raw) for raw in quarantined_raw]
        all_logical = export_logical + quarantined_logical
        if all_logical:
            pr.logical_tables = all_logical
            pr.table_operations = build_table_operations(export_logical or all_logical)
            from docmirror.core.analyze.mirror_ltqg import attach_mirror_ltqg

            attach_mirror_ltqg(pr, base_metadata)
            return

    # Priority 2: Live composition — merger quarantine + LTQG export (parity with extractor)
    try:
        from docmirror.core.table.compose.export_pipeline import (
            compose_logical_export_from_layouts,
            page_content_to_layouts,
        )

        layouts = list(page_layouts) if page_layouts else page_content_to_layouts(pr.pages)
        if not layouts:
            return

        meta = base_metadata if base_metadata is not None else {}
        pre = meta.get("pre_analysis") if isinstance(meta.get("pre_analysis"), dict) else {}
        export_result = compose_logical_export_from_layouts(
            layouts,
            layout_profile_id=meta.get("layout_profile_id"),
            full_text=pr.full_text or meta.get("full_text") or "",
            scene_hint=pre.get("scene_hint"),
            content_type=pre.get("content_type"),
        )

        if export_result.quarantined_physical:
            meta["quarantined_tables"] = export_result.quarantined_physical
        if export_result.skipped_payload:
            meta["quarantined_logical_tables"] = export_result.skipped_payload
        if export_result.ltqg_summary is not None and export_result.ltqg_summary.enabled:
            meta["ltqg"] = export_result.ltqg_summary.to_dict()
        if export_result.export_payload:
            meta["dual_view"] = True

        if export_result.ltqg_summary is not None and export_result.ltqg_summary.enabled:
            pr.parser_info.structure = dict(pr.parser_info.structure or {})
            from docmirror.core.analyze.structure_provenance import apply_logical_tables_spe

            pr.parser_info.structure = apply_logical_tables_spe(
                pr.parser_info.structure,
                logical_table_count=len(export_result.export_logical),
                dual_view=bool(export_result.export_payload),
                ltqg_summary=export_result.ltqg_summary.to_dict(),
            )

        plugin_logical = list(export_result.export_logical)
        if export_result.skipped_logical:
            plugin_logical.extend(export_result.skipped_logical)
        if plugin_logical:
            pr.logical_tables = plugin_logical
            pr.table_operations = build_table_operations(
                export_result.export_logical or plugin_logical
            )

        from docmirror.core.analyze.mirror_ltqg import attach_mirror_ltqg

        attach_mirror_ltqg(pr, meta)
    except Exception as exc:
        logger.warning("[DocMirror] Bridge logical table composition failed: %s", exc)
