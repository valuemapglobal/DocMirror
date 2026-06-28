# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Region reconstructors for UDTR topology regions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from docmirror.models.mirror.vnext import BlockInfo, EvidenceAtom
from docmirror.structure.evidence_plane import EvidencePlane
from docmirror.structure.page_topology import TopologyRegion
from docmirror.structure.reconstruction_contract import ReconstructionContract, default_contract
from docmirror.structure.tables.statement import build_statement_structure


@dataclass(frozen=True)
class ReconstructionContext:
    evidence_plane: EvidencePlane
    atom_by_id: dict[str, EvidenceAtom]
    atom_text: dict[str, str]


@dataclass(frozen=True)
class ReconstructionReport:
    block: BlockInfo
    selected_reconstructor: str
    selected_score: float
    candidate_scores: list[dict[str, object]]
    contract: dict[str, object]
    fallback_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "block_id": self.block.id,
            "selected_reconstructor": self.selected_reconstructor,
            "selected_score": float(self.selected_score),
            "candidate_scores": [dict(candidate) for candidate in self.candidate_scores],
            "contract": dict(self.contract),
            "fallback_reason": self.fallback_reason,
        }


class RegionReconstructor(Protocol):
    id: str
    supported_kinds: set[str]

    def score(self, region: TopologyRegion, context: ReconstructionContext) -> float:
        """Return a confidence-like score for claiming a region."""

    def reconstruct(self, region: TopologyRegion, context: ReconstructionContext) -> BlockInfo:
        """Reconstruct a semantic block from a claimed region."""


class RegionReconstructorRegistry:
    """Choose the best registered reconstructor for a topology region."""

    def __init__(self, reconstructors: list[RegionReconstructor] | None = None) -> None:
        self._reconstructors: list[RegionReconstructor] = reconstructors or [
            CoverRegionReconstructor(),
            FinancialStatementReconstructor(),
            TableLikeRegionReconstructor(),
            KeyValueGroupRegionReconstructor(),
            TocRegionReconstructor(),
            VisualRegionReconstructor(),
            TextRegionReconstructor(),
            ResidualRegionReconstructor(),
        ]

    def register(self, reconstructor: RegionReconstructor) -> None:
        self._reconstructors.append(reconstructor)

    def reconstruct(self, region: TopologyRegion, context: ReconstructionContext) -> BlockInfo:
        return self.reconstruct_with_report(region, context).block

    def reconstruct_with_report(self, region: TopologyRegion, context: ReconstructionContext) -> ReconstructionReport:
        scored = [
            (reconstructor.score(region, context), idx, reconstructor)
            for idx, reconstructor in enumerate(self._reconstructors)
            if region.kind in reconstructor.supported_kinds
        ]
        if not scored:
            fallback = ResidualRegionReconstructor()
            block = fallback.reconstruct(region, context)
            return _attach_dispatch_provenance(
                block,
                fallback,
                1.0,
                [],
                fallback_reason="no_supported_reconstructor",
            )
        score, _, reconstructor = max(scored, key=lambda item: (item[0], -item[1]))
        if score <= 0:
            fallback = ResidualRegionReconstructor()
            block = fallback.reconstruct(region, context)
            return _attach_dispatch_provenance(
                block,
                fallback,
                1.0,
                scored,
                fallback_reason="non_positive_reconstructor_score",
            )
        block = reconstructor.reconstruct(region, context)
        return _attach_dispatch_provenance(block, reconstructor, score, scored)


def _attach_dispatch_provenance(
    block: BlockInfo,
    reconstructor: RegionReconstructor,
    score: float,
    scored: list[tuple[float, int, RegionReconstructor]],
    *,
    fallback_reason: str = "",
) -> ReconstructionReport:
    contract = (
        reconstructor.contract()
        if hasattr(reconstructor, "contract")
        else default_contract(reconstructor)
    )
    candidates = [
        {
            "reconstructor": getattr(candidate, "id", type(candidate).__name__),
            "score": round(float(candidate_score), 6),
            "contract_id": (
                candidate.contract().id
                if hasattr(candidate, "contract")
                else default_contract(candidate).id
            ),
        }
        for candidate_score, _idx, candidate in scored
    ]
    block.provenance = {
        **(block.provenance or {}),
        "reconstruction_contract": contract.to_dict(),
        "dispatch": {
            "selected_reconstructor": getattr(reconstructor, "id", type(reconstructor).__name__),
            "selected_score": round(float(score), 6),
            "candidate_scores": candidates,
            "fallback_reason": fallback_reason,
        },
    }
    return ReconstructionReport(
        block=block,
        selected_reconstructor=getattr(reconstructor, "id", type(reconstructor).__name__),
        selected_score=round(float(score), 6),
        candidate_scores=candidates,
        contract=contract.to_dict(),
        fallback_reason=fallback_reason,
    )


class TextRegionReconstructor:
    id = "minimal_text_region_reconstructor"
    supported_kinds = {"text", "heading", "header", "footer", "footnote"}

    def score(self, region: TopologyRegion, context: ReconstructionContext) -> float:
        text = _joined_text(region, context)
        return 0.8 if text else 0.0

    def reconstruct(self, region: TopologyRegion, context: ReconstructionContext) -> BlockInfo:
        text = _joined_text(region, context)
        block_type = _text_block_type(region, text)
        content: dict[str, object] = {
            "source": "page_topology_text_region",
            "topology": dict(region.diagnostics),
        }
        if block_type == "list":
            content["list_item"] = _list_item_info(text)
        return BlockInfo(
            id=f"blk:{block_type}:{_region_suffix(region)}",
            type=block_type,
            role=region.role,
            page_ids=[region.page_id],
            region_ids=[region.id],
            bbox=region.bbox,
            text=text,
            content=content,
            evidence_ids=list(region.evidence_ids),
            confidence=region.confidence,
            quality={"requires_review": False},
            provenance={"reconstructor": self.id, "version": "0.1.0"},
        )


class CoverRegionReconstructor:
    """Recognize audit-report cover pages from heading-like regions.

    Detects cover patterns: large centered text on page 1 containing keywords
    like 审计报告 / annual report / 年度报告.  Outputs a heading block with
    enriched cover metadata.
    """

    id = "cover_page_reconstructor"
    supported_kinds = {"heading"}

    _COVER_KEYWORDS = (
        "审计报告", "年度报告", "财务报告", "annual report", "audit report",
        "financial report", "审计报告及财务报表",
    )

    def score(self, region: TopologyRegion, context: ReconstructionContext) -> float:
        # Extract page number from page_id (format: "page:0001")
        page_number = int(region.page_id.split(":")[-1]) if ":" in region.page_id else 0
        if page_number > 2:
            return 0.0
        text = _joined_text(region, context)
        if not text:
            return 0.0
        text_lower = text.lower()
        for kw in self._COVER_KEYWORDS:
            if kw.lower() in text_lower:
                base = 0.9 if page_number <= 1 else 0.6
                return base * _cover_text_size_ratio(region, context)
        return 0.0

    def reconstruct(self, region: TopologyRegion, context: ReconstructionContext) -> BlockInfo:
        text = _joined_text(region, context)
        clean_text = text
        for prefix in ("文档头部", "文档末尾", "页眉", "页脚"):
            if clean_text.startswith(prefix):
                clean_text = clean_text[len(prefix):].strip()
        content: dict[str, object] = {"source": "cover_page_detection", "text": clean_text, "cover_title": clean_text}
        return BlockInfo(
            id=f"block:cover:{_region_suffix(region)}",
            type="heading",
            role="cover_title",
            text=clean_text,
            page_ids=[region.page_id],
            bbox=list(region.bbox) if region.bbox else None,
            content=content,
            evidence_ids=list(region.evidence_ids),
            quality={"grid_confidence": 0.8},
        )


class FinancialStatementReconstructor:
    """Recognize financial statement tables (balance sheet, income statement, cash flow).

    Detects financial statement table patterns by header keywords and
    multi-line column spans. It delegates grid reconstruction to the standard
    table-like reconstructor, then enriches the resulting table block with a
    financial-statement role hint.
    """

    id = "financial_statement_reconstructor"
    supported_kinds = {"table_like"}

    _FS_KEYWORDS = (
        "资产负债表", "利润表", "现金流量表", "所有者权益变动表",
        "balance sheet", "income statement", "cash flow",
    )

    def contract(self) -> ReconstructionContract:
        return ReconstructionContract(
            id=self.id,
            accepted_region_kinds=["table_like"],
            required_evidence_kinds=["text_token"],
            optional_evidence_kinds=["vector_line", "image", "visual_artifact"],
            output_block_types=["table"],
            output_roles=["financial_statement"],
            failure_modes=[
                "insufficient_header_bands",
                "low_alignment_score",
                "ambiguous_column_groups",
            ],
            fallback=TableLikeRegionReconstructor.id,
            quality_keys=[
                "grid_confidence",
                "header_hierarchy_confidence",
                "column_group_confidence",
                "account_hierarchy_confidence",
            ],
        )

    def score(self, region: TopologyRegion, context: ReconstructionContext) -> float:
        text = _joined_text(region, context)
        diagnostics = region.diagnostics or {}
        statement_keywords = diagnostics.get("statement_keywords") if isinstance(diagnostics.get("statement_keywords"), list) else []
        if diagnostics.get("role") == "financial_statement" or statement_keywords:
            return 0.98
        if not text:
            return 0.0
        text_lower = text.lower()
        for kw in self._FS_KEYWORDS:
            if kw.lower() in text_lower:
                return 0.97
        return 0.0

    def reconstruct(self, region: TopologyRegion, context: ReconstructionContext) -> BlockInfo:
        text = _joined_text(region, context)
        diagnostics = region.diagnostics or {}
        statement_keywords = diagnostics.get("statement_keywords") if isinstance(diagnostics.get("statement_keywords"), list) else []
        structure_source_text = " ".join([text, *(str(keyword) for keyword in statement_keywords)]).strip()
        block = TableLikeRegionReconstructor().reconstruct(region, context)
        fs_type = next((kw for kw in self._FS_KEYWORDS if kw.lower() in structure_source_text.lower()), "unknown")
        block.role = "financial_statement"
        block.content = {
            **(block.content or {}),
            "financial_statement": {
                "fs_type": fs_type,
                "source": "financial_statement_detection",
                "text": structure_source_text,
            },
        }
        block.content["statement_structure"] = build_statement_structure(block, source_text=structure_source_text)
        statement_quality = block.content["statement_structure"].get("quality", {})
        block.quality = {
            **(block.quality or {}),
            "financial_statement_detected": True,
            "header_hierarchy_confidence": statement_quality.get("header_hierarchy_confidence", 0.0),
            "column_group_confidence": statement_quality.get("column_group_confidence", 0.0),
            "account_hierarchy_confidence": statement_quality.get("account_hierarchy_confidence", 0.0),
            "statement_structure_review_reasons": statement_quality.get("review_reasons", []),
            "requires_review": bool((block.quality or {}).get("grid_confidence", 0.0) < 0.8),
        }
        block.provenance = {
            **(block.provenance or {}),
            "reconstructor": self.id,
            "version": "0.1.0",
            "delegates_to": TableLikeRegionReconstructor.id,
        }
        return block


def _cover_text_size_ratio(region: TopologyRegion, context: ReconstructionContext) -> float:
    try:
        atoms = [context.atom_by_id.get(aid) for aid in (region.evidence_ids or [])]
        heights: list[float] = []
        for a in atoms:
            if a is None or not a.bbox or len(a.bbox) < 4:
                continue
            h = float(a.bbox[3]) - float(a.bbox[1])
            if h > 2:
                heights.append(h)
        if not heights:
            return 1.0
        return min(1.0, (sum(heights) / len(heights)) / 14.0)
    except Exception:
        return 1.0


class VisualRegionReconstructor:
    id = "minimal_visual_region_reconstructor"
    supported_kinds = {"figure", "image", "seal", "signature"}

    def score(self, region: TopologyRegion, context: ReconstructionContext) -> float:
        atoms = _region_atoms(region, context)
        return 0.85 if atoms else 0.0

    def reconstruct(self, region: TopologyRegion, context: ReconstructionContext) -> BlockInfo:
        atoms = _region_atoms(region, context)
        block_type = "figure" if region.kind == "figure" else "artifact"
        return BlockInfo(
            id=f"blk:{block_type}:{_region_suffix(region)}",
            type=block_type,
            role=region.role,
            page_ids=[region.page_id],
            region_ids=[region.id],
            bbox=region.bbox,
            text=None,
            content={
                "atom_count": len(atoms),
                "atom_kinds": sorted({str(atom.kind) for atom in atoms}),
                "source_kinds": sorted({atom.source_kind for atom in atoms}),
            },
            evidence_ids=list(region.evidence_ids),
            confidence=region.confidence,
            quality={"requires_review": False},
            provenance={"reconstructor": self.id, "version": "0.1.0"},
        )


class ResidualRegionReconstructor:
    id = "minimal_residual_reconstructor"
    supported_kinds = {"residual", "unknown"}

    def score(self, region: TopologyRegion, context: ReconstructionContext) -> float:
        return 1.0

    def reconstruct(self, region: TopologyRegion, context: ReconstructionContext) -> BlockInfo:
        return BlockInfo(
            id=f"blk:residual:{_region_suffix(region)}",
            type="residual",
            role=region.role,
            page_ids=[region.page_id],
            region_ids=[region.id],
            bbox=region.bbox,
            text=_joined_text(region, context),
            content={
                "reason": region.diagnostics.get("reason", "unassigned_evidence"),
                "candidate_roles": [],
            },
            evidence_ids=list(region.evidence_ids),
            confidence=region.confidence,
            quality={"requires_review": True},
            provenance={"reconstructor": self.id, "version": "0.1.0"},
        )


class KeyValueGroupRegionReconstructor:
    id = "metadata_key_value_group_reconstructor"
    supported_kinds = {"text"}

    def score(self, region: TopologyRegion, context: ReconstructionContext) -> float:
        atoms = _key_value_atoms(region, context)
        if atoms:
            return 0.95
        inferred_items = _inferred_key_value_items(region, context)
        return 0.78 if inferred_items else 0.0

    def reconstruct(self, region: TopologyRegion, context: ReconstructionContext) -> BlockInfo:
        atoms = _key_value_atoms(region, context)
        items: list[dict[str, object]] = []
        if atoms:
            for atom in atoms:
                key = str(atom.metadata.get("key") or "")
                raw_text = str(atom.text or "")
                parsed_key, parsed_value = _split_key_value_text(raw_text)
                key = key or parsed_key
                items.append(
                    {
                        "key": key,
                        "value": _typed_value_dict(parsed_value, confidence=atom.confidence),
                        "bbox": atom.bbox,
                        "evidence_ids": [atom.id],
                    }
                )
        else:
            items = _inferred_key_value_items(region, context)

        return BlockInfo(
            id=f"blk:kv_group:{_region_suffix(region)}",
            type="key_value_group",
            role=region.role,
            page_ids=[region.page_id],
            region_ids=[region.id],
            bbox=region.bbox,
            text=_joined_text(region, context),
            content={"items": items},
            evidence_ids=[atom.id for atom in atoms] if atoms else list(region.evidence_ids),
            confidence=region.confidence,
            quality={
                "item_count": len(items),
                "requires_review": not items,
            },
            provenance={"reconstructor": self.id, "version": "0.1.0"},
        )


class TocRegionReconstructor:
    id = "minimal_toc_region_reconstructor"
    supported_kinds = {"text"}

    def score(self, region: TopologyRegion, context: ReconstructionContext) -> float:
        return 0.9 if region.role == "toc_entry" else 0.0

    def reconstruct(self, region: TopologyRegion, context: ReconstructionContext) -> BlockInfo:
        title = str(region.diagnostics.get("toc_title") or _joined_text(region, context))
        target_page = region.diagnostics.get("toc_target_page")
        item: dict[str, object] = {
            "title": title,
            "target_page": target_page,
            "evidence_ids": list(region.evidence_ids),
        }
        return BlockInfo(
            id=f"blk:toc:{_region_suffix(region)}",
            type="toc",
            role=region.role,
            page_ids=[region.page_id],
            region_ids=[region.id],
            bbox=region.bbox,
            text=_joined_text(region, context),
            content={"items": [item]},
            evidence_ids=list(region.evidence_ids),
            confidence=region.confidence,
            quality={"requires_review": target_page is None},
            provenance={"reconstructor": self.id, "version": "0.1.0"},
        )


class TableLikeRegionReconstructor:
    id = "metadata_table_like_region_reconstructor"
    supported_kinds = {"table_like"}

    def contract(self) -> ReconstructionContract:
        return ReconstructionContract(
            id=self.id,
            accepted_region_kinds=["table_like"],
            required_evidence_kinds=["text_token"],
            optional_evidence_kinds=["vector_line"],
            output_block_types=["table"],
            output_roles=["table"],
            failure_modes=["missing_columns", "missing_rows", "low_grid_confidence"],
            fallback="minimal_residual_reconstructor",
            quality_keys=["grid_confidence", "header_confidence", "column_count", "row_count"],
        )

    def score(self, region: TopologyRegion, context: ReconstructionContext) -> float:
        table_atoms = _table_atoms(region, context)
        if not table_atoms:
            if _implicit_table_grid(region):
                return 0.75
            if region.diagnostics.get("predicted_kind") == "micro_grid" and _line_grid_table(region, context):
                return 0.58
            return 0.0
        has_columns = any("header_index" in atom.metadata or "col_index" in atom.metadata for atom in table_atoms)
        return 0.9 if has_columns else 0.5

    def reconstruct(self, region: TopologyRegion, context: ReconstructionContext) -> BlockInfo:
        table_atoms = _table_atoms(region, context)
        if not table_atoms:
            implicit_grid = _implicit_table_grid(region, context)
            if implicit_grid:
                return _grid_table_block(
                    region,
                    self.id,
                    implicit_grid,
                    line_source=str(region.diagnostics.get("implicit_table_source") or "implicit_grid_text_atoms"),
                )
            line_grid = _line_grid_table(region, context)
            if line_grid:
                return _grid_table_block(
                    region,
                    self.id,
                    line_grid,
                    line_source="segment_page_blocks_line_grid",
                )
        block_id = f"blk:table:{_region_suffix(region)}"
        headers = _headers(table_atoms)
        row_cells = _row_cells(table_atoms)
        column_count = max([len(headers), *[max(cols.keys()) + 1 for cols in row_cells.values() if cols], 0])

        columns = [
            {
                "id": f"col:{block_id}:{col_index:04d}",
                "index": col_index,
                "bbox": _column_bbox(region.bbox, col_index, column_count),
                "header": headers[col_index] if col_index < len(headers) else "",
                "data_type": "unknown",
                "confidence": region.confidence,
            }
            for col_index in range(column_count)
        ]

        rows: list[dict[str, object]] = []
        cells: list[dict[str, object]] = []
        output_row_index = 0
        if headers:
            rows.append(_row_dict(block_id, output_row_index, "header", region, len(row_cells) + 1))
            for col_index in range(column_count):
                header_atom = _header_atom(table_atoms, col_index)
                header_text = headers[col_index] if col_index < len(headers) else ""
                cells.append(
                    _cell_dict(
                        block_id,
                        output_row_index,
                        col_index,
                        text=header_text,
                        atom=header_atom,
                        bbox=_cell_bbox(rows[-1].get("bbox"), col_index, column_count),
                    )
                )
            output_row_index += 1

        for source_row_index in sorted(row_cells):
            rows.append(_row_dict(block_id, output_row_index, "data", region, len(row_cells) + int(bool(headers))))
            source_cells = row_cells[source_row_index]
            for col_index in range(column_count):
                atom = source_cells.get(col_index)
                cells.append(
                    _cell_dict(
                        block_id,
                        output_row_index,
                        col_index,
                        text=str(atom.text or "") if atom else "",
                        atom=atom,
                        bbox=(atom.bbox if atom and atom.bbox else _cell_bbox(rows[-1].get("bbox"), col_index, column_count)),
                    )
                )
            output_row_index += 1

        return BlockInfo(
            id=block_id,
            type="table",
            role=region.role,
            page_ids=[region.page_id],
            region_ids=[region.id],
            bbox=region.bbox,
            text=_joined_text(region, context),
            content={
                "grid": {
                    "line_source": "evidence_metadata",
                    "columns": columns,
                    "rows": rows,
                    "cells": cells,
                    "implicit_lines": [],
                },
                "continuation": {
                    "table_group_id": f"tblgrp:{region.diagnostics.get('table_id') or region.id}",
                    "part_index": 0,
                    "continued_from": None,
                    "continued_to": None,
                },
            },
            evidence_ids=list(region.evidence_ids),
            confidence=region.confidence,
            quality={
                "column_count": column_count,
                "row_count": len(rows),
                "header_confidence": region.confidence if headers else 0.0,
                "grid_confidence": region.confidence,
                "requires_review": column_count == 0,
                **_table_region_quality(region),
            },
            provenance={
                "reconstructor": self.id,
                "version": "0.1.0",
                "source_table_id": str(region.diagnostics.get("table_id") or ""),
                **_table_region_provenance(region),
            },
        )


def _grid_table_block(
    region: TopologyRegion,
    reconstructor_id: str,
    table: list[list[object]],
    *,
    line_source: str,
) -> BlockInfo:
    block_id = f"blk:table:{_region_suffix(region)}"
    headers = [str(value or "") for value in table[0]] if table else []
    data_rows = table[1:] if len(table) > 1 else []
    column_count = max([len(headers), *[len(row) for row in data_rows], 0])
    columns = [
        {
            "id": f"col:{block_id}:{col_index:04d}",
            "index": col_index,
            "bbox": _column_bbox(region.bbox, col_index, column_count),
            "header": headers[col_index] if col_index < len(headers) else "",
            "data_type": "unknown",
            "confidence": region.confidence,
        }
        for col_index in range(column_count)
    ]
    row_count = len(table)
    rows: list[dict[str, object]] = []
    cells: list[dict[str, object]] = []
    for row_index, row in enumerate(table):
        role = "header" if row_index == 0 and headers else "data"
        rows.append(_row_dict(block_id, row_index, role, region, row_count))
        for col_index in range(column_count):
            text = str(row[col_index] if col_index < len(row) else "")
            cells.append(
                _cell_dict(
                    block_id,
                    row_index,
                    col_index,
                    text=text,
                    atom=None,
                    bbox=_cell_bbox(rows[-1].get("bbox"), col_index, column_count),
                )
            )
    return BlockInfo(
        id=block_id,
        type="table",
        role=region.role,
        page_ids=[region.page_id],
        region_ids=[region.id],
        bbox=region.bbox,
        text="\n".join("\t".join(str(cell or "") for cell in row) for row in table),
        content={
            "grid": {
                "line_source": line_source,
                "columns": columns,
                "rows": rows,
                "cells": cells,
                "implicit_lines": [
                    {"axis": "x", "source": line_source},
                    {"axis": "y", "source": line_source},
                ],
            },
            "continuation": {
                "table_group_id": f"tblgrp:{region.id}",
                "part_index": 0,
                "continued_from": None,
                "continued_to": None,
            },
        },
        evidence_ids=list(region.evidence_ids),
        confidence=region.confidence,
        quality={
            "column_count": column_count,
            "row_count": row_count,
            "header_confidence": region.confidence if headers else 0.0,
            "grid_confidence": region.confidence,
            "requires_review": column_count == 0 or row_count < 2,
            **_table_region_quality(region),
        },
        provenance={
            "reconstructor": reconstructor_id,
            "version": "0.1.0",
            "source_table_id": str(region.diagnostics.get("implicit_table_source") or line_source),
            **_table_region_provenance(region),
        },
    )


def _implicit_table_grid(region: TopologyRegion, context: ReconstructionContext | None = None) -> list[list[object]]:
    table = region.diagnostics.get("implicit_table_grid")
    if not isinstance(table, list) or not all(isinstance(row, list) for row in table):
        return []
    _ = context
    return table


def _table_region_quality(region: TopologyRegion) -> dict[str, object]:
    out: dict[str, object] = {}
    for key in (
        "extraction_confidence",
        "geometry_confidence",
        "ocr_orientation_score",
        "preserve_headers",
        "statement_keywords",
    ):
        value = region.diagnostics.get(key)
        if value not in (None, "", [], {}):
            out[key] = value
    return out


def _table_region_provenance(region: TopologyRegion) -> dict[str, object]:
    mapping = {
        "extraction_layer": "extraction_layer",
        "geometry_source": "geometry_source",
        "coordinate_system": "coordinate_system",
        "ocr_rotation": "ocr_rotation",
        "normalized_page_width": "normalized_page_width",
        "normalized_page_height": "normalized_page_height",
        "role": "source_role",
        "source": "source",
        "page_width": "source_page_width",
        "page_height": "source_page_height",
    }
    out: dict[str, object] = {}
    for source_key, output_key in mapping.items():
        value = region.diagnostics.get(source_key)
        if value not in (None, "", [], {}):
            out[output_key] = value
    return out


def _line_grid_table(region: TopologyRegion, context: ReconstructionContext) -> list[list[object]]:
    line_groups = _line_groups(_region_atoms(region, context))
    table: list[list[object]] = []
    for line_atoms in line_groups:
        if len(line_atoms) >= 2:
            table.append([str(atom.text or "").strip() for atom in line_atoms])
            continue
        text = " ".join(str(atom.text or "") for atom in line_atoms).strip()
        parts = [part for part in re.split(r"\s{2,}|\t+", text) if part.strip()]
        if len(parts) < 2:
            parts = [part for part in text.replace("　", " ").split(" ") if part.strip()]
        if len(parts) >= 2:
            table.append(parts)
    if len(table) < 2:
        return []
    column_count = max(len(row) for row in table)
    if column_count < 2:
        return []
    return [row + [""] * (column_count - len(row)) for row in table]


def _joined_text(region: TopologyRegion, context: ReconstructionContext) -> str:
    return " ".join(context.atom_text.get(atom_id, "") for atom_id in region.evidence_ids).strip()


def _text_block_type(region: TopologyRegion, text: str) -> str:
    if region.kind == "heading":
        return "heading"
    if region.kind == "header":
        return "header"
    if region.kind == "footer":
        return "footer"
    if region.kind == "footnote":
        return "footnote"
    if _list_item_info(text) is not None:
        return "list"
    return "paragraph"


def _list_item_info(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if not stripped:
        return None
    patterns = [
        ("bullet", r"^([-*•])\s+(.+)$"),
        ("ordered", r"^(\d+[.)、．])\s*(.+)$"),
        ("ordered", r"^([一二三四五六七八九十]+[、.．])\s*(.+)$"),
        ("ordered", r"^([（(][一二三四五六七八九十\d]+[)）])\s*(.+)$"),
    ]
    for kind, pattern in patterns:
        match = re.match(pattern, stripped)
        if match is None:
            continue
        return {
            "kind": kind,
            "marker": match.group(1),
            "text": match.group(2).strip(),
            "level": 1,
        }
    return None


def _region_suffix(region: TopologyRegion) -> str:
    return region.id.replace(":", "_")


def _region_atoms(region: TopologyRegion, context: ReconstructionContext) -> list[EvidenceAtom]:
    return [atom for atom_id in region.evidence_ids if (atom := context.atom_by_id.get(atom_id)) is not None]


def _table_atoms(region: TopologyRegion, context: ReconstructionContext) -> list[EvidenceAtom]:
    return [
        atom
        for atom_id in region.evidence_ids
        if (atom := context.atom_by_id.get(atom_id)) is not None and atom.metadata.get("block_type") == "table"
    ]


def _key_value_atoms(region: TopologyRegion, context: ReconstructionContext) -> list[EvidenceAtom]:
    return [
        atom
        for atom_id in region.evidence_ids
        if (atom := context.atom_by_id.get(atom_id)) is not None and atom.metadata.get("block_type") == "key_value"
    ]


def _inferred_key_value_items(region: TopologyRegion, context: ReconstructionContext) -> list[dict[str, object]]:
    if region.role != "document_metadata" and region.diagnostics.get("predicted_kind") != "field_grid":
        return []
    atoms = _region_atoms(region, context)
    line_groups = _line_groups(atoms)
    items: list[dict[str, object]] = []
    for line_atoms in line_groups:
        text = " ".join(str(atom.text or "") for atom in line_atoms).strip()
        parsed = _split_inferred_key_value_text(text)
        if parsed is None:
            continue
        key, raw_value = parsed
        items.append(
            {
                "key": key,
                "value": _typed_value_dict(raw_value, confidence=_mean_confidence(line_atoms)),
                "bbox": _union_bbox([atom.bbox for atom in line_atoms if atom.bbox]),
                "evidence_ids": [atom.id for atom in line_atoms],
            }
        )
    return items


def _line_groups(atoms: list[EvidenceAtom]) -> list[list[EvidenceAtom]]:
    with_bbox = [atom for atom in atoms if atom.bbox]
    if not with_bbox:
        return [[atom] for atom in atoms]
    ordered = sorted(with_bbox, key=lambda atom: (float((atom.bbox or [0, 0, 0, 0])[1]), float((atom.bbox or [0, 0, 0, 0])[0])))
    groups: list[list[EvidenceAtom]] = []
    current: list[EvidenceAtom] = []
    current_y: float | None = None
    for atom in ordered:
        bbox = atom.bbox or [0.0, 0.0, 0.0, 0.0]
        y_center = (float(bbox[1]) + float(bbox[3])) / 2.0
        if current_y is None or abs(y_center - current_y) <= 10.0:
            current.append(atom)
            current_y = y_center if current_y is None else (current_y + y_center) / 2.0
            continue
        groups.append(sorted(current, key=lambda item: float((item.bbox or [0, 0, 0, 0])[0])))
        current = [atom]
        current_y = y_center
    if current:
        groups.append(sorted(current, key=lambda item: float((item.bbox or [0, 0, 0, 0])[0])))
    return groups


def _split_inferred_key_value_text(text: str) -> tuple[str, str] | None:
    stripped = text.strip()
    if not stripped:
        return None
    key, value = _split_key_value_text(stripped)
    if key and value:
        return key, value
    match = re.match(r"^(.{2,24}?)[\s　]{2,}(.{1,80})$", stripped)
    if match is None:
        match = re.match(r"^([^\d\s:：]{2,16})\s+([A-Za-z0-9\u4e00-\u9fff].{0,80})$", stripped)
    if match is None:
        return None
    key = match.group(1).strip(" ：:")
    value = match.group(2).strip()
    if not key or not value or len(key) > 24:
        return None
    return key, value


def _mean_confidence(atoms: list[EvidenceAtom]) -> float:
    if not atoms:
        return 0.0
    return sum(float(atom.confidence or 0.0) for atom in atoms) / len(atoms)


def _union_bbox(bboxes: list[list[float] | None]) -> list[float] | None:
    values = [bbox for bbox in bboxes if bbox and len(bbox) == 4]
    if not values:
        return None
    return [
        min(float(bbox[0]) for bbox in values),
        min(float(bbox[1]) for bbox in values),
        max(float(bbox[2]) for bbox in values),
        max(float(bbox[3]) for bbox in values),
    ]


def _split_key_value_text(text: str) -> tuple[str, str]:
    if ":" in text:
        key, value = text.split(":", 1)
        return key.strip(), value.strip()
    if "：" in text:
        key, value = text.split("：", 1)
        return key.strip(), value.strip()
    return "", text.strip()


def _typed_value_dict(raw: object, *, confidence: float) -> dict[str, object]:
    text = str(raw or "")
    stripped = text.replace(",", "").strip()
    normalized: object = text
    value_type = "string"
    if not stripped:
        value_type = "empty"
        normalized = ""
    else:
        try:
            normalized = float(stripped)
            value_type = "number"
        except ValueError:
            value_type = "date" if _looks_like_date(stripped) else "string"
    return {
        "raw": text,
        "normalized": normalized,
        "type": value_type,
        "confidence": confidence,
    }


def _looks_like_date(text: str) -> bool:
    if len(text) != 10:
        return False
    return text[4] in {"-", "/"} and text[7] in {"-", "/"} and text[:4].isdigit()


def _headers(atoms: list[EvidenceAtom]) -> list[str]:
    headers_by_index = {
        int(atom.metadata["header_index"]): str(atom.text or "")
        for atom in atoms
        if "header_index" in atom.metadata
    }
    if not headers_by_index:
        return []
    return [headers_by_index.get(idx, "") for idx in range(max(headers_by_index) + 1)]


def _header_atom(atoms: list[EvidenceAtom], col_index: int) -> EvidenceAtom | None:
    for atom in atoms:
        if atom.metadata.get("header_index") == col_index:
            return atom
    return None


def _row_cells(atoms: list[EvidenceAtom]) -> dict[int, dict[int, EvidenceAtom]]:
    rows: dict[int, dict[int, EvidenceAtom]] = {}
    for atom in atoms:
        if "row_index" not in atom.metadata or "col_index" not in atom.metadata:
            continue
        try:
            row_index = int(atom.metadata["row_index"])
            col_index = int(atom.metadata["col_index"])
        except (TypeError, ValueError):
            continue
        rows.setdefault(row_index, {})[col_index] = atom
    return rows


def _row_dict(
    block_id: str,
    row_index: int,
    role: str,
    region: TopologyRegion,
    row_count: int,
) -> dict[str, object]:
    return {
        "id": f"row:{block_id}:{row_index:04d}",
        "index": row_index,
        "role": role,
        "bbox": _row_bbox(region.bbox, row_index, row_count),
        "confidence": region.confidence,
    }


def _cell_dict(
    block_id: str,
    row_index: int,
    col_index: int,
    *,
    text: str,
    atom: EvidenceAtom | None,
    bbox: object,
) -> dict[str, object]:
    evidence_ids = [atom.id] if atom else []
    confidence = atom.confidence if atom else 0.5
    return {
        "id": f"cell:{block_id}:{row_index:04d}:{col_index:04d}",
        "row": row_index,
        "col": col_index,
        "row_span": 1,
        "col_span": 1,
        "text": text,
        "value": _typed_value_dict(text, confidence=confidence),
        "bbox": bbox,
        "evidence_ids": evidence_ids,
        "confidence": confidence,
    }


def _column_bbox(table_bbox: list[float] | None, col_index: int, column_count: int) -> list[float] | None:
    if not table_bbox or column_count <= 0:
        return None
    width = (table_bbox[2] - table_bbox[0]) / column_count
    return [
        table_bbox[0] + width * col_index,
        table_bbox[1],
        table_bbox[0] + width * (col_index + 1),
        table_bbox[3],
    ]


def _row_bbox(table_bbox: list[float] | None, row_index: int, row_count: int) -> list[float] | None:
    if not table_bbox or row_count <= 0:
        return None
    height = (table_bbox[3] - table_bbox[1]) / row_count
    return [
        table_bbox[0],
        table_bbox[1] + height * row_index,
        table_bbox[2],
        table_bbox[1] + height * (row_index + 1),
    ]


def _cell_bbox(row_bbox: object, col_index: int, column_count: int) -> list[float] | None:
    if not isinstance(row_bbox, list) or len(row_bbox) != 4 or column_count <= 0:
        return None
    width = (row_bbox[2] - row_bbox[0]) / column_count
    return [
        row_bbox[0] + width * col_index,
        row_bbox[1],
        row_bbox[0] + width * (col_index + 1),
        row_bbox[3],
    ]


__all__ = [
    "CoverRegionReconstructor",
    "FinancialStatementReconstructor",
    "ReconstructionContext",
    "KeyValueGroupRegionReconstructor",
    "RegionReconstructor",
    "RegionReconstructorRegistry",
    "ResidualRegionReconstructor",
    "TableLikeRegionReconstructor",
    "TextRegionReconstructor",
    "TocRegionReconstructor",
    "VisualRegionReconstructor",
]
