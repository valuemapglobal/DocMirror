# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compose canonical Mirror JSON vNext from the current ParseResult.

This is the first executable bridge from the existing Mirror Object Contract to
the UDTR-era document digital twin. It deliberately avoids the old REST/API
envelope and produces the new canonical ``_mirror.json`` shape.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docmirror.models.entities.parse_result import DataType, RowType, TextLevel
from docmirror.models.mirror.vnext import (
    AssetStore,
    BlockInfo,
    DiagnosticsInfo,
    DocumentInfo,
    DocumentTypeCandidate,
    EntityInfo,
    EvidenceAtom,
    EvidenceStore,
    FactInfo,
    GraphEdge,
    GraphInfo,
    GraphNode,
    MirrorInfo,
    MirrorJsonVNext,
    OverallQuality,
    PageInfo,
    QualityInfo,
    ReadingFlowInfo,
    RegionInfo,
    SemanticsInfo,
    SourceInfo,
    TypedValue,
)


class _IdFactory:
    def __init__(self) -> None:
        self._counters: defaultdict[str, int] = defaultdict(int)

    def next(self, prefix: str, *, width: int = 4) -> str:
        self._counters[prefix] += 1
        return f"{prefix}:{self._counters[prefix]:0{width}d}"

    @staticmethod
    def page(page_number: int) -> str:
        return f"page:{page_number:04d}"


def compose_mirror_json_vnext(
    result: Any,
    *,
    source_filename: str = "",
    profile: str = "canonical_full",
    engine_version: str = "0.1.0",
) -> MirrorJsonVNext:
    """Build canonical Mirror JSON vNext from a ParseResult-like object."""

    ids = _IdFactory()
    source = _build_source(result, source_filename=source_filename)
    document_id = _document_id(source)

    evidence = EvidenceStore(indexes={"by_page": {}, "by_source": {}})
    pages: list[PageInfo] = []
    regions: list[RegionInfo] = []
    blocks: list[BlockInfo] = []
    graph_nodes: list[GraphNode] = [GraphNode(id=document_id, kind="document")]
    graph_edges: list[GraphEdge] = []
    semantics = SemanticsInfo()

    block_order: list[tuple[int, int, str]] = []
    block_to_region: dict[str, str] = {}

    source_pages = list(getattr(result, "pages", []) or [])
    if source_pages:
        page_items: list[tuple[int, Any, int]] = [
            (idx, page, int(getattr(page, "page_number", idx + 1) or idx + 1)) for idx, page in enumerate(source_pages)
        ]
    else:
        page_items = [(idx, None, idx + 1) for idx in range(max(source.page_count, 0))]

    for page_index, page, page_number in page_items:
        page_id = ids.page(page_number)
        page_width = _to_float_or_none(getattr(page, "width", None))
        page_height = _to_float_or_none(getattr(page, "height", None))
        page_info = PageInfo(
            page_id=page_id,
            page_index=page_index,
            page_number=page_number,
            width=page_width,
            height=page_height,
            coordinate_transform=_identity_coordinate_transform(page_width, page_height),
            content_mode=_page_content_mode(page),
        )
        graph_nodes.append(GraphNode(id=page_id, kind="page"))
        graph_edges.append(
            GraphEdge(
                id=ids.next("edge", width=6),
                type="contains",
                **{"from": document_id},
                to=page_id,
                confidence=1.0,
            )
        )

        page_blocks: list[BlockInfo] = []
        page_regions: list[RegionInfo] = []
        local_order = 0

        for text in getattr(page, "texts", []) or []:
            local_order += 1
            text_atoms = _text_atoms_for_content(
                ids,
                evidence,
                page_id=page_id,
                text=str(getattr(text, "content", "") or ""),
                bbox=_bbox(getattr(text, "bbox", None)),
                confidence=_confidence(getattr(text, "confidence", 1.0)),
                source_refs=list(getattr(text, "evidence_ids", []) or []),
            )
            block = _text_block(ids, text, page_id=page_id, evidence_ids=text_atoms)
            region = _region_for_block(
                ids,
                block,
                page_id=page_id,
                kind=_region_kind_for_text(getattr(text, "level", TextLevel.BODY)),
                role=_role_for_text(getattr(text, "level", TextLevel.BODY)),
                reading_order=local_order,
            )
            page_blocks.append(block)
            page_regions.append(region)
            block_to_region[block.id] = region.id
            block_order.append((page_number, local_order, block.id))

        if getattr(page, "key_values", None):
            local_order += 1
            kv_block, kv_region, kv_facts = _kv_group_block(
                ids,
                page,
                page_id=page_id,
                document_id=document_id,
                reading_order=local_order,
                evidence=evidence,
            )
            page_blocks.append(kv_block)
            page_regions.append(kv_region)
            semantics.facts.extend(kv_facts)
            block_to_region[kv_block.id] = kv_region.id
            block_order.append((page_number, local_order, kv_block.id))

        for table in getattr(page, "tables", []) or []:
            local_order += 1
            block, region = _table_block(
                ids,
                table,
                page_id=page_id,
                page_number=page_number,
                reading_order=local_order,
                evidence=evidence,
            )
            page_blocks.append(block)
            page_regions.append(region)
            block_to_region[block.id] = region.id
            block_order.append((page_number, local_order, block.id))

        if not page_blocks:
            local_order += 1
            residual_block, residual_region = _page_residual_block(
                ids,
                page_id=page_id,
                bbox=_page_bbox(page_info),
                reading_order=local_order,
                reason="no_content_detected",
            )
            page_blocks.append(residual_block)
            page_regions.append(residual_region)
            block_to_region[residual_block.id] = residual_region.id
            block_order.append((page_number, local_order, residual_block.id))

        for region in page_regions:
            graph_nodes.append(GraphNode(id=region.id, kind="region"))
            graph_edges.append(
                GraphEdge(
                    id=ids.next("edge", width=6),
                    type="contains",
                    **{"from": page_id},
                    to=region.id,
                    confidence=region.confidence,
                )
            )
        for block in page_blocks:
            graph_nodes.append(GraphNode(id=block.id, kind="block"))
            graph_edges.append(
                GraphEdge(
                    id=ids.next("edge", width=6),
                    type="contains",
                    **{"from": block_to_region[block.id]},
                    to=block.id,
                    confidence=block.confidence,
                )
            )

        page_info.region_ids = [region.id for region in page_regions]
        page_info.block_ids = [block.id for block in page_blocks]
        page_info.blocks = [block.model_dump(by_alias=True, exclude_none=True) for block in page_blocks]
        page_info.evidence_ids = _page_evidence_ids(evidence, page_id)
        page_info.quality = _page_quality(page_info, has_residual=any(block.type == "residual" for block in page_blocks))
        pages.append(page_info)
        regions.extend(page_regions)
        blocks.extend(page_blocks)

    if not pages and not blocks:
        residual_block = _document_residual_block(ids, reason="no_pages_detected")
        blocks.append(residual_block)
        graph_nodes.append(GraphNode(id=residual_block.id, kind="block"))
        graph_edges.append(
            GraphEdge(
                id=ids.next("edge", width=6),
                type="contains",
                **{"from": document_id},
                to=residual_block.id,
                confidence=residual_block.confidence,
            )
        )
        block_order.append((0, 0, residual_block.id))

    _add_logical_tables(ids, result, blocks, graph_nodes, graph_edges)
    _add_entity_facts(result, document_id=document_id, semantics=semantics)
    _add_domain_view(result, semantics=semantics, blocks=blocks)

    sorted_block_ids = [block_id for _, _, block_id in sorted(block_order)]
    for prev, current in zip(sorted_block_ids, sorted_block_ids[1:]):
        graph_edges.append(
            GraphEdge(
                id=ids.next("edge", width=6),
                type="reading_next",
                **{"from": prev},
                to=current,
                confidence=0.98,
            )
        )

    for fact in semantics.facts:
        graph_nodes.append(GraphNode(id=fact.id, kind="fact"))
        for source_block_id in fact.source_block_ids:
            graph_edges.append(
                GraphEdge(
                    id=ids.next("edge", width=6),
                    type="derived_from",
                    **{"from": fact.id},
                    to=source_block_id,
                    confidence=fact.confidence,
                    evidence_ids=fact.evidence_ids,
                )
            )

    mirror = MirrorInfo(
        generated_at=datetime.now(timezone.utc).isoformat(),
        profile=profile,
        engine_version=engine_version,
    )
    document = DocumentInfo(
        document_id=document_id,
        title=_document_title(blocks),
        languages=_languages(result),
        content_mode=_document_content_mode(pages),
        document_type_candidates=_document_type_candidates(result),
        root_block_ids=sorted_block_ids,
        outline_block_ids=[b.id for b in blocks if b.type == "heading"],
        primary_reading_flow_id="flow:main",
    )
    graph = GraphInfo(
        nodes=graph_nodes,
        edges=graph_edges,
        reading_flows=[
            ReadingFlowInfo(
                flow_id="flow:main",
                kind="main_reading_order",
                node_ids=sorted_block_ids,
                confidence=0.98 if sorted_block_ids else 0.0,
            )
        ],
        outline=_outline_from_blocks(blocks),
    )
    quality = _quality(result, pages=pages, evidence=evidence, blocks=blocks)
    diagnostics = DiagnosticsInfo(
        pipeline=[
            {
                "stage": "mirror_json_vnext_composer",
                "status": "ok",
                "profile": profile,
                "block_count": len(blocks),
                "region_count": len(regions),
                "residual_count": sum(1 for block in blocks if block.type == "residual"),
                "evidence_count": len(evidence.text_atoms)
                + len(evidence.visual_atoms)
                + len(evidence.image_atoms)
                + len(evidence.vector_atoms),
            }
        ],
        warnings=[*_warnings(result), *_residual_warnings(blocks)],
    )

    _finalize_evidence_indexes(evidence)

    return MirrorJsonVNext(
        mirror=mirror,
        source=source,
        document=document,
        pages=pages,
        evidence=evidence,
        regions=regions,
        blocks=blocks,
        graph=graph,
        semantics=semantics,
        quality=quality,
        diagnostics=diagnostics,
        assets=AssetStore(),
    )


def mirror_json_vnext_dict(result: Any, **kwargs: Any) -> dict[str, Any]:
    """Return a JSON-serializable canonical Mirror JSON vNext dict."""

    return compose_mirror_json_vnext(result, **kwargs).model_dump(by_alias=True, exclude_none=True)


def _build_source(result: Any, *, source_filename: str) -> SourceInfo:
    provenance = getattr(result, "provenance", None)
    filename = source_filename or _provenance_value(provenance, "filename") or ""
    if not filename:
        source_path = _provenance_document_property(provenance, "source_path") or ""
        filename = Path(str(source_path)).name if source_path else ""
    mime_type = _provenance_value(provenance, "mime_type") or ""
    checksum = _provenance_value(provenance, "checksum") or ""
    file_size = _provenance_value(provenance, "file_size")
    input_kind = _input_kind(mime_type=mime_type, filename=filename, fallback=_provenance_value(provenance, "file_type"))
    page_count = int(getattr(getattr(result, "parser_info", None), "page_count", 0) or getattr(result, "page_count", 0) or 0)
    return SourceInfo(
        filename=filename,
        mime_type=str(mime_type or ""),
        sha256=str(checksum or ""),
        size_bytes=int(file_size) if isinstance(file_size, int | float) and file_size else None,
        page_count=page_count,
        input_kind=input_kind,
        provenance=_model_dump(provenance) if provenance is not None else {},
    )


def _document_id(source: SourceInfo) -> str:
    if source.sha256:
        return f"doc:sha256:{source.sha256}"
    if source.filename:
        return f"doc:filename:{source.filename}"
    return "doc:unknown"


def _text_atoms_for_content(
    ids: _IdFactory,
    evidence: EvidenceStore,
    *,
    page_id: str,
    text: str,
    bbox: list[float] | None,
    confidence: float,
    source_refs: list[str],
    source_bbox: list[float] | None = None,
    coordinate_transform: dict[str, Any] | None = None,
) -> list[str]:
    if not text:
        return []
    atom_id = ids.next(f"ev:{page_id.split(':')[-1]}:text", width=6)
    evidence.text_atoms.append(
        EvidenceAtom(
            id=atom_id,
            kind="text_token",
            source_kind="parse_result",
            page_id=page_id,
            text=text,
            bbox=bbox,
            source_bbox=source_bbox if source_bbox is not None else bbox,
            coordinate_transform=coordinate_transform or _identity_coordinate_transform(None, None),
            confidence=confidence,
            source_refs=source_refs,
        )
    )
    return [atom_id]


def _text_block(ids: _IdFactory, text: Any, *, page_id: str, evidence_ids: list[str]) -> BlockInfo:
    level = getattr(text, "level", TextLevel.BODY)
    block_type = "heading" if level in {TextLevel.TITLE, TextLevel.H1, TextLevel.H2, TextLevel.H3} else "paragraph"
    return BlockInfo(
        id=ids.next(f"blk:{block_type}", width=4),
        type=block_type,
        role=_role_for_text(level),
        page_ids=[page_id],
        bbox=_bbox(getattr(text, "bbox", None)),
        text=str(getattr(text, "content", "") or ""),
        evidence_ids=evidence_ids,
        confidence=_confidence(getattr(text, "confidence", 1.0)),
        provenance={"reconstructor": "parse_result_text_adapter", "version": "0.1.0"},
    )


def _kv_group_block(
    ids: _IdFactory,
    page: Any,
    *,
    page_id: str,
    document_id: str,
    reading_order: int,
    evidence: EvidenceStore,
) -> tuple[BlockInfo, RegionInfo, list[FactInfo]]:
    block_id = ids.next("blk:kv_group", width=4)
    items: list[dict[str, Any]] = []
    evidence_ids: list[str] = []
    facts: list[FactInfo] = []
    bboxes: list[list[float]] = []
    for kv in getattr(page, "key_values", []) or []:
        key = str(getattr(kv, "key", "") or "")
        value = str(getattr(kv, "value", "") or "")
        bbox = _bbox(getattr(kv, "bbox", None))
        if bbox:
            bboxes.append(bbox)
        atom_ids = _text_atoms_for_content(
            ids,
            evidence,
            page_id=page_id,
            text=f"{key}: {value}".strip(": "),
            bbox=bbox,
            confidence=_confidence(getattr(kv, "confidence", 1.0)),
            source_refs=list(getattr(kv, "evidence_ids", []) or []),
        )
        evidence_ids.extend(atom_ids)
        fact_id = _fact_id(key)
        item = {
            "key": key,
            "value": _typed_value(value, confidence=_confidence(getattr(kv, "confidence", 1.0))).model_dump(
                exclude_none=True
            ),
            "evidence_ids": atom_ids,
            "fact_id": fact_id,
        }
        if bbox:
            item["bbox"] = bbox
        items.append(item)
        facts.append(
            FactInfo(
                id=fact_id,
                subject_id=document_id,
                predicate=f"document.field.{_slug(key)}",
                object=_typed_value(value, confidence=_confidence(getattr(kv, "confidence", 1.0))),
                source_block_ids=[block_id],
                evidence_ids=atom_ids,
                confidence=_confidence(getattr(kv, "confidence", 1.0)),
            )
        )

    block = BlockInfo(
        id=block_id,
        type="key_value_group",
        role="document_metadata",
        page_ids=[page_id],
        bbox=_union_bbox(bboxes),
        content={"items": items},
        evidence_ids=evidence_ids,
        confidence=_average([_confidence(getattr(kv, "confidence", 1.0)) for kv in getattr(page, "key_values", [])]),
        provenance={"reconstructor": "parse_result_key_value_adapter", "version": "0.1.0"},
    )
    region = _region_for_block(
        ids,
        block,
        page_id=page_id,
        kind="text",
        role="document_metadata",
        reading_order=reading_order,
    )
    return block, region, facts


def _table_block(
    ids: _IdFactory,
    table: Any,
    *,
    page_id: str,
    page_number: int,
    reading_order: int,
    evidence: EvidenceStore,
) -> tuple[BlockInfo, RegionInfo]:
    block_id = ids.next("blk:table", width=4)
    table_bbox = _bbox(getattr(table, "bbox", None))
    headers = [str(h) for h in (getattr(table, "headers", []) or [])]
    row_objs = list(getattr(table, "rows", []) or [])
    column_count = max([len(headers), *(len(getattr(row, "cells", []) or []) for row in row_objs), 0])
    columns = [
        {
            "id": f"col:{block_id}:{idx:04d}",
            "index": idx,
            "bbox": _column_bbox(table_bbox, idx, column_count),
            "header": headers[idx] if idx < len(headers) else "",
            "data_type": _column_data_type(row_objs, idx),
            "confidence": _confidence(getattr(table, "confidence", 1.0)),
        }
        for idx in range(column_count)
    ]

    rows: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    evidence_ids: list[str] = []
    row_index = 0
    if headers:
        row_bbox = _row_bbox(table_bbox, row_index, len(row_objs) + 1)
        rows.append(
            {
                "id": f"row:{block_id}:{row_index:04d}",
                "index": row_index,
                "role": "header",
                "bbox": row_bbox,
                "confidence": _confidence(getattr(table, "confidence", 1.0)),
            }
        )
        for col_index, header in enumerate(headers):
            atom_ids = _text_atoms_for_content(
                ids,
                evidence,
                page_id=page_id,
                text=header,
                bbox=_cell_bbox(row_bbox, col_index, column_count),
                confidence=_confidence(getattr(table, "confidence", 1.0)),
                source_refs=list(getattr(table, "evidence_ids", []) or []),
            )
            evidence_ids.extend(atom_ids)
            cells.append(
                _cell_dict(
                    block_id=block_id,
                    row_index=row_index,
                    col_index=col_index,
                    text=header,
                    value=_typed_value(header),
                    bbox=_cell_bbox(row_bbox, col_index, column_count),
                    evidence_ids=atom_ids,
                    confidence=_confidence(getattr(table, "confidence", 1.0)),
                )
            )
        row_index += 1

    for source_row_index, row in enumerate(row_objs):
        row_bbox = _row_bbox_from_cells(row) or _row_bbox(table_bbox, row_index, len(row_objs) + int(bool(headers)))
        rows.append(
            {
                "id": f"row:{block_id}:{row_index:04d}",
                "index": row_index,
                "role": _row_role(getattr(row, "row_type", RowType.DATA)),
                "bbox": row_bbox,
                "confidence": _confidence(getattr(row, "confidence", 1.0)),
                "source_page": int(getattr(row, "source_page", 0) or page_number),
                "source_row_index": int(getattr(row, "source_row_index", source_row_index) or source_row_index),
            }
        )
        for col_index, cell in enumerate(getattr(row, "cells", []) or []):
            cell_text = str(getattr(cell, "text", "") or "")
            cell_bbox = _bbox(getattr(cell, "bbox", None)) or _cell_bbox(row_bbox, col_index, column_count)
            atom_ids = _text_atoms_for_content(
                ids,
                evidence,
                page_id=page_id,
                text=cell_text,
                bbox=cell_bbox,
                confidence=_confidence(getattr(cell, "confidence", 1.0)),
                source_refs=list(getattr(cell, "evidence_ids", []) or []),
            )
            evidence_ids.extend(atom_ids)
            cells.append(
                _cell_dict(
                    block_id=block_id,
                    row_index=row_index,
                    col_index=col_index,
                    text=cell_text,
                    value=_value_from_cell(cell),
                    bbox=cell_bbox,
                    evidence_ids=atom_ids,
                    confidence=_confidence(getattr(cell, "confidence", 1.0)),
                    row_span=int(getattr(cell, "row_span", 1) or 1),
                    col_span=int(getattr(cell, "col_span", 1) or 1),
                )
            )
        row_index += 1

    block = BlockInfo(
        id=block_id,
        type="table",
        role=_table_role(table),
        page_ids=[page_id],
        bbox=table_bbox,
        content={
            "caption": getattr(table, "caption", None),
            "grid": {
                "line_source": _line_source(table),
                "columns": columns,
                "rows": rows,
                "cells": cells,
                "implicit_lines": _implicit_lines(table_bbox, column_count, len(rows), source=_line_source(table)),
            },
            "continuation": {
                "table_group_id": f"tblgrp:{getattr(table, 'table_id', '') or block_id}",
                "part_index": 0,
                "continued_from": None,
                "continued_to": None,
            },
        },
        evidence_ids=evidence_ids,
        confidence=_confidence(getattr(table, "confidence", 1.0)),
        quality={
            "column_count": column_count,
            "row_count": len(rows),
            "header_confidence": _confidence(getattr(table, "confidence", 1.0)) if headers else 0.0,
            "grid_confidence": _confidence(
                getattr(table, "extraction_confidence", None) or getattr(table, "confidence", 1.0)
            ),
            "cell_assignment_coverage": 1.0 if cells else 0.0,
            "empty_cell_ratio": _empty_cell_ratio(cells),
        },
        provenance={
            "reconstructor": "parse_result_table_adapter",
            "version": "0.1.0",
            "source_table_id": getattr(table, "table_id", ""),
            "extraction_layer": getattr(table, "extraction_layer", ""),
        },
    )
    region = _region_for_block(
        ids,
        block,
        page_id=page_id,
        kind="table_like",
        role=block.role,
        reading_order=reading_order,
    )
    return block, region


def _region_for_block(
    ids: _IdFactory,
    block: BlockInfo,
    *,
    page_id: str,
    kind: str,
    role: str,
    reading_order: int,
) -> RegionInfo:
    region = RegionInfo(
        id=ids.next(f"reg:{page_id.split(':')[-1]}", width=4),
        page_id=page_id,
        kind=kind,
        role=role,
        bbox=block.bbox,
        evidence_ids=block.evidence_ids,
        block_ids=[block.id],
        reading_order=reading_order,
        confidence=block.confidence,
        quality={"ownership_ratio": 1.0, "overlap_warnings": []},
    )
    block.region_ids = [region.id]
    return region


def _page_residual_block(
    ids: _IdFactory,
    *,
    page_id: str,
    bbox: list[float] | None,
    reading_order: int,
    reason: str,
) -> tuple[BlockInfo, RegionInfo]:
    block = BlockInfo(
        id=ids.next("blk:residual", width=4),
        type="residual",
        role="empty_page",
        page_ids=[page_id],
        bbox=bbox,
        text="",
        content={
            "reason": reason,
            "candidate_roles": [],
        },
        confidence=1.0,
        quality={"requires_review": True},
        provenance={"reconstructor": "residual_collector_minimal", "version": "0.1.0"},
    )
    region = _region_for_block(
        ids,
        block,
        page_id=page_id,
        kind="residual",
        role="empty_page",
        reading_order=reading_order,
    )
    return block, region


def _document_residual_block(ids: _IdFactory, *, reason: str) -> BlockInfo:
    return BlockInfo(
        id=ids.next("blk:residual", width=4),
        type="residual",
        role="empty_document",
        page_ids=[],
        text="",
        content={
            "reason": reason,
            "candidate_roles": [],
        },
        confidence=1.0,
        quality={"requires_review": True},
        provenance={"reconstructor": "residual_collector_minimal", "version": "0.1.0"},
    )


def _cell_dict(
    *,
    block_id: str,
    row_index: int,
    col_index: int,
    text: str,
    value: TypedValue,
    bbox: list[float] | None,
    evidence_ids: list[str],
    confidence: float,
    row_span: int = 1,
    col_span: int = 1,
) -> dict[str, Any]:
    return {
        "id": f"cell:{block_id}:{row_index:04d}:{col_index:04d}",
        "row": row_index,
        "col": col_index,
        "row_span": row_span,
        "col_span": col_span,
        "bbox": bbox,
        "text": text,
        "value": value.model_dump(exclude_none=True),
        "evidence_ids": evidence_ids,
        "confidence": confidence,
    }


def _value_from_cell(cell: Any) -> TypedValue:
    raw = str(getattr(cell, "text", "") or "")
    data_type = getattr(cell, "data_type", DataType.TEXT)
    normalized = getattr(cell, "numeric", None)
    if normalized is None:
        normalized = getattr(cell, "cleaned", None) or raw
    return TypedValue(
        raw=raw,
        normalized=normalized,
        type=_data_type_value(data_type),
        confidence=_confidence(getattr(cell, "confidence", 1.0)),
    )


def _typed_value(raw: Any, *, confidence: float = 1.0) -> TypedValue:
    text = str(raw or "")
    normalized: Any = text
    value_type = "string"
    stripped = text.replace(",", "").strip()
    if stripped:
        try:
            normalized = float(stripped)
            value_type = "number"
        except ValueError:
            if _looks_like_date(stripped):
                value_type = "date"
    return TypedValue(raw=text, normalized=normalized, type=value_type, confidence=confidence)


def _add_logical_tables(
    ids: _IdFactory,
    result: Any,
    blocks: list[BlockInfo],
    graph_nodes: list[GraphNode],
    graph_edges: list[GraphEdge],
) -> None:
    by_source = {str((block.provenance or {}).get("source_table_id") or ""): block.id for block in blocks}
    for lt in getattr(result, "logical_tables", []) or []:
        source_block_ids = [by_source.get(str(pid)) for pid in getattr(lt, "source_physical_ids", []) or []]
        source_block_ids = [bid for bid in source_block_ids if bid]
        if len(source_block_ids) < 2:
            continue
        for left, right in zip(source_block_ids, source_block_ids[1:]):
            graph_edges.append(
                GraphEdge(
                    id=ids.next("edge", width=6),
                    type="same_table",
                    **{"from": left},
                    to=right,
                    confidence=_confidence(getattr(lt, "merge_confidence", 1.0)),
                    metadata={"logical_id": getattr(lt, "logical_id", "") or getattr(lt, "table_id", "")},
                )
            )
        for block_id in source_block_ids:
            if all(node.id != block_id for node in graph_nodes):
                graph_nodes.append(GraphNode(id=block_id, kind="block"))


def _add_entity_facts(result: Any, *, document_id: str, semantics: SemanticsInfo) -> None:
    entities = getattr(result, "entities", None)
    if entities is None:
        return
    field_map = {
        "organization": ("organization", "document.organization"),
        "subject_name": ("person_or_subject", "document.subject.name"),
        "subject_id": ("identifier", "document.subject.id"),
        "document_date": ("date", "document.date"),
        "period_start": ("date", "document.period.start"),
        "period_end": ("date", "document.period.end"),
    }
    for attr, (entity_type, predicate) in field_map.items():
        value = getattr(entities, attr, None)
        if not value:
            continue
        entity_id = f"ent:{_slug(attr)}"
        semantics.entities.append(
            EntityInfo(
                id=entity_id,
                type=entity_type,
                name=str(value),
                normalized_name=str(value),
                confidence=1.0,
            )
        )
        semantics.facts.append(
            FactInfo(
                id=f"fact:{_slug(attr)}",
                subject_id=document_id,
                predicate=predicate,
                object=_typed_value(value),
                confidence=1.0,
            )
        )


def _add_domain_view(result: Any, *, semantics: SemanticsInfo, blocks: list[BlockInfo]) -> None:
    document_type = str(getattr(getattr(result, "entities", None), "document_type", "") or "unknown")
    if not document_type or document_type == "unknown":
        return
    view: dict[str, Any] = {
        "fact_ids": [fact.id for fact in semantics.facts],
        "block_ids": [block.id for block in blocks],
    }
    table_ids = [block.id for block in blocks if block.type == "table"]
    if table_ids:
        view["table_block_ids"] = table_ids
    semantics.views[document_type] = view


def _quality(result: Any, *, pages: list[PageInfo], evidence: EvidenceStore, blocks: list[BlockInfo]) -> QualityInfo:
    text_count = len(evidence.text_atoms)
    block_evidence = {ev_id for block in blocks for ev_id in block.evidence_ids}
    coverage = (len(block_evidence) / text_count) if text_count else (0.0 if blocks else 0.0)
    confidence = _confidence(getattr(result, "confidence", 1.0))
    table_blocks = [block for block in blocks if block.type == "table"]
    residual_blocks = [block for block in blocks if block.type == "residual"]
    residual_ratio = (len(residual_blocks) / len(blocks)) if blocks else 1.0
    avg_grid = _average([float((block.quality or {}).get("grid_confidence", 0.0) or 0.0) for block in table_blocks])
    status = "pass" if coverage >= 0.995 and confidence >= 0.8 and residual_ratio < 0.5 else "warn"
    return QualityInfo(
        overall=OverallQuality(score=min(coverage, confidence), status=status, confidence=confidence),
        coverage={
            "evidence_coverage": coverage,
            "text_token_coverage": coverage,
            "visual_atom_coverage": 1.0,
            "residual_ratio": residual_ratio,
        },
        tables={
            "count": len(table_blocks),
            "average_grid_confidence": avg_grid,
            "low_confidence_table_ids": [
                block.id for block in table_blocks if float((block.quality or {}).get("grid_confidence", 0.0) or 0.0) < 0.8
            ],
        },
        reading_order={"score": 0.98 if blocks else 0.0, "warnings": []},
        gates=[
            {
                "id": "gate:evidence_conservation",
                "status": "pass" if coverage >= 0.995 else "warn",
                "score": coverage,
                "threshold": 0.995,
            }
        ],
        events=[],
    )


def _finalize_evidence_indexes(evidence: EvidenceStore) -> None:
    by_page: dict[str, list[str]] = defaultdict(list)
    by_source: dict[str, list[str]] = defaultdict(list)
    for atom in [*evidence.text_atoms, *evidence.visual_atoms, *evidence.image_atoms, *evidence.vector_atoms]:
        by_page[atom.page_id].append(atom.id)
        by_source[atom.source_kind].append(atom.id)
    evidence.indexes = {"by_page": dict(by_page), "by_source": dict(by_source)}


def _page_evidence_ids(evidence: EvidenceStore, page_id: str) -> list[str]:
    return [
        atom.id
        for atom in [*evidence.text_atoms, *evidence.visual_atoms, *evidence.image_atoms, *evidence.vector_atoms]
        if atom.page_id == page_id
    ]


def _page_quality(page: PageInfo, *, has_residual: bool = False) -> dict[str, Any]:
    return {
        "evidence_coverage": 1.0 if page.evidence_ids else 0.0,
        "residual_ratio": 1.0 if has_residual else 0.0,
    }


def _page_bbox(page: PageInfo) -> list[float] | None:
    if page.width is None or page.height is None:
        return None
    return [0.0, 0.0, float(page.width), float(page.height)]


def _identity_coordinate_transform(width: float | None, height: float | None) -> dict[str, Any]:
    return {
        "source_rotation": 0,
        "normalized_rotation": 0,
        "deskew_angle": 0.0,
        "scale": 1.0,
        "source_width": float(width or 0.0),
        "source_height": float(height or 0.0),
        "matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    }


def _residual_warnings(blocks: list[BlockInfo]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for idx, block in enumerate([item for item in blocks if item.type == "residual"], start=1):
        warnings.append(
            {
                "id": f"warn:residual:{idx:04d}",
                "severity": "medium",
                "message": f"residual block emitted: {block.content.get('reason', 'unknown')}",
                "target_ids": [block.id],
            }
        )
    return warnings


def _document_title(blocks: list[BlockInfo]) -> dict[str, Any] | None:
    for block in blocks:
        if block.type == "heading" and block.text:
            return {"text": block.text, "block_id": block.id, "confidence": block.confidence}
    return None


def _document_type_candidates(result: Any) -> list[DocumentTypeCandidate]:
    document_type = str(getattr(getattr(result, "entities", None), "document_type", "") or "unknown")
    return [DocumentTypeCandidate(type=document_type, confidence=_confidence(getattr(result, "confidence", 1.0)))]


def _outline_from_blocks(blocks: list[BlockInfo]) -> list[dict[str, Any]]:
    outline: list[dict[str, Any]] = []
    for block in blocks:
        if block.type == "heading":
            outline.append(
                {
                    "block_id": block.id,
                    "title": block.text or "",
                    "level": {"title": 1, "h1": 1, "h2": 2, "h3": 3}.get(block.role, 1),
                    "page_ids": block.page_ids,
                    "confidence": block.confidence,
                }
            )
    return outline


def _languages(result: Any) -> list[str]:
    language = (getattr(getattr(result, "entities", None), "domain_specific", {}) or {}).get("language")
    if isinstance(language, str) and language:
        return [language]
    if isinstance(language, list):
        return [str(item) for item in language if item]
    return []


def _warnings(result: Any) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    parser_info = getattr(result, "parser_info", None)
    for idx, warning in enumerate(getattr(parser_info, "warnings", []) or [], start=1):
        warnings.append({"id": f"warn:{idx:04d}", "severity": "medium", "message": str(warning), "target_ids": []})
    for idx, error in enumerate(getattr(result, "errors", []) or [], start=len(warnings) + 1):
        warnings.append({"id": f"warn:{idx:04d}", "severity": "high", "message": str(error), "target_ids": []})
    return warnings


def _page_content_mode(page: Any) -> str:
    mode = getattr(page, "page_mode", None)
    if mode:
        return str(mode)
    if getattr(page, "texts", None) or getattr(page, "tables", None) or getattr(page, "key_values", None):
        return "native_text"
    return "unknown"


def _document_content_mode(pages: list[PageInfo]) -> str:
    modes = {page.content_mode for page in pages if page.content_mode != "unknown"}
    if not modes:
        return "unknown"
    if len(modes) == 1:
        return next(iter(modes))
    return "hybrid"


def _region_kind_for_text(level: Any) -> str:
    return "heading" if level in {TextLevel.TITLE, TextLevel.H1, TextLevel.H2, TextLevel.H3} else "text"


def _role_for_text(level: Any) -> str:
    if hasattr(level, "value"):
        return str(level.value)
    return str(level or "body")


def _table_role(table: Any) -> str:
    metadata = getattr(table, "metadata", None) or {}
    role = metadata.get("role") or metadata.get("mirror_role")
    if role:
        return str(role)
    return "table"


def _line_source(table: Any) -> str:
    layer = str(getattr(table, "extraction_layer", "") or "")
    if "grid" in layer or "implicit" in layer or "char" in layer:
        return "implicit"
    if "line" in layer or "pdf" in layer:
        return "explicit"
    return "unknown"


def _implicit_lines(
    bbox: list[float] | None,
    column_count: int,
    row_count: int,
    *,
    source: str,
) -> dict[str, list[dict[str, Any]]]:
    if not bbox:
        return {"vertical": [], "horizontal": []}
    x0, y0, x1, y1 = bbox
    vertical = [
        {"x": x0 + ((x1 - x0) * idx / max(column_count, 1)), "confidence": 0.5, "source": source}
        for idx in range(column_count + 1)
    ]
    horizontal = [
        {"y": y0 + ((y1 - y0) * idx / max(row_count, 1)), "confidence": 0.5, "source": source}
        for idx in range(row_count + 1)
    ]
    return {"vertical": vertical, "horizontal": horizontal}


def _column_data_type(rows: list[Any], col_index: int) -> str:
    values = []
    for row in rows:
        cells = list(getattr(row, "cells", []) or [])
        if col_index < len(cells):
            values.append(_data_type_value(getattr(cells[col_index], "data_type", DataType.TEXT)))
    if not values:
        return "string"
    non_text = [value for value in values if value not in {"text", "string"}]
    return non_text[0] if non_text else "string"


def _data_type_value(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    value = str(value or "text")
    return "string" if value == "text" else value


def _row_role(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "data")


def _row_bbox_from_cells(row: Any) -> list[float] | None:
    return _union_bbox([bbox for cell in getattr(row, "cells", []) or [] if (bbox := _bbox(getattr(cell, "bbox", None)))])


def _row_bbox(table_bbox: list[float] | None, row_index: int, row_count: int) -> list[float] | None:
    if not table_bbox or row_count <= 0:
        return None
    x0, y0, x1, y1 = table_bbox
    height = (y1 - y0) / row_count
    return [x0, y0 + row_index * height, x1, y0 + (row_index + 1) * height]


def _column_bbox(table_bbox: list[float] | None, col_index: int, col_count: int) -> list[float] | None:
    if not table_bbox or col_count <= 0:
        return None
    x0, y0, x1, y1 = table_bbox
    width = (x1 - x0) / col_count
    return [x0 + col_index * width, y0, x0 + (col_index + 1) * width, y1]


def _cell_bbox(row_bbox: list[float] | None, col_index: int, col_count: int) -> list[float] | None:
    if not row_bbox or col_count <= 0:
        return None
    x0, y0, x1, y1 = row_bbox
    width = (x1 - x0) / col_count
    return [x0 + col_index * width, y0, x0 + (col_index + 1) * width, y1]


def _union_bbox(bboxes: list[list[float]] | None) -> list[float] | None:
    values = [bbox for bbox in (bboxes or []) if bbox and len(bbox) == 4]
    if not values:
        return None
    return [
        min(b[0] for b in values),
        min(b[1] for b in values),
        max(b[2] for b in values),
        max(b[3] for b in values),
    ]


def _bbox(value: Any) -> list[float] | None:
    if not value or not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    return [x0, y0, x1, y1]


def _empty_cell_ratio(cells: list[dict[str, Any]]) -> float:
    if not cells:
        return 0.0
    empty = sum(1 for cell in cells if not str(cell.get("text") or "").strip())
    return empty / len(cells)


def _confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, parsed))


def _average(values: list[float]) -> float:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _looks_like_date(text: str) -> bool:
    if len(text) < 8:
        return False
    return any(sep in text for sep in ("-", "/", "."))


def _slug(value: str) -> str:
    out = []
    for ch in str(value).strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_") or "unknown"


def _fact_id(key: str) -> str:
    return f"fact:{_slug(key)}"


def _input_kind(*, mime_type: str, filename: str, fallback: Any) -> str:
    mime = str(mime_type or "").lower()
    if "pdf" in mime:
        return "pdf"
    if "image" in mime:
        return "image"
    if "spreadsheet" in mime or "excel" in mime:
        return "spreadsheet"
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}:
        return "image"
    if suffix in {".xlsx", ".xls", ".csv", ".tsv"}:
        return "spreadsheet"
    if fallback:
        return str(fallback)
    return "unknown"


def _provenance_value(provenance: Any, key: str) -> Any:
    if provenance is None:
        return None
    return getattr(provenance, key, None)


def _provenance_document_property(provenance: Any, key: str) -> Any:
    props = getattr(provenance, "document_properties", None) or {}
    if isinstance(props, dict):
        return props.get(key)
    return None


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return value
    return {}


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "compose_mirror_json_vnext",
    "mirror_json_vnext_dict",
]
