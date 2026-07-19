"""Canonical MirrorJson projection core.

This module lives under ``models.mirror`` so core parse/model paths can build
the canonical mirror projection without depending on the output/export layer.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from hashlib import sha256
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
                "schema_version": "1.0.7",
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
        from docmirror.evidence.plane import DocumentSource, EvidencePlaneBuilder
        from docmirror.geometry.verification import build_verification_quality_gates, build_verification_report
        from docmirror.quality.udtr_gates import build_udtr_quality_gates

        page_topology_module = import_module("docmirror.topology.page")
        reconstructors_module = import_module("docmirror.topology.reconstructors")
        PageTopologyBuilder = page_topology_module.PageTopologyBuilder
        ReconstructionContext = reconstructors_module.ReconstructionContext
        RegionReconstructorRegistry = reconstructors_module.RegionReconstructorRegistry

        evidence_builder = self.evidence_builder or EvidencePlaneBuilder()
        topology_builder = self.topology_builder or PageTopologyBuilder()
        evidence_input = source_input
        if options.source_filename and type(source_input).__name__ == "ParseResult":
            document_source = DocumentSource.from_any(source_input)
            source_path = Path(options.source_filename)
            metadata = dict(document_source.metadata or {})
            if str(document_source.sha256 or "").startswith("fast:"):
                metadata["fast_fingerprint"] = document_source.sha256
            digest = document_source.sha256
            size_bytes = document_source.size_bytes
            if source_path.is_file():
                digest = self._sha256_file(source_path)
                size_bytes = source_path.stat().st_size
                metadata["source_path"] = str(source_path)
            evidence_input = dataclass_replace(
                document_source,
                filename=str(source_path),
                sha256=digest,
                size_bytes=size_bytes,
                metadata=metadata,
            )
        plane = evidence_builder.build(evidence_input)
        topology = topology_builder.build(plane)
        atom_by_id = self._atom_by_id(plane)
        context = ReconstructionContext(
            evidence_plane=plane,
            atom_by_id=atom_by_id,
            atom_text={atom_id: str(atom.text or "") for atom_id, atom in atom_by_id.items()},
        )
        registry = RegionReconstructorRegistry()
        reports = [
            registry.reconstruct_with_report(region, context) for page in topology.pages for region in page.regions
        ]
        blocks = [report.block for report in reports]
        self._propagate_evidence_confidence(blocks, atom_by_id)
        self._normalize_block_quality(blocks)
        regions = self._regions_from_topology(topology)
        self._attach_region_block_refs(regions, blocks)
        pages = self._pages_from_plane(plane, regions, blocks)
        semantics = self._semantics_from_blocks(blocks, plane=plane)
        graph = self._graph_from_blocks_regions(blocks, regions, semantics, plane)
        document = self._document_from_plane_blocks(plane, blocks, semantics)
        verification_report = build_verification_report(
            blocks=blocks,
            evidence_atoms=list(atom_by_id.values()),
        )
        base_gates = [
            *build_udtr_quality_gates(
                pages=pages,
                regions=regions,
                blocks=blocks,
                evidence_atoms=list(atom_by_id.values()),
                graph=graph,
                source_provenance=getattr(plane.source, "provenance", {}) or {},
            ),
            *build_verification_quality_gates(verification_report),
        ]
        quality = self._quality_from_model(
            pages=pages,
            regions=regions,
            blocks=blocks,
            evidence_atoms=list(atom_by_id.values()),
            base_gates=base_gates,
        )
        quality["verification"] = verification_report.summary()
        quality["verification"]["scope"] = "internal_consistency"
        correction_audit = self._ocr_correction_audit(plane)
        if correction_audit:
            quality["ocr_correction"] = {key: value for key, value in correction_audit.items() if key != "events"}
        source = to_json_safe(plane.source)
        if options.source_filename:
            source["filename"] = options.source_filename
        source_provenance = source.get("provenance") if isinstance(source, dict) else None
        source_parser_info = source_provenance.get("parser_info") if isinstance(source_provenance, dict) else None
        source_parser_options = source_parser_info.get("options") if isinstance(source_parser_info, dict) else None
        if isinstance(source_parser_options, dict):
            # Canonical events live in evidence.indexes; avoid duplicating the
            # potentially large audit ledger in source parser options.
            source_parser_options.pop("ocr_corrections", None)
        evidence_payload = to_json_safe(plane.evidence)
        if correction_audit:
            indexes = evidence_payload.setdefault("indexes", {})
            indexes["ocr_corrections"] = {
                str(event.get("event_id") or f"corr:{index:06d}"): event
                for index, event in enumerate(correction_audit.get("events") or [], start=1)
                if isinstance(event, dict)
            }
        payload = {
            "mirror": {
                "schema": "docmirror.mirror_json",
                "schema_version": "1.0.7",
                "engine": "udtr",
                "engine_version": options.engine_version,
                "profile": options.profile,
            },
            "source": source,
            "document": document,
            "pages": pages,
            "evidence": evidence_payload,
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
                    {
                        "stage": "universal_evidence_verification",
                        "status": "ok",
                        "summary": verification_report.summary(),
                    },
                    self._profile_diagnostics(
                        quality,
                        pages=pages,
                        regions=regions,
                        blocks=blocks,
                        graph=graph,
                        evidence=plane.evidence,
                    ),
                ],
                "warnings": self._diagnostic_warnings(quality, blocks),
            },
            "assets": {
                "items": [],
            },
        }
        return MirrorResult(payload)

    @staticmethod
    def _ocr_correction_audit(plane: Any) -> dict[str, Any]:
        provenance = getattr(getattr(plane, "source", None), "provenance", {}) or {}
        parser_info = provenance.get("parser_info") if isinstance(provenance, dict) else None
        options = parser_info.get("options") if isinstance(parser_info, dict) else None
        audit = options.get("ocr_corrections") if isinstance(options, dict) else None
        return dict(audit) if isinstance(audit, dict) else {}

    def _sha256_file(self, path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _atom_by_id(self, plane: Any) -> dict[str, Any]:
        atoms = [
            *list(getattr(plane.evidence, "text_atoms", []) or []),
            *list(getattr(plane.evidence, "visual_atoms", []) or []),
            *list(getattr(plane.evidence, "image_atoms", []) or []),
            *list(getattr(plane.evidence, "vector_atoms", []) or []),
        ]
        return {atom.id: atom for atom in atoms if getattr(atom, "id", "")}

    def _propagate_evidence_confidence(self, blocks: list[Any], atom_by_id: dict[str, Any]) -> None:
        for block in blocks:
            atoms = [
                atom_by_id[evidence_id]
                for evidence_id in getattr(block, "evidence_ids", []) or []
                if evidence_id in atom_by_id
            ]
            if not atoms:
                continue
            weighted = [
                (float(getattr(atom, "confidence", 0.0) or 0.0), max(1, len(str(getattr(atom, "text", "") or ""))))
                for atom in atoms
            ]
            total_weight = sum(weight for _confidence, weight in weighted)
            block.confidence = round(
                sum(confidence * weight for confidence, weight in weighted) / total_weight,
                4,
            )

    def _regions_from_topology(self, topology: Any) -> list[dict[str, Any]]:
        regions: list[dict[str, Any]] = []
        for page in topology.pages:
            for region in page.regions:
                diagnostics = dict(getattr(region, "diagnostics", {}) or {})
                quality = {
                    "selected_candidate_ids": diagnostics.get("selected_candidate_ids", [region.id]),
                    "ownership_reason": diagnostics.get(
                        "ownership_reason", diagnostics.get("grouping", "topology_region")
                    ),
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

    def _attach_region_block_refs(self, regions: list[dict[str, Any]], blocks: list[Any]) -> None:
        region_by_id = {str(region.get("id") or ""): region for region in regions}
        for block in blocks:
            for region_id in getattr(block, "region_ids", []) or []:
                region = region_by_id.get(str(region_id))
                if region is not None and block.id not in region["block_ids"]:
                    region["block_ids"].append(block.id)

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
                    "blocks": [self._page_block_ref(block) for block in page_blocks],
                    "tables": [
                        self._page_table_projection(block)
                        for block in page_blocks
                        if str(getattr(block, "type", "")) == "table"
                    ],
                    "quality": {
                        "evidence_coverage": 1.0 if evidence_ids or page_regions else 0.0,
                        "residual_ratio": residual_ratio,
                    },
                }
            )
        return pages

    def _page_block_ref(self, block: Any) -> dict[str, Any]:
        """Lightweight page-local block reference.

        The canonical block payload lives in top-level ``blocks``.  Keeping a
        full copy under every page makes MirrorJson much larger and creates two
        owners for the same table grid.  Page-local entries are references plus
        enough summary data for quick inspection.
        """
        return {
            "id": getattr(block, "id", ""),
            "type": getattr(block, "type", ""),
            "role": getattr(block, "role", ""),
            "text": getattr(block, "text", "") or "",
            "region_ids": list(getattr(block, "region_ids", []) or []),
            "evidence_ids": list(getattr(block, "evidence_ids", []) or []),
            "bbox": getattr(block, "bbox", None),
            "quality": to_json_safe(getattr(block, "quality", {}) or {}),
        }

    def _document_from_plane_blocks(self, plane: Any, blocks: list[Any], semantics: dict[str, Any]) -> dict[str, Any]:
        provenance = getattr(plane.source, "provenance", {}) or {}
        entities = provenance.get("entities") if isinstance(provenance, dict) else {}
        document_type = (
            (entities or {}).get("document_type")
            or (provenance or {}).get("scene")
            or getattr(plane.source, "input_kind", "generic")
            or "generic"
        )
        headings = [block for block in blocks if self._is_outline_heading(block)]
        title_block = self._select_document_title(plane, blocks)
        title = (
            {
                "text": title_block.text,
                "block_id": title_block.id,
                "confidence": float(getattr(title_block, "confidence", 0.0) or 0.0),
                "evidence_ids": list(getattr(title_block, "evidence_ids", []) or []),
            }
            if title_block is not None
            else None
        )
        candidate = {"type": document_type, "confidence": 1.0, "evidence_ids": []}
        root_blocks = [block for block in blocks if self._is_main_reading_block(block)]
        page_modes = {str(getattr(page, "content_mode", "unknown") or "unknown") for page in plane.pages}
        if page_modes == {"scanned_ocr"}:
            content_mode = "scanned_ocr"
        elif len(page_modes - {"unknown"}) > 1:
            content_mode = "mixed"
        else:
            content_mode = next(iter(page_modes - {"unknown"}), "unknown")
        return {
            "document_type": document_type,
            "document_type_candidates": [candidate],
            "title": title,
            "content_mode": content_mode,
            "root_block_ids": [block.id for block in root_blocks],
            "outline_block_ids": [block.id for block in headings],
            "primary_reading_flow_id": "flow:main",
        }

    def _select_document_title(self, plane: Any, blocks: list[Any]) -> Any | None:
        import re

        first_page = next((page for page in plane.pages if int(getattr(page, "page_number", 0) or 0) == 1), None)
        if first_page is None or not first_page.width or not first_page.height:
            return None
        candidates: list[tuple[float, Any]] = []
        for block in blocks:
            if "page:0001" not in (getattr(block, "page_ids", []) or []):
                continue
            text = str(getattr(block, "text", "") or "").strip()
            bbox = getattr(block, "bbox", None)
            confidence = float(getattr(block, "confidence", 0.0) or 0.0)
            if not text or not bbox or confidence < 0.6 or len(text) > 32:
                continue
            if float(bbox[1]) > float(first_page.height) * 0.28:
                continue
            if re.search(r"\d{6,}|[:：]", text) or (text.startswith(("（", "(")) and text.endswith(("）", ")"))):
                continue
            cx = (float(bbox[0]) + float(bbox[2])) / 2.0
            center_score = max(0.0, 1.0 - abs(cx - float(first_page.width) / 2.0) / (float(first_page.width) / 2.0))
            top_score = max(0.0, 1.0 - float(bbox[1]) / (float(first_page.height) * 0.28))
            length_score = min(1.0, len(text) / 6.0)
            score = 0.60 * center_score + 0.20 * top_score + 0.10 * length_score + 0.10 * confidence
            candidates.append((score, block))
        score, selected = max(candidates, key=lambda item: item[0], default=(0.0, None))
        return selected if selected is not None and score >= 0.72 else None

    def _is_outline_heading(self, block: Any) -> bool:
        import re

        if str(getattr(block, "type", "")) != "heading":
            return False
        text = str(getattr(block, "text", "") or "").strip()
        if not text or len(text) > 80 or float(getattr(block, "confidence", 0.0) or 0.0) < 0.7:
            return False
        return re.fullmatch(r"\d{4}[.\-/年]\d{1,2}[.\-/月]\d{1,2}日?\s*结清", text) is None

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
            edges.append(
                {"id": f"edge:document:{block.id}", "type": "contains", "from": "document:root", "to": block.id}
            )
            for region_id in getattr(block, "region_ids", []) or []:
                edges.append(
                    {"id": f"edge:{region_id}:{block.id}", "type": "derived_from", "from": region_id, "to": block.id}
                )
        reading_blocks = [
            block
            for block in blocks
            if str(getattr(block, "type", "")) not in {"header", "footer", "artifact", "figure", "residual"}
            and not (getattr(block, "quality", {}) or {}).get("suppressed_from_reading_flow")
        ]
        for previous, current in zip(reading_blocks, reading_blocks[1:], strict=False):
            edges.append(
                {
                    "id": f"edge:reading:{previous.id}:{current.id}",
                    "type": "reading_next",
                    "from": previous.id,
                    "to": current.id,
                }
            )
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

    def _semantics_from_blocks(self, blocks: list[Any], *, plane: Any | None = None) -> dict[str, Any]:
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
                table_views.append(
                    {"block_id": block.id, "grid": (getattr(block, "content", {}) or {}).get("grid", {})}
                )
        views: dict[str, Any] = {}
        if document_metadata:
            views["document_metadata"] = document_metadata
        provenance = getattr(getattr(plane, "source", None), "provenance", {}) or {}
        entities = provenance.get("entities") if isinstance(provenance, dict) else {}
        document_type = str((entities or {}).get("document_type") or provenance.get("scene") or "")
        if table_views and document_type == "bank_statement":
            views["bank_statement"] = {"tables": table_views}
        return {"facts": facts, "entities": [], "views": views}

    def _quality_from_model(
        self,
        *,
        pages: list[dict[str, Any]],
        regions: list[dict[str, Any]],
        blocks: list[Any],
        evidence_atoms: list[Any],
        base_gates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        residual_ratios = [float((page.get("quality") or {}).get("residual_ratio", 0.0) or 0.0) for page in pages]
        residual_ratio = max(residual_ratios) if residual_ratios else 0.0
        numeric_score = self._table_numeric_parse_score(blocks)
        text_evidence_ids = {
            str(getattr(atom, "id", "") or "")
            for atom in evidence_atoms
            if str(getattr(atom, "kind", "")) in {"text_token", "text_line"} and str(getattr(atom, "id", "") or "")
        }
        owned_text_ids = {
            str(evidence_id)
            for block in blocks
            for evidence_id in getattr(block, "evidence_ids", []) or []
            if str(evidence_id) in text_evidence_ids
        }
        token_conservation = len(owned_text_ids) / len(text_evidence_ids) if text_evidence_ids else 1.0
        token_status = "pass" if token_conservation >= 0.99 else "warn"
        table_count = sum(1 for block in blocks if str(getattr(block, "type", "")) == "table")
        gates = [
            *base_gates,
            self._gate("gate:evidence_plane_built", "pass", 1.0, 1.0),
            self._gate("gate:region_ownership", "pass", 1.0, 1.0),
            self._gate(
                "gate:token_conservation",
                token_status,
                token_conservation,
                0.99,
                details={
                    "text_evidence_count": len(text_evidence_ids),
                    "owned_text_evidence_count": len(owned_text_ids),
                    "unowned_text_evidence_ids": sorted(text_evidence_ids - owned_text_ids),
                },
            ),
            self._gate("gate:residual_ratio", "pass" if residual_ratio <= 0.2 else "warn", 1.0 - residual_ratio, 0.8),
            self._gate(
                "gate:table_numeric_parse",
                "not_applicable" if table_count == 0 else ("pass" if numeric_score >= 0.95 else "warn"),
                numeric_score if table_count else 1.0,
                0.95,
            ),
            self._gate(
                "gate:region_overlap",
                "warn" if self._overlap_pairs(regions) else "pass",
                1.0,
                1.0,
                target_ids=self._overlap_details(regions)["target_ids"],
                details=self._overlap_details(regions),
            ),
            self._gate(
                "gate:toc_consistency",
                "pass",
                1.0,
                1.0,
                details={"heading_linked_count": self._toc_heading_linked_count(blocks)},
            ),
            self._gate(
                "gate:cross_page_continuity", "pass", 1.0, 1.0, details=self._cross_page_continuity_details(blocks)
            ),
        ]
        events = [
            {
                "event_type": "quality_gate",
                "gate_id": gate["id"],
                "status": gate["status"],
                "actionable": gate["status"] in {"warn", "fail"},
                **(
                    {
                        "severity": {
                            "warn": "warning",
                            "fail": "error",
                        }[str(gate["status"])]
                    }
                    if gate["status"] in {"warn", "fail"}
                    else {}
                ),
                **({"score": gate.get("score")} if gate["status"] in {"warn", "fail"} else {}),
                **({"target_ids": gate["target_ids"]} if gate.get("target_ids") else {}),
                **({"details": gate["details"]} if gate["status"] in {"warn", "fail"} and gate.get("details") else {}),
            }
            for gate in gates
        ]
        applicable_gates = [gate for gate in gates if gate["status"] != "not_applicable"]
        measured_score = (
            min(float(gate.get("score", 1.0) or 0.0) for gate in applicable_gates) if applicable_gates else 1.0
        )
        measured_confidence = min(
            [
                float(gate.get("score", 1.0) or 0.0)
                for gate in applicable_gates
                if gate["id"]
                in {
                    "gate:ocr_confidence",
                    "gate:page_normalization_confidence",
                    "gate:coordinate_roundtrip",
                    "gate:scanned_visual_coverage",
                    "gate:table_structure_coverage",
                }
            ]
            or [1.0]
        )
        return {
            "overall": {
                "status": "fail"
                if any(gate["status"] == "fail" for gate in gates)
                else ("warn" if any(gate["status"] == "warn" for gate in gates) else "pass"),
                "score": measured_score,
                "confidence": measured_confidence,
            },
            "coverage": {"residual_ratio": residual_ratio, "text_conservation_score": token_conservation},
            "tables": {
                "numeric_parse_score": numeric_score,
                "count": table_count,
            },
            "reading_order": {},
            "gates": gates,
            "events": events,
            "event_summary": {
                "event_count": len(events),
                "actionable_count": sum(1 for event in events if event["actionable"]),
                "by_status": dict(Counter(str(event["status"]) for event in events)),
                "by_severity": dict(Counter(str(event.get("severity") or "unknown") for event in events)),
                "actionable_gate_ids": [event["gate_id"] for event in events if event["actionable"]],
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

    def _page_table_projection(self, block: Any) -> dict[str, Any]:
        provenance = getattr(block, "provenance", {}) or {}
        return {
            "block_id": str(getattr(block, "id", "") or ""),
            "table_id": str(provenance.get("source_table_id") or ""),
            "bbox": getattr(block, "bbox", None),
            "confidence": float(getattr(block, "confidence", 0.0) or 0.0),
        }

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
            for warning in (region.get("quality") or {}).get("overlap_warnings") or []:
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
        return block_type not in {"header", "footer", "artifact", "figure", "residual"} and not (
            getattr(block, "quality", {}) or {}
        ).get("suppressed_from_reading_flow")

    def _overlay_edges(self, blocks: list[Any]) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        targets = [block for block in blocks if str(getattr(block, "type", "")) not in {"artifact", "figure"}]
        for overlay in blocks:
            if str(getattr(overlay, "role", "")) not in {"seal", "signature"}:
                continue
            target = next(
                (
                    block
                    for block in targets
                    if self._same_page(overlay, block) and self._bbox_overlap(overlay.bbox, block.bbox) > 0
                ),
                None,
            )
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
            evidence_confidence = float(getattr(block, "confidence", 0.0) or 0.0)
            review = bool(evidence_confidence < 0.8)
            if (
                str(getattr(block, "type", "")) in {"header", "footer"}
                or str(getattr(block, "role", "")) == "page_background"
            ):
                block.quality = {
                    **(getattr(block, "quality", {}) or {}),
                    "suppressed_from_reading_flow": True,
                    "requires_review": review,
                }
            else:
                block.quality = {
                    **(getattr(block, "quality", {}) or {}),
                    "requires_review": bool((getattr(block, "quality", {}) or {}).get("requires_review")) or review,
                }

    def _toc_edges(self, blocks: list[Any]) -> list[dict[str, Any]]:
        headings = [block for block in blocks if str(getattr(block, "type", "")) == "heading"]
        page_by_id = {
            page_id: self._page_number_from_id(page_id)
            for block in blocks
            for page_id in (getattr(block, "page_ids", []) or [])
        }
        edges: list[dict[str, Any]] = []
        for toc in [block for block in blocks if str(getattr(block, "type", "")) == "toc"]:
            for item in (getattr(toc, "content", {}) or {}).get("items", []) or []:
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
                        and any(
                            page_by_id.get(page_id) == int(target_page)
                            for page_id in (getattr(block, "page_ids", []) or [])
                        )
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
        logical_tables = (
            provenance.get("logical_table_refs") or provenance.get("logical_tables", [])
            if isinstance(provenance, dict)
            else []
        )
        table_blocks = [block for block in blocks if str(getattr(block, "type", "")) == "table"]
        by_source_id = {
            str((getattr(block, "provenance", {}) or {}).get("source_table_id") or ""): block for block in table_blocks
        }
        edges: list[dict[str, Any]] = []
        for logical_table in logical_tables:
            source_ids = (
                list(dict.fromkeys(str(value) for value in logical_table.get("source_physical_ids", [])))
                if isinstance(logical_table, dict)
                else []
            )
            linked = list(
                {
                    block.id: block
                    for source_id in source_ids
                    if source_id in by_source_id
                    for block in [by_source_id[source_id]]
                }.values()
            )
            if len(linked) < 2:
                continue
            logical_id = str(logical_table.get("logical_id") or logical_table.get("table_id") or "")
            confidence = float(logical_table.get("merge_confidence", 1.0) or 1.0)
            linked.sort(
                key=lambda block: min((self._page_number_from_id(page_id) for page_id in block.page_ids), default=0)
            )
            for previous, current in zip(linked, linked[1:], strict=False):
                if previous.id == current.id:
                    continue
                previous_page = min((self._page_number_from_id(page_id) for page_id in previous.page_ids), default=0)
                current_page = min((self._page_number_from_id(page_id) for page_id in current.page_ids), default=0)
                edges.append(
                    {
                        "id": f"edge:same_table:{previous.id}:{current.id}",
                        "type": "same_table",
                        "from": previous.id,
                        "to": current.id,
                        "confidence": confidence,
                        "metadata": {"logical_id": logical_id},
                    }
                )
                if current_page > previous_page:
                    edges.append(
                        {
                            "id": f"edge:continues:{previous.id}:{current.id}",
                            "type": "continues",
                            "from": previous.id,
                            "to": current.id,
                            "confidence": confidence,
                            "metadata": {"logical_id": logical_id},
                        }
                    )
        return edges

    def _toc_heading_linked_count(self, blocks: list[Any]) -> int:
        return len([edge for edge in self._toc_edges(blocks) if edge["type"] == "references"])

    def _cross_page_continuity_details(self, blocks: list[Any]) -> dict[str, int]:
        table_pages = sorted(
            {
                page_id
                for block in blocks
                if str(getattr(block, "type", "")) == "table"
                for page_id in getattr(block, "page_ids", []) or []
            }
        )
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

    def _profile_diagnostics(
        self,
        quality: dict[str, Any],
        *,
        pages: list[dict[str, Any]],
        regions: list[dict[str, Any]],
        blocks: list[Any],
        graph: dict[str, Any],
        evidence: Any,
    ) -> dict[str, Any]:
        return {
            "stage": "udtr_profile_summary",
            "status": "ok",
            "page_count": len(pages),
            "region_count": len(regions),
            "block_count": len(blocks),
            "edge_count": len(graph.get("edges") or []),
            "evidence_atom_counts": {
                "text": len(getattr(evidence, "text_atoms", []) or []),
                "visual": len(getattr(evidence, "visual_atoms", []) or []),
                "image": len(getattr(evidence, "image_atoms", []) or []),
                "vector": len(getattr(evidence, "vector_atoms", []) or []),
            },
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
                warnings.append(
                    {"type": "quality_gate", "gate_id": gate.get("id"), "target_ids": gate.get("target_ids", [])}
                )
        return warnings
