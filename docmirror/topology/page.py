# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""UDTR Page Topology builder.

This first topology pass groups page-scoped evidence atoms into conservative
regions. It guarantees ownership and a reading-order skeleton so downstream
reconstructors have stable inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from docmirror.evidence.plane import EvidencePage, EvidencePlane
from docmirror.models.mirror.vnext import EvidenceAtom
from docmirror.topology.region_graph import produce_region_candidates, solve_region_graph


@dataclass
class TopologyRegion:
    id: str
    page_id: str
    kind: str
    role: str
    bbox: list[float] | None
    evidence_ids: list[str] = field(default_factory=list)
    reading_order: int = 0
    confidence: float = 1.0
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageTopology:
    page_id: str
    page_index: int
    page_number: int
    regions: list[TopologyRegion] = field(default_factory=list)
    residual_region_ids: list[str] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DocumentTopology:
    pages: list[PageTopology] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        regions = [region for page in self.pages for region in page.regions]
        return {
            "pages": len(self.pages),
            "regions": len(regions),
            "image_regions": sum(1 for region in regions if region.kind == "image"),
            "figure_regions": sum(1 for region in regions if region.kind == "figure"),
            "seal_regions": sum(1 for region in regions if region.kind == "seal"),
            "signature_regions": sum(1 for region in regions if region.kind == "signature"),
            "header_regions": sum(1 for region in regions if region.kind == "header"),
            "footer_regions": sum(1 for region in regions if region.kind == "footer"),
            "footnote_regions": sum(1 for region in regions if region.kind == "footnote"),
            "notice_regions": sum(1 for region in regions if region.role in {"notice", "legal_notice"}),
            "table_like_regions": sum(1 for region in regions if region.kind == "table_like"),
            "key_value_regions": sum(1 for region in regions if region.role == "document_metadata"),
            "residual_regions": sum(1 for region in regions if region.kind == "residual"),
            "bundle_regions": sum(1 for region in regions if str(region.diagnostics.get("grouping", "")).startswith("page_evidence_bundle")),
            "page_canvas_regions": sum(1 for region in regions if region.diagnostics.get("grouping") == "page_canvas_region"),
            "segment_regions": sum(1 for region in regions if region.diagnostics.get("grouping") == "segment_page_blocks"),
            "implicit_grid_regions": sum(1 for region in regions if region.diagnostics.get("grouping") == "implicit_grid_text_atoms"),
            "overlap_warnings": sum(
                1
                for page in self.pages
                for diagnostic in page.diagnostics
                if diagnostic.get("type") == "region_overlap"
            ),
        }

    def diagnostics_entry(self) -> dict[str, Any]:
        page_diagnostics = [
            {
                "page_id": page.page_id,
                "page_number": page.page_number,
                **diagnostic,
            }
            for page in self.pages
            for diagnostic in page.diagnostics
        ]
        return {
            "stage": "page_topology_segmentation",
            "status": "ok",
            "counts": self.counts,
            "diagnostics": [*self.diagnostics, *page_diagnostics],
        }


class PageTopologyBuilder:
    """Build conservative page topology from an EvidencePlane."""

    def __init__(
        self,
        *,
        line_gap_tolerance: float = 8.0,
        table_surrounding_gap: float = 96.0,
        header_footer_band_ratio: float = 0.08,
        region_overlap_threshold: float = 0.15,
    ) -> None:
        self.line_gap_tolerance = line_gap_tolerance
        self.table_surrounding_gap = table_surrounding_gap
        self.header_footer_band_ratio = header_footer_band_ratio
        self.region_overlap_threshold = region_overlap_threshold

    def build(self, evidence_plane: EvidencePlane) -> DocumentTopology:
        atom_by_id = _atom_index(evidence_plane)
        text_atom_ids = {atom.id for atom in evidence_plane.evidence.text_atoms}
        visual_atom_ids = {atom.id for atom in evidence_plane.evidence.visual_atoms}
        image_atom_ids = {atom.id for atom in evidence_plane.evidence.image_atoms}
        vector_atom_ids = {atom.id for atom in evidence_plane.evidence.vector_atoms}
        page_canvas_by_number = _page_canvas_by_number(evidence_plane.source.provenance)
        page_bundle_by_number = _page_bundle_by_number(evidence_plane.source.provenance)
        topologies: list[PageTopology] = []
        diagnostics: list[dict[str, Any]] = []

        for page in evidence_plane.pages:
            page_topology = PageTopology(
                page_id=page.page_id,
                page_index=page.page_index,
                page_number=page.page_number,
            )
            page_atoms = [atom_by_id[atom_id] for atom_id in page.evidence_ids if atom_id in atom_by_id]
            table_atoms = [
                atom
                for atom in page_atoms
                if atom.id in text_atom_ids and atom.text and atom.metadata.get("block_type") == "table"
            ]
            key_value_atoms = [
                atom
                for atom in page_atoms
                if atom.id in text_atom_ids and atom.text and atom.metadata.get("block_type") == "key_value"
            ]
            text_atoms = [
                atom
                for atom in page_atoms
                if atom.id in text_atom_ids
                and atom.text
                and atom.metadata.get("block_type") not in {"key_value", "table"}
            ]
            visual_atoms = [atom for atom in page_atoms if atom.id in visual_atom_ids]
            image_atoms = [atom for atom in page_atoms if atom.id in image_atom_ids]
            vector_atoms = [atom for atom in page_atoms if atom.id in vector_atom_ids]
            owned: set[str] = set()

            visual_artifact_regions = self._visual_artifact_regions(page, visual_atoms)
            for region in visual_artifact_regions:
                owned.update(region.evidence_ids)
            page_topology.regions.extend(visual_artifact_regions)

            image_regions = self._image_regions(page, image_atoms)
            for region in image_regions:
                owned.update(region.evidence_ids)
            page_topology.regions.extend(image_regions)

            figure_regions = self._figure_regions(page, vector_atoms)
            for region in figure_regions:
                owned.update(region.evidence_ids)
            page_topology.regions.extend(figure_regions)

            table_regions = self._table_regions(page, table_atoms)
            for region in table_regions:
                owned.update(region.evidence_ids)
            page_topology.regions.extend(table_regions)

            key_value_regions = self._key_value_regions(page, key_value_atoms)
            for region in key_value_regions:
                owned.update(region.evidence_ids)
            page_topology.regions.extend(key_value_regions)

            bundle_regions = self._page_bundle_regions(
                page,
                page_bundle_by_number.get(page.page_number),
                text_atoms,
                skip_table_candidates=bool(table_regions),
            )
            bundle_evidence_ids = {evidence_id for region in bundle_regions for evidence_id in region.evidence_ids}
            for region in bundle_regions:
                owned.update(region.evidence_ids)
            page_topology.regions.extend(bundle_regions)
            if bundle_evidence_ids:
                text_atoms = [atom for atom in text_atoms if atom.id not in bundle_evidence_ids]

            page_canvas_regions = self._page_canvas_regions(
                page,
                page_canvas_by_number.get(page.page_number),
                text_atoms,
                skip_table_candidates=bool(table_regions),
            )
            page_canvas_evidence_ids = {evidence_id for region in page_canvas_regions for evidence_id in region.evidence_ids}
            for region in page_canvas_regions:
                owned.update(region.evidence_ids)
            page_topology.regions.extend(page_canvas_regions)
            if page_canvas_evidence_ids:
                text_atoms = [atom for atom in text_atoms if atom.id not in page_canvas_evidence_ids]

            segment_regions = self._segment_page_block_regions(page, text_atoms, skip_table_candidates=bool(table_regions))
            segment_evidence_ids = {evidence_id for region in segment_regions for evidence_id in region.evidence_ids}
            for region in segment_regions:
                owned.update(region.evidence_ids)
            page_topology.regions.extend(segment_regions)
            if segment_evidence_ids:
                text_atoms = [atom for atom in text_atoms if atom.id not in segment_evidence_ids]

            implicit_table_regions = self._implicit_table_regions(page, text_atoms) if not table_regions else []
            implicit_table_evidence_ids = {evidence_id for region in implicit_table_regions for evidence_id in region.evidence_ids}
            for region in implicit_table_regions:
                owned.update(region.evidence_ids)
            page_topology.regions.extend(implicit_table_regions)
            if implicit_table_evidence_ids:
                text_atoms = [atom for atom in text_atoms if atom.id not in implicit_table_evidence_ids]

            text_regions = self._text_regions(page, text_atoms)
            for region in text_regions:
                owned.update(region.evidence_ids)
            page_topology.regions.extend(text_regions)

            residual_atoms = [atom for atom in page_atoms if atom.id not in owned]
            if residual_atoms or not page_topology.regions:
                residual_region = self._residual_region(page, residual_atoms, reading_order=len(page_topology.regions) + 1)
                page_topology.regions.append(residual_region)
                page_topology.residual_region_ids.append(residual_region.id)

            page_topology.regions = _assign_reading_order(page_topology.regions)
            self._classify_toc_text(page_topology, atom_by_id)
            self._classify_header_footer_text(page, page_topology)
            self._classify_heading_text(page_topology, atom_by_id)
            self._classify_table_surrounding_text(page_topology)
            self._classify_notice_footnote_text(page_topology, atom_by_id)
            self._annotate_region_overlaps(page_topology)
            candidate_batch = produce_region_candidates(page_id=page.page_id, regions=page_topology.regions)
            region_graph = solve_region_graph(
                page_id=page.page_id,
                regions=page_topology.regions,
                all_evidence_ids=[atom.id for atom in page_atoms],
                candidates=candidate_batch.candidates,
                candidate_diagnostics=candidate_batch.diagnostics,
                evidence_by_id=atom_by_id,
            )
            _apply_region_graph_diagnostics(page_topology, region_graph.to_diagnostics())
            if not page_atoms:
                page_topology.diagnostics.append({"severity": "warning", "message": "page has no evidence atoms"})
            topologies.append(page_topology)

        self._classify_repeated_header_footer_text(evidence_plane, topologies, atom_by_id)

        if not topologies:
            diagnostics.append({"severity": "warning", "message": "evidence plane has no pages"})

        return DocumentTopology(pages=topologies, diagnostics=diagnostics)

    def _visual_artifact_regions(self, page: EvidencePage, atoms: list[EvidenceAtom]) -> list[TopologyRegion]:
        regions: list[TopologyRegion] = []
        for idx, atom in enumerate(atoms, start=1):
            kind = _visual_artifact_kind(atom)
            if kind is None:
                continue
            regions.append(
                TopologyRegion(
                    id=f"reg:{page.page_number:04d}:{kind}:{idx:04d}",
                    page_id=page.page_id,
                    kind=kind,
                    role=kind,
                    bbox=atom.bbox,
                    evidence_ids=[atom.id],
                    reading_order=idx,
                    confidence=atom.confidence,
                    diagnostics={
                        "grouping": "visual_artifact_region",
                        "source_kind": atom.source_kind,
                    },
                )
            )
        return regions

    def _image_regions(self, page: EvidencePage, atoms: list[EvidenceAtom]) -> list[TopologyRegion]:
        regions: list[TopologyRegion] = []
        for idx, atom in enumerate(atoms, start=1):
            regions.append(
                TopologyRegion(
                    id=f"reg:{page.page_number:04d}:image:{idx:04d}",
                    page_id=page.page_id,
                    kind="image",
                    role=str(atom.metadata.get("role") or atom.kind or "embedded_image"),
                    bbox=atom.bbox,
                    evidence_ids=[atom.id],
                    reading_order=idx,
                    confidence=atom.confidence,
                    diagnostics={
                        "grouping": "image_atom_region",
                        "source_kind": atom.source_kind,
                    },
                )
            )
        return regions

    def _figure_regions(self, page: EvidencePage, atoms: list[EvidenceAtom]) -> list[TopologyRegion]:
        if not atoms:
            return []
        return [
            TopologyRegion(
                id=f"reg:{page.page_number:04d}:figure:0001",
                page_id=page.page_id,
                kind="figure",
                role="vector_graphics",
                bbox=_union_bbox([atom.bbox for atom in atoms if atom.bbox]),
                evidence_ids=[atom.id for atom in atoms],
                reading_order=1,
                confidence=_average_confidence(atoms),
                diagnostics={
                    "grouping": "vector_atom_group",
                    "atom_count": len(atoms),
                },
            )
        ]

    def _key_value_regions(self, page: EvidencePage, atoms: list[EvidenceAtom]) -> list[TopologyRegion]:
        if not atoms:
            return []
        return [
            TopologyRegion(
                id=f"reg:{page.page_number:04d}:kv:0001",
                page_id=page.page_id,
                kind="text",
                role="document_metadata",
                bbox=_union_bbox([atom.bbox for atom in atoms if atom.bbox]),
                evidence_ids=[atom.id for atom in atoms],
                reading_order=1,
                confidence=_average_confidence(atoms),
                diagnostics={"grouping": "key_value_metadata_group", "atom_count": len(atoms)},
            )
        ]

    def _table_regions(self, page: EvidencePage, atoms: list[EvidenceAtom]) -> list[TopologyRegion]:
        if not atoms:
            return []

        table_ids: dict[str, list[EvidenceAtom]] = {}
        for atom in atoms:
            table_id = str(atom.metadata.get("table_id") or "unknown")
            table_ids.setdefault(table_id, []).append(atom)

        regions: list[TopologyRegion] = []
        for idx, (table_id, table_atoms) in enumerate(table_ids.items(), start=1):
            bbox = _metadata_bbox(table_atoms, "table_bbox") or _union_bbox([atom.bbox for atom in table_atoms if atom.bbox])
            table_provenance = _table_region_provenance(table_atoms)
            regions.append(
                TopologyRegion(
                    id=f"reg:{page.page_number:04d}:table:{idx:04d}",
                    page_id=page.page_id,
                    kind="table_like",
                    role="table",
                    bbox=bbox,
                    evidence_ids=[atom.id for atom in table_atoms],
                    reading_order=idx,
                    confidence=0.9 if bbox else 0.7,
                    diagnostics={
                        "grouping": "table_metadata_group",
                        "table_id": table_id,
                        "atom_count": len(table_atoms),
                        **table_provenance,
                    },
                )
            )
        return regions

    def _text_regions(self, page: EvidencePage, atoms: list[EvidenceAtom]) -> list[TopologyRegion]:
        if not atoms:
            return []
        with_bbox = [atom for atom in atoms if atom.bbox]
        if not with_bbox:
            line_regions = _no_bbox_line_regions(page, atoms)
            if line_regions:
                return line_regions
            kind, role = _text_region_kind_role(atoms)
            return [
                TopologyRegion(
                    id=f"reg:{page.page_number:04d}:0001",
                    page_id=page.page_id,
                    kind=kind,
                    role=role,
                    bbox=None,
                    evidence_ids=[atom.id for atom in atoms],
                    reading_order=1,
                    confidence=0.65,
                    diagnostics={"grouping": "no_bbox_all_text"},
                )
            ]

        sorted_atoms = sorted(with_bbox, key=lambda atom: ((atom.bbox or [0, 0, 0, 0])[1], (atom.bbox or [0, 0, 0, 0])[0]))
        lines: list[list[EvidenceAtom]] = []
        current: list[EvidenceAtom] = []
        current_y: float | None = None
        for atom in sorted_atoms:
            y0 = float((atom.bbox or [0, 0, 0, 0])[1])
            if current_y is None or abs(y0 - current_y) <= self.line_gap_tolerance:
                current.append(atom)
                current_y = y0 if current_y is None else (current_y + y0) / 2.0
            else:
                lines.append(current)
                current = [atom]
                current_y = y0
        if current:
            lines.append(current)

        regions: list[TopologyRegion] = []
        for idx, line_atoms in enumerate(lines, start=1):
            kind, role = _text_region_kind_role(line_atoms)
            regions.append(
                TopologyRegion(
                    id=f"reg:{page.page_number:04d}:{idx:04d}",
                    page_id=page.page_id,
                    kind=kind,
                    role=role,
                    bbox=_union_bbox([atom.bbox for atom in line_atoms if atom.bbox]),
                    evidence_ids=[atom.id for atom in line_atoms],
                    reading_order=idx,
                    confidence=0.85,
                    diagnostics={"grouping": "bbox_line_cluster"},
                )
            )
        return regions

    def _page_bundle_regions(
        self,
        page: EvidencePage,
        bundle: dict[str, Any] | None,
        atoms: list[EvidenceAtom],
        *,
        skip_table_candidates: bool,
    ) -> list[TopologyRegion]:
        if not isinstance(bundle, dict):
            return []
        regions: list[TopologyRegion] = []
        claimed_ids: set[str] = set()
        if not skip_table_candidates:
            for idx, grid in enumerate(bundle.get("micro_grid_structures") or [], start=1):
                if not isinstance(grid, dict):
                    continue
                bbox = _bbox(grid.get("bbox"))
                if not bbox:
                    continue
                region_atoms = [atom for atom in atoms if atom.id not in claimed_ids and _atom_center_in_bbox(atom, bbox)]
                if not region_atoms:
                    continue
                claimed_ids.update(atom.id for atom in region_atoms)
                diagnostics = {
                    "grouping": "page_evidence_bundle_micro_grid",
                    "grid_id": grid.get("grid_id", ""),
                    "schema_hint": grid.get("grid_type_hint", ""),
                    "implicit_table_grid": _grid_rows_from_micro_grid(grid),
                    "implicit_table_source": "page_evidence_bundle_micro_grid",
                }
                regions.append(
                    TopologyRegion(
                        id=f"reg:{page.page_number:04d}:bundle:grid:{idx:04d}",
                        page_id=page.page_id,
                        kind="table_like",
                        role="table_candidate",
                        bbox=bbox,
                        evidence_ids=[atom.id for atom in region_atoms],
                        reading_order=idx,
                        confidence=_confidence(grid.get("confidence", 0.76)),
                        diagnostics=diagnostics,
                    )
                )

        local_evidence = bundle.get("local_structure_evidence")
        structures = local_evidence.get("structures") if isinstance(local_evidence, dict) else None
        if isinstance(structures, list):
            for idx, structure in enumerate(structures, start=1):
                if not isinstance(structure, dict):
                    continue
                bbox = _bbox(structure.get("bbox"))
                if not bbox:
                    continue
                region_atoms = [atom for atom in atoms if atom.id not in claimed_ids and _atom_center_in_bbox(atom, bbox)]
                if not region_atoms:
                    continue
                claimed_ids.update(atom.id for atom in region_atoms)
                regions.append(
                    TopologyRegion(
                        id=f"reg:{page.page_number:04d}:bundle:field:{idx:04d}",
                        page_id=page.page_id,
                        kind="text",
                        role="document_metadata",
                        bbox=bbox,
                        evidence_ids=[atom.id for atom in region_atoms],
                        reading_order=len(regions) + 1,
                        confidence=_confidence(structure.get("confidence", structure.get("score", 0.72))),
                        diagnostics={
                            "grouping": "page_evidence_bundle_local_structure",
                            "structure_id": structure.get("structure_id", structure.get("candidate_id", "")),
                            "schema_hint": structure.get("schema_hint", ""),
                        },
                    )
                )
        return regions

    def _page_canvas_regions(
        self,
        page: EvidencePage,
        page_canvas: dict[str, Any] | None,
        atoms: list[EvidenceAtom],
        *,
        skip_table_candidates: bool,
    ) -> list[TopologyRegion]:
        if not isinstance(page_canvas, dict):
            return []
        raw_regions = page_canvas.get("regions")
        if not isinstance(raw_regions, list):
            return []
        regions: list[TopologyRegion] = []
        claimed_ids: set[str] = set()
        for idx, raw_region in enumerate(raw_regions, start=1):
            if not isinstance(raw_region, dict):
                continue
            bbox = _bbox(raw_region.get("bbox"))
            if not bbox:
                continue
            kind, role = _page_canvas_region_kind_role(raw_region)
            if kind == "table_like" and skip_table_candidates:
                continue
            region_atoms = [
                atom
                for atom in atoms
                if atom.id not in claimed_ids and _atom_center_in_bbox(atom, bbox)
            ]
            if not region_atoms:
                continue
            claimed_ids.update(atom.id for atom in region_atoms)
            diagnostics: dict[str, Any] = {
                "grouping": "page_canvas_region",
                "page_canvas_region_id": raw_region.get("region_id", ""),
                "page_canvas_kind": raw_region.get("kind", ""),
                "page_canvas_morphology": raw_region.get("morphology", ""),
                "anchor_text": raw_region.get("anchor_text", ""),
            }
            regions.append(
                TopologyRegion(
                    id=f"reg:{page.page_number:04d}:canvas:{idx:04d}",
                    page_id=page.page_id,
                    kind=kind,
                    role=role,
                    bbox=bbox,
                    evidence_ids=[atom.id for atom in region_atoms],
                    reading_order=idx,
                    confidence=_confidence(raw_region.get("confidence", 0.65)),
                    diagnostics=diagnostics,
                )
            )
        return regions

    def _segment_page_block_regions(
        self,
        page: EvidencePage,
        atoms: list[EvidenceAtom],
        *,
        skip_table_candidates: bool,
    ) -> list[TopologyRegion]:
        line_groups = _line_groups_from_atoms(atoms, tolerance=max(self.line_gap_tolerance, 10.0))
        if len(line_groups) < 3:
            return []
        try:
            from docmirror.ocr.page_canvas.page_segment import segment_page_blocks
        except Exception:
            return []

        line_items = [_line_item_from_group(page, idx, group) for idx, group in enumerate(line_groups)]
        tokens = _ocr_tokens_from_atoms(atoms, page_number=page.page_number)
        try:
            blocks = segment_page_blocks(
                line_items,
                tokens=tokens,
                page=page.page_number,
                page_width=page.width,
                page_height=page.height,
                gap_threshold=32.0,
            )
        except Exception:
            return []

        regions: list[TopologyRegion] = []
        claimed_ids: set[str] = set()
        for idx, block in enumerate(blocks, start=1):
            predicted_kind = str(getattr(block, "predicted_kind", "") or "")
            if predicted_kind == "micro_grid" and skip_table_candidates:
                continue
            if predicted_kind not in {"micro_grid", "field_grid"}:
                continue
            score = float(getattr(block, "score", 0.0) or 0.0)
            if score < 0.55:
                continue
            block_line_indices = [int(value) for value in getattr(block, "line_indices", ()) or ()]
            block_atoms = [
                atom
                for line_index in block_line_indices
                if 0 <= line_index < len(line_groups)
                for atom in line_groups[line_index]
                if atom.id not in claimed_ids
            ]
            if not block_atoms:
                continue
            claimed_ids.update(atom.id for atom in block_atoms)
            kind = "table_like" if predicted_kind == "micro_grid" else "text"
            role = "table_candidate" if predicted_kind == "micro_grid" else "document_metadata"
            diagnostics: dict[str, Any] = {
                "grouping": "segment_page_blocks",
                "predicted_kind": predicted_kind,
                "reason_codes": list(getattr(block, "reason_codes", ()) or ()),
                "anchor_text": str(getattr(block, "anchor_text", "") or ""),
                "grid_score": float(getattr(block, "grid_score", 0.0) or 0.0),
                "field_score": float(getattr(block, "field_score", 0.0) or 0.0),
            }
            if predicted_kind == "micro_grid":
                grid = _table_grid_from_tokens(tokens, block.bbox, page_height=page.height)
                if grid:
                    diagnostics["implicit_table_grid"] = grid
                    diagnostics["implicit_table_source"] = "segment_page_blocks+grid_legacy_tokens"
            regions.append(
                TopologyRegion(
                    id=f"reg:{page.page_number:04d}:segment:{idx:04d}",
                    page_id=page.page_id,
                    kind=kind,
                    role=role,
                    bbox=[float(value) for value in getattr(block, "bbox", ())],
                    evidence_ids=[atom.id for atom in block_atoms],
                    reading_order=idx,
                    confidence=score,
                    diagnostics=diagnostics,
                )
            )
        return regions

    def _implicit_table_regions(self, page: EvidencePage, atoms: list[EvidenceAtom]) -> list[TopologyRegion]:
        candidates = [atom for atom in atoms if atom.bbox and atom.text]
        if len(candidates) < 12:
            return []
        try:
            from docmirror.tables.char.grid_reconstructor import detect_table_via_grid
        except Exception:
            return []

        wrapper = _EvidencePagePlum(candidates)
        try:
            table = detect_table_via_grid(wrapper)
        except Exception:
            return []
        if not table or len(table) < 2 or len(table[0]) < 3:
            return []

        bbox = _union_bbox([atom.bbox for atom in candidates if atom.bbox])
        return [
            TopologyRegion(
                id=f"reg:{page.page_number:04d}:table:implicit:0001",
                page_id=page.page_id,
                kind="table_like",
                role="table",
                bbox=bbox,
                evidence_ids=[atom.id for atom in candidates],
                reading_order=1,
                confidence=0.72,
                diagnostics={
                    "grouping": "implicit_grid_text_atoms",
                    "implicit_table_grid": table,
                    "implicit_table_source": "grid_reconstructor",
                    "atom_count": len(candidates),
                },
            )
        ]

    def _residual_region(
        self,
        page: EvidencePage,
        atoms: list[EvidenceAtom],
        *,
        reading_order: int,
    ) -> TopologyRegion:
        is_empty = not atoms
        role = "unassigned_evidence"
        reason = "unassigned_evidence"
        if is_empty:
            if page.content_mode in ("scanned_ocr", "unknown"):
                role = "scanned_blank_page"
                reason = "scanned_page_no_text_content" if page.content_mode == "scanned_ocr" else "no_evidence_atoms_unknown_source"
            else:
                role = "empty_page"
                reason = "no_evidence_atoms"
        return TopologyRegion(
            id=f"reg:{page.page_number:04d}:{reading_order:04d}",
            page_id=page.page_id,
            kind="residual",
            role=role,
            bbox=_union_bbox([atom.bbox for atom in atoms if atom.bbox]) or _page_bbox(page),
            evidence_ids=[atom.id for atom in atoms],
            reading_order=reading_order,
            confidence=1.0 if atoms else 0.8,
            diagnostics={"reason": reason},
        )

    def _classify_table_surrounding_text(self, page_topology: PageTopology) -> None:
        table_regions = [region for region in page_topology.regions if region.kind == "table_like" and region.bbox]
        if not table_regions:
            return

        for region in page_topology.regions:
            if region.kind != "text" or region.role != "body" or not region.bbox:
                continue
            relation = _nearest_table_relation(region, table_regions, max_gap=self.table_surrounding_gap)
            if relation is None:
                continue
            role, table_region, gap = relation
            region.role = role
            region.diagnostics = {
                **region.diagnostics,
                "surrounding_table_region_id": table_region.id,
                "surrounding_table_gap": gap,
            }

    def _classify_header_footer_text(self, page: EvidencePage, page_topology: PageTopology) -> None:
        if page.height is None:
            return
        band_height = float(page.height) * self.header_footer_band_ratio
        for region in page_topology.regions:
            if region.kind != "text" or region.role != "body" or not region.bbox:
                continue
            if region.bbox[3] <= band_height:
                region.kind = "header"
                region.role = "page_header"
                region.diagnostics = {**region.diagnostics, "classification": "top_page_band"}
            elif region.bbox[1] >= float(page.height) - band_height:
                region.kind = "footer"
                region.role = "page_footer"
                region.diagnostics = {**region.diagnostics, "classification": "bottom_page_band"}

    def _classify_repeated_header_footer_text(
        self,
        evidence_plane: EvidencePlane,
        topologies: list[PageTopology],
        atom_by_id: dict[str, EvidenceAtom],
    ) -> None:
        page_by_id = {page.page_id: page for page in evidence_plane.pages}
        groups: dict[tuple[str, str], list[TopologyRegion]] = {}
        for page_topology in topologies:
            page = page_by_id.get(page_topology.page_id)
            if page is None or page.height is None:
                continue
            loose_band = float(page.height) * 0.18
            for region in page_topology.regions:
                if region.kind not in {"text", "header", "footer"} or region.role not in {"body", "page_header", "page_footer"}:
                    continue
                if not region.bbox:
                    continue
                text_key = _normalize_repeated_text(_region_text(region, atom_by_id))
                if not text_key:
                    continue
                side = ""
                if region.bbox[3] <= loose_band:
                    side = "header"
                elif region.bbox[1] >= float(page.height) - loose_band:
                    side = "footer"
                if side:
                    groups.setdefault((side, text_key), []).append(region)

        for (side, _text_key), regions in groups.items():
            page_ids = {region.page_id for region in regions}
            if len(page_ids) < 2:
                continue
            for region in regions:
                region.kind = side
                region.role = f"page_{side}"
                region.diagnostics = {
                    **region.diagnostics,
                    "classification": f"repeated_{side}_text",
                    "repeated_page_count": len(page_ids),
                }

    def _classify_toc_text(self, page_topology: PageTopology, atom_by_id: dict[str, EvidenceAtom]) -> None:
        for region in page_topology.regions:
            if region.kind not in {"heading", "text"}:
                continue
            text = _region_text(region, atom_by_id)
            if _is_toc_title(text):
                region.kind = "heading"
                region.role = "toc_title"
                region.diagnostics = {**region.diagnostics, "classification": "toc_title"}
                continue
            toc_entry = _parse_toc_entry(text)
            if toc_entry is None:
                continue
            title, target_page = toc_entry
            region.kind = "text"
            region.role = "toc_entry"
            region.diagnostics = {
                **region.diagnostics,
                "classification": "toc_entry",
                "toc_title": title,
                "toc_target_page": target_page,
            }

    def _classify_heading_text(self, page_topology: PageTopology, atom_by_id: dict[str, EvidenceAtom]) -> None:
        for region in page_topology.regions:
            if region.kind != "text" or region.role != "body":
                continue
            text = _region_text(region, atom_by_id)
            level = _heading_level_from_text(text)
            if level is not None:
                region.kind = "heading"
                region.role = level
                region.diagnostics = {**region.diagnostics, "classification": "heading_pattern"}
                continue
            # Bank statement / account identity patterns
            if _is_account_identity_text(text):
                region.kind = "heading"
                region.role = "document_header"
                region.diagnostics = {**region.diagnostics, "classification": "account_identity"}

    def _classify_notice_footnote_text(
        self,
        page_topology: PageTopology,
        atom_by_id: dict[str, EvidenceAtom],
    ) -> None:
        for region in page_topology.regions:
            if region.kind != "text" or region.role not in {"body", "table_preamble", "table_postamble"}:
                continue
            text = _region_text(region, atom_by_id)
            if not text:
                continue
            if _is_table_summary_text(text) and region.diagnostics.get("surrounding_table_region_id"):
                kv = _extract_summary_kv(text)
                if kv:
                    region.diagnostics = {**region.diagnostics, "classification": "table_summary",
                                          "summary_fields": kv}
                region.role = "table_summary"
                continue
            if _is_footnote_text(text):
                region.kind = "footnote"
                region.role = "table_footnote" if region.diagnostics.get("surrounding_table_region_id") else "footnote"
                region.diagnostics = {**region.diagnostics, "classification": "footnote"}
                continue
            if _is_notice_text(text):
                cleaned = _clean_notice_text(text)
                if cleaned and cleaned != text:
                    region.diagnostics = {**region.diagnostics, "clean_text": cleaned}
                region.role = "legal_notice"
                region.diagnostics = {**region.diagnostics, "classification": "legal_notice"}

    _REGION_CONFLICT_PRIORITY: dict[str, int] = {
        "table_like": 10, "seal": 9, "signature": 8, "heading": 7,
        "figure": 6, "image": 5, "text": 4, "document_metadata": 3,
        "header": 2, "footer": 2, "footnote": 2, "toc": 1,
        "residual": 0, "unknown": 0,
    }

    def _annotate_region_overlaps(self, page_topology: PageTopology) -> None:
        regions = [region for region in page_topology.regions if region.bbox and _bbox_area(region.bbox) > 0.0]
        for idx, left in enumerate(regions):
            for right in regions[idx + 1 :]:
                if _is_background_region(left) or _is_background_region(right):
                    continue
                overlap_ratio = _bbox_overlap_ratio(left.bbox, right.bbox)
                if overlap_ratio < self.region_overlap_threshold:
                    continue
                # Resolve: lower-priority region loses overlapping evidence ids
                left_prio = self._REGION_CONFLICT_PRIORITY.get(left.kind or "unknown", 0)
                right_prio = self._REGION_CONFLICT_PRIORITY.get(right.kind or "unknown", 0)
                loser = right if left_prio >= right_prio else left
                winner = left if left_prio >= right_prio else right
                overlap_evidence = {eid for eid in loser.evidence_ids if eid in winner.evidence_ids}
                if overlap_evidence:
                    loser.evidence_ids = [eid for eid in loser.evidence_ids if eid not in overlap_evidence]
                warning = {
                    "type": "region_overlap",
                    "severity": "warning",
                    "message": f"overlap resolved: {loser.kind} → {winner.kind}",
                    "region_ids": [left.id, right.id],
                    "overlap_ratio": round(overlap_ratio, 4),
                    "threshold": self.region_overlap_threshold,
                    "resolution": {"winner": winner.kind, "loser": loser.kind, "removed_evidence_count": len(overlap_evidence)},
                }
                _append_region_overlap_warning(left, right.id, overlap_ratio, self.region_overlap_threshold)
                _append_region_overlap_warning(right, left.id, overlap_ratio, self.region_overlap_threshold)
                page_topology.diagnostics.append(warning)


def _atom_index(evidence_plane: EvidencePlane) -> dict[str, EvidenceAtom]:
    atoms = [
        *evidence_plane.evidence.text_atoms,
        *evidence_plane.evidence.visual_atoms,
        *evidence_plane.evidence.image_atoms,
        *evidence_plane.evidence.vector_atoms,
    ]
    return {atom.id: atom for atom in atoms}


def _page_canvas_by_number(provenance: dict[str, Any]) -> dict[int, dict[str, Any]]:
    canvases = provenance.get("page_canvases") if isinstance(provenance, dict) else None
    if not isinstance(canvases, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for canvas in canvases:
        if not isinstance(canvas, dict):
            continue
        try:
            page_number = int(canvas.get("page_number") or 0)
        except (TypeError, ValueError):
            page_number = 0
        if page_number > 0:
            out[page_number] = canvas
    return out


def _page_bundle_by_number(provenance: dict[str, Any]) -> dict[int, dict[str, Any]]:
    bundles = provenance.get("page_evidence_bundles") if isinstance(provenance, dict) else None
    if not isinstance(bundles, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        try:
            page_number = int(bundle.get("page") or 0)
        except (TypeError, ValueError):
            page_number = 0
        if page_number > 0:
            out[page_number] = bundle
    return out


def _grid_rows_from_micro_grid(grid: dict[str, Any]) -> list[list[str]]:
    cells = grid.get("cells")
    if not isinstance(cells, list):
        return []
    rows: list[list[str]] = []
    for row in cells:
        if not isinstance(row, list):
            continue
        rows.append([
            str(cell.get("text", "") if isinstance(cell, dict) else getattr(cell, "text", ""))
            for cell in row
        ])
    if len(rows) < 2:
        return []
    column_count = max((len(row) for row in rows), default=0)
    if column_count < 2:
        return []
    return [row + [""] * (column_count - len(row)) for row in rows]


def _page_canvas_region_kind_role(raw_region: dict[str, Any]) -> tuple[str, str]:
    kind = str(raw_region.get("kind") or "").lower()
    morphology = str(raw_region.get("morphology") or "").lower()
    schema_hint = str(raw_region.get("schema_hint") or "").lower()
    haystack = " ".join([kind, morphology, schema_hint])
    if "micro_grid" in haystack or "table" in haystack or "grid" in haystack:
        return "table_like", "table_candidate"
    if "field" in haystack or "key" in haystack or "value" in haystack:
        return "text", "document_metadata"
    if "figure" in haystack or "chart" in haystack:
        return "figure", "figure"
    if "image" in haystack:
        return "image", "embedded_image"
    return "text", "body"


def _atom_center_in_bbox(atom: EvidenceAtom, bbox: list[float]) -> bool:
    if not atom.bbox or len(atom.bbox) != 4:
        return False
    center_x = (float(atom.bbox[0]) + float(atom.bbox[2])) / 2.0
    center_y = (float(atom.bbox[1]) + float(atom.bbox[3])) / 2.0
    return float(bbox[0]) <= center_x <= float(bbox[2]) and float(bbox[1]) <= center_y <= float(bbox[3])


def _bbox(value: Any) -> list[float] | None:
    if not value or not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        return [float(v) for v in value]
    except (TypeError, ValueError):
        return None


def _line_groups_from_atoms(atoms: list[EvidenceAtom], *, tolerance: float) -> list[list[EvidenceAtom]]:
    candidates = [atom for atom in atoms if atom.bbox and atom.text]
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda atom: (float((atom.bbox or [0, 0, 0, 0])[1]), float((atom.bbox or [0, 0, 0, 0])[0])))
    groups: list[list[EvidenceAtom]] = []
    current: list[EvidenceAtom] = []
    current_y: float | None = None
    for atom in ordered:
        bbox = atom.bbox or [0.0, 0.0, 0.0, 0.0]
        y_center = (float(bbox[1]) + float(bbox[3])) / 2.0
        if current_y is None or abs(y_center - current_y) <= tolerance:
            current.append(atom)
            current_y = y_center if current_y is None else (current_y + y_center) / 2.0
            continue
        groups.append(sorted(current, key=lambda item: float((item.bbox or [0, 0, 0, 0])[0])))
        current = [atom]
        current_y = y_center
    if current:
        groups.append(sorted(current, key=lambda item: float((item.bbox or [0, 0, 0, 0])[0])))
    return groups


def _line_item_from_group(page: EvidencePage, idx: int, atoms: list[EvidenceAtom]) -> dict[str, Any]:
    bbox = _union_bbox([atom.bbox for atom in atoms if atom.bbox]) or [0.0, 0.0, 0.0, 0.0]
    text = " ".join(str(atom.text or "") for atom in atoms if atom.text).strip()
    confidence = _average_confidence(atoms)
    return {
        "line_id": f"udtr_p{page.page_number}_l{idx}",
        "text": text,
        "bbox": tuple(float(value) for value in bbox),
        "confidence": confidence,
    }


def _ocr_tokens_from_atoms(atoms: list[EvidenceAtom], *, page_number: int) -> list[Any]:
    try:
        from docmirror.ocr.micro_grid.models import OCRToken
    except Exception:
        return []
    tokens: list[Any] = []
    for idx, atom in enumerate(atoms):
        if not atom.bbox or not atom.text:
            continue
        tokens.append(
            OCRToken(
                token_id=str(atom.metadata.get("source_token_id") or atom.id),
                text=str(atom.text or ""),
                bbox=tuple(float(value) for value in atom.bbox),
                confidence=atom.confidence,
                page=page_number,
                source=str(atom.source_kind or "udtr_evidence"),
            )
        )
    return tokens


def _table_grid_from_tokens(
    tokens: list[Any],
    bbox: tuple[float, float, float, float],
    *,
    page_height: float | None,
) -> list[list[str]]:
    if not tokens:
        return []
    x0, y0, x1, y1 = bbox
    block_tokens = [
        token
        for token in tokens
        if x0 <= token.center[0] <= x1 and y0 - 4.0 <= token.center[1] <= y1 + 4.0
    ]
    if len(block_tokens) < 6:
        return []
    try:
        from docmirror.ocr.reconstruct.grid_legacy import reconstruct_table_grid_from_tokens
    except Exception:
        return []
    try:
        return reconstruct_table_grid_from_tokens(block_tokens, page_h=float(page_height or y1 or 0.0))
    except Exception:
        return []


def _no_bbox_line_regions(page: EvidencePage, atoms: list[EvidenceAtom]) -> list[TopologyRegion]:
    if not any("line_index" in atom.metadata for atom in atoms):
        return []
    grouped: dict[int, list[EvidenceAtom]] = {}
    unindexed: list[EvidenceAtom] = []
    for atom in atoms:
        if "line_index" not in atom.metadata:
            unindexed.append(atom)
            continue
        try:
            line_index = int(atom.metadata["line_index"])
        except (TypeError, ValueError):
            unindexed.append(atom)
            continue
        grouped.setdefault(line_index, []).append(atom)
    regions: list[TopologyRegion] = []
    for output_index, line_index in enumerate(sorted(grouped), start=1):
        line_atoms = grouped[line_index]
        kind, role = _text_region_kind_role(line_atoms)
        regions.append(
            TopologyRegion(
                id=f"reg:{page.page_number:04d}:{output_index:04d}",
                page_id=page.page_id,
                kind=kind,
                role=role,
                bbox=None,
                evidence_ids=[atom.id for atom in line_atoms],
                reading_order=output_index,
                confidence=0.7,
                diagnostics={"grouping": "no_bbox_line_index", "line_index": line_index},
            )
        )
    if unindexed:
        output_index = len(regions) + 1
        kind, role = _text_region_kind_role(unindexed)
        regions.append(
            TopologyRegion(
                id=f"reg:{page.page_number:04d}:{output_index:04d}",
                page_id=page.page_id,
                kind=kind,
                role=role,
                bbox=None,
                evidence_ids=[atom.id for atom in unindexed],
                reading_order=output_index,
                confidence=0.65,
                diagnostics={"grouping": "no_bbox_unindexed_text"},
            )
        )
    return regions


class _EvidencePagePlum:
    def __init__(self, atoms: list[EvidenceAtom]) -> None:
        self._atoms = atoms
        self.chars = _chars_from_text_atoms(atoms)

    def extract_words(self, **_kwargs: Any) -> list[dict[str, Any]]:
        words: list[dict[str, Any]] = []
        for atom in self._atoms:
            if not atom.bbox or not atom.text:
                continue
            words.append(
                {
                    "text": str(atom.text),
                    "x0": float(atom.bbox[0]),
                    "x1": float(atom.bbox[2]),
                    "top": float(atom.bbox[1]),
                    "bottom": float(atom.bbox[3]),
                }
            )
        return words


def _chars_from_text_atoms(atoms: list[EvidenceAtom]) -> list[dict[str, Any]]:
    chars: list[dict[str, Any]] = []
    for atom in atoms:
        if not atom.bbox or not atom.text:
            continue
        text = str(atom.text)
        visible_chars = [char for char in text if char.strip()]
        if not visible_chars:
            continue
        x0, top, x1, bottom = [float(value) for value in atom.bbox]
        width = max(0.1, x1 - x0)
        step = width / max(len(text), 1)
        for idx, char in enumerate(text):
            if not char.strip():
                continue
            char_x0 = x0 + idx * step
            chars.append(
                {
                    "text": char,
                    "x0": char_x0,
                    "x1": min(x1, char_x0 + step),
                    "top": top,
                    "bottom": bottom,
                }
            )
    return chars


def _assign_reading_order(regions: list[TopologyRegion]) -> list[TopologyRegion]:
    if any(region.bbox is None for region in regions):
        for idx, region in enumerate(regions, start=1):
            region.reading_order = idx
        return regions

    def sort_key(item: tuple[int, TopologyRegion]) -> tuple[float, float, int]:
        original_index, region = item
        bbox = region.bbox or [0.0, 0.0, 0.0, 0.0]
        return (float(bbox[1]), float(bbox[0]), original_index)

    ordered = [region for _, region in sorted(enumerate(regions), key=sort_key)]
    for idx, region in enumerate(ordered, start=1):
        region.reading_order = idx
    return ordered


def _apply_region_graph_diagnostics(page_topology: PageTopology, graph_diagnostics: dict[str, Any]) -> None:
    ownership = graph_diagnostics.get("ownership") if isinstance(graph_diagnostics.get("ownership"), dict) else {}
    owned = ownership.get("owned") if isinstance(ownership.get("owned"), dict) else {}
    overlay = ownership.get("overlay") if isinstance(ownership.get("overlay"), dict) else {}
    nested = ownership.get("nested") if isinstance(ownership.get("nested"), dict) else {}
    residual = set(ownership.get("residual") or [])
    candidates = [
        candidate
        for candidate in graph_diagnostics.get("candidates", []) or []
        if isinstance(candidate, dict)
    ]
    candidate_by_region: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        region_ids = [
            str(candidate.get("selected_region_id") or ""),
            *(str(region_id or "") for region_id in candidate.get("source_region_ids", []) or []),
        ]
        for region_id in region_ids:
            if region_id and region_id not in candidate_by_region:
                candidate_by_region[region_id] = candidate
    rejected_candidates = ownership.get("rejected_candidates") if isinstance(ownership.get("rejected_candidates"), list) else []
    rejected_by_region: dict[str, list[dict[str, Any]]] = {}
    for item in rejected_candidates:
        if not isinstance(item, dict):
            continue
        region_id = str(item.get("candidate_region_id") or item.get("selected_region_id") or "")
        if region_id:
            rejected_by_region.setdefault(region_id, []).append(item)
    for region in page_topology.regions:
        candidate = candidate_by_region.get(region.id)
        region_owned = [eid for eid in region.evidence_ids if owned.get(eid) == region.id]
        region_residual = [eid for eid in region.evidence_ids if eid in residual]
        diagnostics = dict(region.diagnostics)
        if candidate:
            diagnostics["selected_candidate_ids"] = [candidate["candidate_id"]]
            diagnostics["candidate_detector"] = candidate.get("detector", "")
            diagnostics["competing_candidate_ids"] = list(candidate.get("competing_candidate_ids") or [])
            diagnostics["parent_candidate_ids"] = list(candidate.get("parent_candidate_ids") or [])
            diagnostics["child_candidate_ids"] = list(candidate.get("child_candidate_ids") or [])
            diagnostics["candidate_source_region_ids"] = list(candidate.get("source_region_ids") or [])
            diagnostics["merged_candidate_ids"] = list(candidate.get("merged_candidate_ids") or [])
            if candidate.get("merge_reason"):
                diagnostics["candidate_merge_reason"] = candidate.get("merge_reason")
        region_rejections = rejected_by_region.get(region.id, [])
        if region_rejections:
            diagnostics["rejected_candidate_ids"] = [
                str(item.get("candidate_id") or "")
                for item in region_rejections
                if item.get("candidate_id")
            ]
            diagnostics["rejection_reasons"] = [
                {
                    key: value
                    for key, value in item.items()
                    if key in {"candidate_id", "reason", "winner_candidate_id", "other_candidate_id", "iou"}
                }
                for item in region_rejections
            ]
        diagnostics["ownership_reason"] = "selected_region_claim"
        diagnostics["owned_evidence_count"] = len(region_owned)
        if region_residual:
            diagnostics["residual_evidence_ids"] = region_residual
            diagnostics["ownership_reason"] = "partial_residual"
        if region.id in overlay:
            diagnostics["overlay_target_region_id"] = overlay[region.id]
            diagnostics["ownership_relation"] = "overlay"
        nested_hits = [eid for eid, region_ids in nested.items() if region.id in region_ids]
        if nested_hits:
            diagnostics["nested_evidence_ids"] = nested_hits
            diagnostics["ownership_relation"] = "nested"
        region.diagnostics = diagnostics
    page_topology.diagnostics.append(
        {
            "severity": "info",
            "message": "region graph ownership solved",
            **{key: value for key, value in graph_diagnostics.items() if key != "ownership"},
            "ownership_stats": {
                "owned": len(owned),
                "nested": len(nested),
                "overlay": len(overlay),
                "residual": len(residual),
                "rejected_candidates": len(ownership.get("rejected_candidates") or []),
            },
        }
    )


def _metadata_bbox(atoms: list[EvidenceAtom], key: str) -> list[float] | None:
    for atom in atoms:
        value = atom.metadata.get(key)
        if isinstance(value, list | tuple) and len(value) == 4:
            try:
                return [float(v) for v in value]
            except (TypeError, ValueError):
                continue
    return None


def _table_region_provenance(atoms: list[EvidenceAtom]) -> dict[str, Any]:
    if not atoms:
        return {}
    keys = (
        "extraction_layer",
        "extraction_confidence",
        "geometry_source",
        "geometry_confidence",
        "coordinate_system",
        "ocr_rotation",
        "ocr_orientation_score",
        "normalized_page_width",
        "normalized_page_height",
        "preserve_headers",
        "statement_keywords",
        "role",
        "source",
        "page_width",
        "page_height",
    )
    out: dict[str, Any] = {}
    for key in keys:
        values = [atom.metadata.get(key) for atom in atoms if atom.metadata.get(key) not in (None, "", [], {})]
        if values:
            out[key] = values[0]
    return out


def _average_confidence(atoms: list[EvidenceAtom]) -> float:
    if not atoms:
        return 0.0
    return sum(atom.confidence for atom in atoms) / len(atoms)


def _text_region_kind_role(atoms: list[EvidenceAtom]) -> tuple[str, str]:
    levels = [str(atom.metadata.get("level") or "body") for atom in atoms]
    for level in levels:
        if level in {"title", "h1", "h2", "h3"}:
            return "heading", level
    for level in levels:
        if level in {"footer", "watermark"}:
            return "text", level
    return "text", "body"


def _nearest_table_relation(
    region: TopologyRegion,
    table_regions: list[TopologyRegion],
    *,
    max_gap: float,
) -> tuple[str, TopologyRegion, float] | None:
    if not region.bbox:
        return None
    candidates: list[tuple[float, str, TopologyRegion]] = []
    for table_region in table_regions:
        if not table_region.bbox:
            continue
        if region.bbox[3] <= table_region.bbox[1]:
            gap = float(table_region.bbox[1] - region.bbox[3])
            candidates.append((gap, "table_preamble", table_region))
        elif region.bbox[1] >= table_region.bbox[3]:
            gap = float(region.bbox[1] - table_region.bbox[3])
            candidates.append((gap, "table_postamble", table_region))

    if not candidates:
        return None
    gap, role, table_region = min(candidates, key=lambda item: item[0])
    if gap > max_gap:
        return None
    return role, table_region, gap


def _append_region_overlap_warning(
    region: TopologyRegion,
    other_region_id: str,
    overlap_ratio: float,
    threshold: float,
) -> None:
    existing = region.diagnostics.get("overlap_warnings")
    warnings = existing if isinstance(existing, list) else []
    warnings.append(
        {
            "region_id": other_region_id,
            "overlap_ratio": round(overlap_ratio, 4),
            "threshold": threshold,
        }
    )
    region.diagnostics = {**region.diagnostics, "overlap_warnings": warnings}


def _is_account_identity_text(text: str) -> bool:
    """Detect bank statement account identity text (account name, account number, period)."""
    primary_markers = ["账户名称", "账号：", "账号:", "起始日期", "终止日期", "对公账户"]
    return any(kw in text for kw in primary_markers)


def _region_text(region: TopologyRegion, atom_by_id: dict[str, EvidenceAtom]) -> str:
    return " ".join(str(atom_by_id[atom_id].text or "") for atom_id in region.evidence_ids if atom_id in atom_by_id).strip()


def _is_background_region(region: TopologyRegion) -> bool:
    return region.kind == "image" and region.role == "page_background"


def _is_toc_title(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text).lower()
    return normalized in {"目录", "contents", "tableofcontents"}


def _parse_toc_entry(text: str) -> tuple[str, int] | None:
    stripped = text.strip()
    if not stripped or _is_toc_title(stripped):
        return None
    match = re.match(r"^(.+?)(?:[.\u00b7\u2022\u2026·•…\s]{2,})(\d{1,4})$", stripped)
    if match is None:
        match = re.match(r"^([一二三四五六七八九十\d]+[、.．].+?)\s+(\d{1,4})$", stripped)
    if match is None:
        return None
    title = match.group(1).strip(" .·•…\t")
    if not title:
        return None
    return title, int(match.group(2))


def _heading_level_from_text(text: str) -> str | None:
    stripped = text.strip()
    compact = re.sub(r"\s+", "", stripped)
    if not compact or len(compact) > 80:
        return None
    if _is_toc_title(stripped) or _parse_toc_entry(stripped) is not None:
        return None
    if re.match(r"^第[一二三四五六七八九十百千万\d]+[章节部篇]", compact):
        return "h1"
    if re.match(r"^[一二三四五六七八九十]+[、.．]\S{2,50}$", compact):
        return "h2"
    if re.match(r"^\d+(\.\d+){1,3}\s*\S{2,50}$", stripped):
        return "h2"
    if re.match(r"^\d+[、.．]\s*\S{2,50}$", stripped):
        return "h3"
    return None


def _is_table_summary_text(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text)
    return bool(re.search(r"(借方|贷方|收入|支出|发生|合计|小计|总额|余额).{0,8}(笔数|金额|总额|合计)", normalized))


def _is_footnote_text(text: str) -> bool:
    stripped = text.strip()
    return bool(
        re.match(r"^(注|备注|说明|附注|note|notes)\s*[:：.．、]", stripped, flags=re.IGNORECASE)
        or re.match(r"^([*※]|\[\d+\]|\(\d+\)|（\d+）)\s*\S+", stripped)
    )


def _extract_summary_kv(text: str) -> dict[str, str]:
    if not text:
        return {}
    _LM = {
        "借方笔数": "debit_count", "贷方笔数": "credit_count",
        "借方发生笔数": "debit_count", "贷方发生笔数": "credit_count",
        "借方发生数": "debit_count", "贷方发生数": "credit_count",
        "借方金额": "debit_amount", "贷方金额": "credit_amount",
        "借方发生额": "debit_amount", "贷方发生额": "credit_amount",
        "余额": "balance",
        "出单截至日期": "cutoff_date", "截止日期": "cutoff_date",
        "出单截止日期": "cutoff_date",
    }
    fields: dict[str, str] = {}
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r'^[─━═\-\*]+|[─━═\-\*]+$', '', line)
        m = re.match(r'^\s*(.+?)\s*[:：]\s*(.+?)\s*$', line)
        if not m:
            continue
        label, value = m.group(1).strip(), m.group(2).strip()
        if not label or not value:
            continue
        for kw, canonical in _LM.items():
            if kw in label:
                prefix = "current_" if any(p in label for p in ("当前", "本页")) else \
                         "period_" if any(p in label for p in ("累计", "本月", "本期")) else ""
                fn = prefix + canonical
                if fn not in fields:
                    fields[fn] = value
                break
    return fields


def _clean_notice_text(text: str) -> str:
    """Strip decorative characters from notice/statement text.

    ``----以下此页无其他交易信息----`` → ``以下此页无其他交易信息``
    """
    if not text:
        return text
    return re.sub(r'^[─━═\-\*\s]+|[─━═\-\*\s]+$', '', text).strip()


def _is_notice_text(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text).lower()
    return any(
        marker in normalized
        for marker in (
            "仅供参考",
            "不作为",
            "免责声明",
            "声明",
            "重要提示",
            "notice",
            "disclaimer",
        )
    )


def _normalize_repeated_text(text: str) -> str:
    normalized = re.sub(r"\s+", "", text or "").lower()
    normalized = re.sub(r"\d+", "#", normalized)
    return normalized if len(normalized) >= 2 else ""


def _visual_artifact_kind(atom: EvidenceAtom) -> str | None:
    haystack = " ".join([str(atom.kind or ""), atom.source_kind, " ".join(str(v) for v in atom.metadata.values())]).lower()
    if "signature" in haystack or "签名" in haystack:
        return "signature"
    if "seal" in haystack or "stamp" in haystack or "印章" in haystack or "公章" in haystack:
        return "seal"
    return None


def _union_bbox(bboxes: list[list[float] | None]) -> list[float] | None:
    values = [bbox for bbox in bboxes if bbox and len(bbox) == 4]
    if not values:
        return None
    return [
        min(b[0] for b in values),
        min(b[1] for b in values),
        max(b[2] for b in values),
        max(b[3] for b in values),
    ]


def _bbox_overlap_ratio(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != 4 or len(right) != 4:
        return 0.0
    intersection_left = max(float(left[0]), float(right[0]))
    intersection_top = max(float(left[1]), float(right[1]))
    intersection_right = min(float(left[2]), float(right[2]))
    intersection_bottom = min(float(left[3]), float(right[3]))
    width = max(0.0, intersection_right - intersection_left)
    height = max(0.0, intersection_bottom - intersection_top)
    intersection_area = width * height
    if intersection_area <= 0.0:
        return 0.0
    smaller_area = min(_bbox_area(left), _bbox_area(right))
    if smaller_area <= 0.0:
        return 0.0
    return intersection_area / smaller_area


def _bbox_area(bbox: list[float] | None) -> float:
    if not bbox or len(bbox) != 4:
        return 0.0
    return max(0.0, float(bbox[2]) - float(bbox[0])) * max(0.0, float(bbox[3]) - float(bbox[1]))


def _page_bbox(page: EvidencePage) -> list[float] | None:
    if page.width is None or page.height is None:
        return None
    return [0.0, 0.0, float(page.width), float(page.height)]


__all__ = [
    "DocumentTopology",
    "PageTopology",
    "PageTopologyBuilder",
    "TopologyRegion",
]
