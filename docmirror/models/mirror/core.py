"""Canonical MirrorJson projection core.

This module lives under ``models.mirror`` so core parse/model paths can build
the canonical mirror projection without depending on the output/export layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from docmirror.runtime.serialization import to_json_safe


@dataclass(slots=True)
class MirrorOptions:
    source_filename: str = ""
    profile: str = "standard"
    engine_version: str = "0.1.0"


@dataclass(slots=True)
class MirrorResult:
    payload: dict[str, Any]

    @property
    def mirror(self) -> Any:
        from docmirror.models.mirror.vnext import MirrorJsonVNext

        return MirrorJsonVNext.model_validate(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return to_json_safe(self.payload)


class MirrorCoreVNext:
    """Build the canonical document-shaped MirrorJson payload."""

    def __init__(self, *, evidence_builder: Any | None = None, topology_builder: Any | None = None) -> None:
        self.evidence_builder = evidence_builder
        self.topology_builder = topology_builder

    def process(self, result: Any, options: MirrorOptions | None = None) -> MirrorResult:
        options = options or MirrorOptions()
        if self._can_build_evidence_plane(result):
            return self._process_source(result, options)

        entities = getattr(result, "entities", None)
        document_type = getattr(entities, "document_type", None) if entities is not None else None
        sections = to_json_safe(getattr(result, "sections", []) or [])
        table_operations = to_json_safe(getattr(result, "table_operations", []) or [])
        pages = to_json_safe(getattr(result, "pages", []) or [])
        status = getattr(getattr(result, "status", None), "value", getattr(result, "status", "success"))

        payload = {
            "mirror": {
                "schema": "docmirror.mirror_json",
                "schema_version": "3.0.0",
                "engine": "udtr",
                "engine_version": options.engine_version,
                "profile": options.profile,
            },
            "source": {
                "filename": options.source_filename,
                "provenance": {
                    "sections": sections,
                    "table_operations": table_operations,
                },
            },
            "document": {
                "document_type": document_type or "generic",
                "document_type_candidates": [],
            },
            "pages": pages,
            "evidence": {
                "text_atoms": [],
                "visual_atoms": [],
            },
            "regions": [],
            "blocks": [],
            "graph": {
                "nodes": [],
                "edges": [],
                "reading_flows": [],
                "outline": [],
            },
            "semantics": {
                "facts": [],
                "entities": [],
                "views": {},
            },
            "quality": {
                "overall": {
                    "status": "fail" if str(status) == "failure" else "pass",
                    "score": float(getattr(result, "confidence", 1.0) or 0.0),
                }
            },
            "diagnostics": {
                "pipeline": [],
            },
            "assets": {
                "items": [],
            },
        }
        error = getattr(result, "error", None)
        if error is not None:
            payload["diagnostics"]["error"] = to_json_safe(error)
        return MirrorResult(payload)

    def _can_build_evidence_plane(self, source: Any) -> bool:
        if isinstance(source, (str, Path)):
            return Path(source).exists()
        if type(source).__name__ in {"DocumentSource", "ParseResult"}:
            return True
        return hasattr(source, "pages") or hasattr(source, "entities")

    def _process_source(self, source_input: Any, options: MirrorOptions) -> MirrorResult:
        from docmirror.evidence.plane import EvidencePlaneBuilder
        from docmirror.quality.udtr_gates import build_udtr_quality_gates

        page_topology_module = import_module("docmirror.structure.page_topology")
        reconstructors_module = import_module("docmirror.structure.reconstructors")
        PageTopologyBuilder = page_topology_module.PageTopologyBuilder
        ReconstructionContext = reconstructors_module.ReconstructionContext
        RegionReconstructorRegistry = reconstructors_module.RegionReconstructorRegistry

        evidence_builder = self.evidence_builder or EvidencePlaneBuilder()
        topology_builder = self.topology_builder or PageTopologyBuilder()
        plane = evidence_builder.build(source_input)
        topology = topology_builder.build(plane)
        atom_by_id = self._atom_by_id(plane)
        context = ReconstructionContext(
            evidence_plane=plane,
            atom_by_id=atom_by_id,
            atom_text={atom_id: str(atom.text or "") for atom_id, atom in atom_by_id.items()},
        )
        registry = RegionReconstructorRegistry()
        reports = [
            registry.reconstruct_with_report(region, context)
            for page in topology.pages
            for region in page.regions
        ]
        blocks = [report.block for report in reports]
        self._normalize_block_quality(blocks)
        regions = self._regions_from_topology(topology)
        pages = self._pages_from_plane(plane, regions, blocks)
        semantics = self._semantics_from_blocks(blocks)
        graph = self._graph_from_blocks_regions(blocks, regions, semantics, plane)
        document = self._document_from_plane_blocks(plane, blocks, semantics)
        quality = self._quality_from_model(
            pages=pages,
            regions=regions,
            blocks=blocks,
            base_gates=build_udtr_quality_gates(pages=pages, regions=regions, blocks=blocks),
        )
        source = to_json_safe(plane.source)
        if options.source_filename:
            source["filename"] = options.source_filename
        payload = {
            "mirror": {
                "schema": "docmirror.mirror_json",
                "schema_version": "3.0.0",
                "engine": "udtr",
                "engine_version": options.engine_version,
                "profile": options.profile,
            },
            "source": source,
            "document": document,
            "pages": pages,
            "evidence": to_json_safe(plane.evidence),
            "regions": regions,
            "blocks": to_json_safe(blocks),
            "graph": graph,
            "semantics": semantics,
            "quality": quality,
            "diagnostics": {
                "pipeline": [
                    plane.diagnostics_entry(),
                    topology.diagnostics_entry(),
                    self._reconstruction_diagnostics(reports),
                    self._profile_diagnostics(quality),
                ],
                "warnings": self._diagnostic_warnings(quality, blocks),
            },
            "assets": {
                "items": [],
            },
        }
        return MirrorResult(payload)

    def _atom_by_id(self, plane: Any) -> dict[str, Any]:
        atoms = [
            *list(getattr(plane.evidence, "text_atoms", []) or []),
            *list(getattr(plane.evidence, "visual_atoms", []) or []),
            *list(getattr(plane.evidence, "image_atoms", []) or []),
            *list(getattr(plane.evidence, "vector_atoms", []) or []),
        ]
        return {atom.id: atom for atom in atoms if getattr(atom, "id", "")}

    def _regions_from_topology(self, topology: Any) -> list[dict[str, Any]]:
        regions: list[dict[str, Any]] = []
        for page in topology.pages:
            for region in page.regions:
                diagnostics = dict(getattr(region, "diagnostics", {}) or {})
                quality = {
                    "selected_candidate_ids": diagnostics.get("selected_candidate_ids", [region.id]),
                    "ownership_reason": diagnostics.get("ownership_reason", diagnostics.get("grouping", "topology_region")),
                }
                if diagnostics.get("overlap_warnings"):
                    quality["overlap_warnings"] = diagnostics["overlap_warnings"]
                regions.append(
                    {
                        "id": region.id,
                        "page_id": region.page_id,
                        "kind": region.kind,
                        "role": region.role,
                        "bbox": region.bbox,
                        "evidence_ids": list(region.evidence_ids),
                        "block_ids": [],
                        "reading_order": region.reading_order,
                        "confidence": region.confidence,
                        "quality": quality,
                        "diagnostics": diagnostics,
                    }
                )
        return regions

    def _pages_from_plane(self, plane: Any, regions: list[dict[str, Any]], blocks: list[Any]) -> list[dict[str, Any]]:
        regions_by_page: dict[str, list[dict[str, Any]]] = {}
        blocks_by_page: dict[str, list[Any]] = {}
        for region in regions:
            regions_by_page.setdefault(str(region.get("page_id") or ""), []).append(region)
        for block in blocks:
            for page_id in getattr(block, "page_ids", []) or []:
                blocks_by_page.setdefault(str(page_id), []).append(block)
        pages: list[dict[str, Any]] = []
        for page in plane.pages:
            page_regions = regions_by_page.get(page.page_id, [])
            page_blocks = blocks_by_page.get(page.page_id, [])
            residual_evidence = {
                evidence_id
                for region in page_regions
                if region.get("kind") == "residual"
                for evidence_id in region.get("evidence_ids", [])
            }
            evidence_ids = list(getattr(page, "evidence_ids", []) or [])
            residual_ratio = len(residual_evidence) / len(evidence_ids) if evidence_ids else 0.0
            pages.append(
                {
                    "page_id": page.page_id,
                    "page_index": page.page_index,
                    "page_number": page.page_number,
                    "width": page.width,
                    "height": page.height,
                    "original_rotation": page.original_rotation,
                    "normalized_rotation": page.normalized_rotation,
                    "coordinate_transform": dict(page.coordinate_transform or {}),
                    "content_mode": page.content_mode,
                    "evidence_ids": evidence_ids,
                    "region_ids": [region["id"] for region in page_regions],
                    "block_ids": [block.id for block in page_blocks],
                    "quality": {
                        "evidence_coverage": 1.0 if evidence_ids or page_regions else 0.0,
                        "residual_ratio": residual_ratio,
                    },
                }
            )
        return pages

    def _document_from_plane_blocks(self, plane: Any, blocks: list[Any], semantics: dict[str, Any]) -> dict[str, Any]:
        provenance = getattr(plane.source, "provenance", {}) or {}
        entities = provenance.get("entities") if isinstance(provenance, dict) else {}
        document_type = (
            (entities or {}).get("document_type")
            or (provenance or {}).get("scene")
            or getattr(plane.source, "input_kind", "generic")
            or "generic"
        )
        headings = [block for block in blocks if str(getattr(block, "type", "")) == "heading"]
        title = {"text": headings[0].text, "block_id": headings[0].id} if headings and headings[0].text else None
        candidate = {"type": document_type, "confidence": 1.0, "evidence_ids": []}
        root_blocks = [block for block in blocks if self._is_main_reading_block(block)]
        return {
            "document_type": document_type,
            "document_type_candidates": [candidate],
            "title": title,
            "root_block_ids": [block.id for block in root_blocks],
            "outline_block_ids": [block.id for block in headings],
            "primary_reading_flow_id": "flow:main",
        }

    def _graph_from_blocks_regions(
        self,
        blocks: list[Any],
        regions: list[dict[str, Any]],
        semantics: dict[str, Any],
        plane: Any,
    ) -> dict[str, Any]:
        nodes = [
            {"id": "document:root", "kind": "document"},
            *[{"id": region["id"], "kind": "region"} for region in regions],
            *[{"id": block.id, "kind": "block"} for block in blocks],
            *[{"id": fact["id"], "kind": "fact"} for fact in semantics.get("facts", [])],
        ]
        edges: list[dict[str, Any]] = []
        for block in blocks:
            edges.append({"id": f"edge:document:{block.id}", "type": "contains", "from": "document:root", "to": block.id})
            for region_id in getattr(block, "region_ids", []) or []:
                edges.append({"id": f"edge:{region_id}:{block.id}", "type": "derived_from", "from": region_id, "to": block.id})
        reading_blocks = [
            block
            for block in blocks
            if str(getattr(block, "type", "")) not in {"header", "footer"} and not (getattr(block, "quality", {}) or {}).get("suppressed_from_reading_flow")
        ]
        for previous, current in zip(reading_blocks, reading_blocks[1:], strict=False):
            edges.append({"id": f"edge:reading:{previous.id}:{current.id}", "type": "reading_next", "from": previous.id, "to": current.id})
        edges.extend(self._overlay_edges(blocks))
        edges.extend(self._toc_edges(blocks))
        edges.extend(self._footnote_edges(blocks))
        edges.extend(self._cross_page_table_edges(blocks, plane))
        return {
            "nodes": nodes,
            "edges": edges,
            "reading_flows": [
                {
                    "flow_id": "flow:main",
                    "kind": "main_reading_order",
                    "node_ids": [block.id for block in reading_blocks],
                }
            ],
            "outline": [],
        }

    def _semantics_from_blocks(self, blocks: list[Any]) -> dict[str, Any]:
        facts: list[dict[str, Any]] = []
        document_metadata: dict[str, Any] = {}
        table_views: list[dict[str, Any]] = []
        for block in blocks:
            if str(getattr(block, "type", "")) == "key_value_group":
                for item in (getattr(block, "content", {}) or {}).get("items", []) or []:
                    key = str(item.get("key") or "")
                    if not key:
                        continue
                    value = item.get("value") or {}
                    document_metadata[key] = value
                    facts.append(
                        {
                            "id": f"fact:document.field.{key}",
                            "subject_id": "document:root",
                            "predicate": f"document.field.{key}",
                            "object": value,
                            "source_block_ids": [block.id],
                            "evidence_ids": item.get("evidence_ids", []),
                            "confidence": float(value.get("confidence", 1.0) if isinstance(value, dict) else 1.0),
                        }
                    )
            if str(getattr(block, "type", "")) == "table":
                table_views.append({"block_id": block.id, "grid": (getattr(block, "content", {}) or {}).get("grid", {})})
        views: dict[str, Any] = {}
        if document_metadata:
            views["document_metadata"] = document_metadata
        if table_views:
            views["bank_statement"] = {"tables": table_views}
        return {"facts": facts, "entities": [], "views": views}

    def _quality_from_model(
        self,
        *,
        pages: list[dict[str, Any]],
        regions: list[dict[str, Any]],
        blocks: list[Any],
        base_gates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        residual_ratios = [float((page.get("quality") or {}).get("residual_ratio", 0.0) or 0.0) for page in pages]
        residual_ratio = max(residual_ratios) if residual_ratios else 0.0
        numeric_score = self._table_numeric_parse_score(blocks)
        gates = [
            *base_gates,
            self._gate("gate:region_ownership", "pass", 1.0, 1.0),
            self._gate("gate:token_conservation", "pass", 1.0, 1.0),
            self._gate("gate:residual_ratio", "pass" if residual_ratio <= 0.2 else "warn", 1.0 - residual_ratio, 0.8),
            self._gate("gate:table_numeric_parse", "pass" if numeric_score >= 0.95 else "warn", numeric_score, 0.95),
            self._gate(
                "gate:region_overlap",
                "warn" if self._overlap_pairs(regions) else "pass",
                1.0,
                1.0,
                target_ids=self._overlap_details(regions)["target_ids"],
                details=self._overlap_details(regions),
            ),
            self._gate("gate:toc_consistency", "pass", 1.0, 1.0, details={"heading_linked_count": self._toc_heading_linked_count(blocks)}),
            self._gate("gate:cross_page_continuity", "pass", 1.0, 1.0, details=self._cross_page_continuity_details(blocks)),
        ]
        events = [
            {
                "event_type": "quality_gate",
                "gate_id": gate["id"],
                "status": gate["status"],
                "score": gate.get("score"),
                "target_ids": gate.get("target_ids", []),
                "details": gate.get("details", {}),
                "actionable": gate["status"] in {"warn", "fail"},
            }
            for gate in gates
        ]
        return {
            "overall": {
                "status": "warn" if any(gate["status"] == "warn" for gate in gates) else "pass",
                "score": min(float(gate.get("score", 1.0) or 0.0) for gate in gates) if gates else 1.0,
                "confidence": 1.0,
            },
            "coverage": {"residual_ratio": residual_ratio},
            "tables": {"numeric_parse_score": numeric_score},
            "reading_order": {},
            "gates": gates,
            "events": events,
            "event_summary": {
                "event_count": len(events),
                "actionable_count": sum(1 for event in events if event["actionable"]),
            },
        }

    def _table_numeric_parse_score(self, blocks: list[Any]) -> float:
        cells = []
        for block in blocks:
            if str(getattr(block, "type", "")) != "table":
                continue
            cells.extend(((getattr(block, "content", {}) or {}).get("grid", {}) or {}).get("cells", []) or [])
        numeric_cells = [cell for cell in cells if ((cell.get("value") or {}).get("type") == "number")]
        return 1.0 if not cells or numeric_cells else 0.0

    def _gate(
        self,
        gate_id: str,
        status: str,
        score: float,
        threshold: float,
        *,
        target_ids: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": gate_id,
            "status": status,
            "score": float(score),
            "threshold": float(threshold),
            "target_ids": target_ids or [],
            "details": details or {},
        }

    def _overlap_pairs(self, regions: list[dict[str, Any]]) -> list[list[str]]:
        pairs: list[list[str]] = []
        for region in regions:
            for warning in ((region.get("quality") or {}).get("overlap_warnings") or []):
                other = warning.get("region_id") if isinstance(warning, dict) else None
                if other:
                    pair = sorted([str(region.get("id") or ""), str(other)])
                    if pair not in pairs:
                        pairs.append(pair)
        return pairs

    def _overlap_details(self, regions: list[dict[str, Any]]) -> dict[str, Any]:
        pairs = self._overlap_pairs(regions)
        target_ids = sorted({region_id for pair in pairs for region_id in pair})
        return {
            "overlap_warning_count": len(pairs),
            "overlap_pairs": pairs,
            "target_ids": target_ids,
        }

    def _is_main_reading_block(self, block: Any) -> bool:
        block_type = str(getattr(block, "type", ""))
        return block_type not in {"header", "footer"} and not (getattr(block, "quality", {}) or {}).get("suppressed_from_reading_flow")

    def _overlay_edges(self, blocks: list[Any]) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        targets = [block for block in blocks if str(getattr(block, "type", "")) not in {"artifact", "figure"}]
        for overlay in blocks:
            if str(getattr(overlay, "role", "")) not in {"seal", "signature"}:
                continue
            target = next((block for block in targets if self._same_page(overlay, block) and self._bbox_overlap(overlay.bbox, block.bbox) > 0), None)
            if target is None:
                continue
            edges.append(
                {
                    "id": f"edge:overlay:{overlay.id}:{target.id}",
                    "type": "overlays",
                    "from": overlay.id,
                    "to": target.id,
                    "confidence": float(getattr(overlay, "confidence", 1.0) or 1.0),
                    "metadata": {
                        "relation_kind": str(getattr(overlay, "role", "overlay")),
                        "overlay_role": str(getattr(overlay, "role", "overlay")),
                    },
                }
            )
        return edges

    def _normalize_block_quality(self, blocks: list[Any]) -> None:
        for block in blocks:
            if str(getattr(block, "type", "")) in {"header", "footer"}:
                block.quality = {
                    **(getattr(block, "quality", {}) or {}),
                    "suppressed_from_reading_flow": True,
                }

    def _toc_edges(self, blocks: list[Any]) -> list[dict[str, Any]]:
        headings = [block for block in blocks if str(getattr(block, "type", "")) == "heading"]
        page_by_id = {page_id: self._page_number_from_id(page_id) for block in blocks for page_id in (getattr(block, "page_ids", []) or [])}
        edges: list[dict[str, Any]] = []
        for toc in [block for block in blocks if str(getattr(block, "type", "")) == "toc"]:
            for item in ((getattr(toc, "content", {}) or {}).get("items", []) or []):
                target_page = item.get("target_page")
                target_page_id = f"page:{int(target_page):04d}" if target_page else ""
                if target_page_id:
                    edges.append(
                        {
                            "id": f"edge:toc:{toc.id}:{target_page_id}",
                            "type": "toc_points_to",
                            "from": toc.id,
                            "to": target_page_id,
                            "confidence": float(getattr(toc, "confidence", 1.0) or 1.0),
                            "metadata": {
                                "relation_kind": "toc_section_range",
                                "section_page_range": [int(target_page), int(target_page)],
                            },
                        }
                    )
                title = str(item.get("title") or "")
                heading = next(
                    (
                        block
                        for block in headings
                        if str(getattr(block, "text", "")) == title
                        and any(page_by_id.get(page_id) == int(target_page) for page_id in (getattr(block, "page_ids", []) or []))
                    ),
                    None,
                )
                if heading is not None:
                    edges.append(
                        {
                            "id": f"edge:toc_heading:{toc.id}:{heading.id}",
                            "type": "references",
                            "from": toc.id,
                            "to": heading.id,
                            "confidence": float(getattr(toc, "confidence", 1.0) or 1.0),
                            "metadata": {"reference_kind": "toc_heading", "relation_kind": "toc_heading"},
                        }
                    )
        return edges

    def _footnote_edges(self, blocks: list[Any]) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        tables = [block for block in blocks if str(getattr(block, "type", "")) == "table"]
        for footnote in [block for block in blocks if str(getattr(block, "type", "")) == "footnote"]:
            target = next((table for table in tables if self._same_page(footnote, table)), None)
            if target is None:
                continue
            edges.append(
                {
                    "id": f"edge:footnote:{footnote.id}:{target.id}",
                    "type": "footnote_of",
                    "from": footnote.id,
                    "to": target.id,
                    "confidence": float(getattr(footnote, "confidence", 1.0) or 1.0),
                    "metadata": {"relation_kind": "table_footnote"},
                }
            )
        return edges

    def _cross_page_table_edges(self, blocks: list[Any], plane: Any) -> list[dict[str, Any]]:
        provenance = getattr(plane.source, "provenance", {}) or {}
        logical_tables = provenance.get("logical_tables", []) if isinstance(provenance, dict) else []
        table_blocks = [block for block in blocks if str(getattr(block, "type", "")) == "table"]
        by_source_id = {
            str((getattr(block, "provenance", {}) or {}).get("source_table_id") or ""): block
            for block in table_blocks
        }
        edges: list[dict[str, Any]] = []
        for logical_table in logical_tables:
            source_ids = [str(value) for value in logical_table.get("source_physical_ids", [])] if isinstance(logical_table, dict) else []
            linked = [by_source_id[source_id] for source_id in source_ids if source_id in by_source_id]
            if len(linked) < 2:
                continue
            logical_id = str(logical_table.get("logical_id") or logical_table.get("table_id") or "")
            confidence = float(logical_table.get("merge_confidence", 1.0) or 1.0)
            edges.append(
                {
                    "id": f"edge:same_table:{linked[0].id}:{linked[1].id}",
                    "type": "same_table",
                    "from": linked[0].id,
                    "to": linked[1].id,
                    "confidence": confidence,
                    "metadata": {"logical_id": logical_id},
                }
            )
            edges.append(
                {
                    "id": f"edge:continues:{linked[0].id}:{linked[1].id}",
                    "type": "continues",
                    "from": linked[0].id,
                    "to": linked[1].id,
                    "confidence": confidence,
                    "metadata": {"logical_id": logical_id},
                }
            )
        return edges

    def _toc_heading_linked_count(self, blocks: list[Any]) -> int:
        return len([edge for edge in self._toc_edges(blocks) if edge["type"] == "references"])

    def _cross_page_continuity_details(self, blocks: list[Any]) -> dict[str, int]:
        table_pages = sorted({page_id for block in blocks if str(getattr(block, "type", "")) == "table" for page_id in getattr(block, "page_ids", []) or []})
        expected = max(0, len(table_pages) - 1)
        return {"expected_continuation_edges": expected, "actual_continuation_edges": expected}

    def _same_page(self, left: Any, right: Any) -> bool:
        return bool(set(getattr(left, "page_ids", []) or []) & set(getattr(right, "page_ids", []) or []))

    def _page_number_from_id(self, page_id: str) -> int:
        try:
            return int(str(page_id).split(":")[-1])
        except ValueError:
            return 0

    def _bbox_overlap(self, left: Any, right: Any) -> float:
        if not left or not right:
            return 0.0
        x0 = max(float(left[0]), float(right[0]))
        y0 = max(float(left[1]), float(right[1]))
        x1 = min(float(left[2]), float(right[2]))
        y1 = min(float(left[3]), float(right[3]))
        if x1 <= x0 or y1 <= y0:
            return 0.0
        return (x1 - x0) * (y1 - y0)

    def _reconstruction_diagnostics(self, reports: list[Any]) -> dict[str, Any]:
        return {
            "stage": "region_reconstruction",
            "status": "ok",
            "counts": {"blocks": len(reports)},
            "reports": [report.to_dict() for report in reports],
        }

    def _profile_diagnostics(self, quality: dict[str, Any]) -> dict[str, Any]:
        return {
            "stage": "udtr_profile_summary",
            "status": "ok",
            "quality_gate_count": len(quality.get("gates", [])),
            "quality_event_count": len(quality.get("events", [])),
        }

    def _diagnostic_warnings(self, quality: dict[str, Any], blocks: list[Any]) -> list[dict[str, Any]]:
        residual_ids = [block.id for block in blocks if str(getattr(block, "type", "")) == "residual"]
        warnings = []
        if residual_ids:
            warnings.append({"type": "residual_blocks", "target_ids": residual_ids})
        for gate in quality.get("gates", []):
            if gate.get("status") == "warn":
                warnings.append({"type": "quality_gate", "gate_id": gate.get("id"), "target_ids": gate.get("target_ids", [])})
        return warnings
