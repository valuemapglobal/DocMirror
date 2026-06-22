# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Source Ref Resolver — resolves source_refs to page/bbox/cell.

GA 1.0 design §5.2 / §9 Wave 1: Every field_path, source_ref, bbox_ref,
token_ref, or cell_ref in the Visual Evidence Graph must resolve to a
concrete page canvas location.

The resolver also performs coordinate validation (W1-05, bbox not out of
page bounds) and tracks unresolved evidence entries (W1-04).

Usage::

    from docmirror.evidence.source_resolver import SourceRefResolver
    resolver = SourceRefResolver(graph)
    resolved = resolver.resolve("cell:p3:t0:r2:c4")
    print(resolved.page, resolved.bbox)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from docmirror.models.visual_evidence import VisualEvidenceGraph, VisualNode


@dataclass
class ResolvedLocation:
    """A resolved source reference with page canvas coordinates."""

    source_ref: str = ""
    node_id: str = ""
    page: int = 0
    bbox: list[float] | None = None
    bbox_space: str = "pdf_points_top_left"
    page_width: float = 0.0
    page_height: float = 0.0
    kind: str = ""
    label: str = ""
    value_preview: str = ""
    confidence: float = 0.0
    review: str = "auto_accepted"
    valid: bool = True
    coordinate_issue: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "node_id": self.node_id,
            "page": self.page,
            "bbox": self.bbox,
            "bbox_space": self.bbox_space,
            "page_width": self.page_width,
            "page_height": self.page_height,
            "kind": self.kind,
            "label": self.label,
            "value_preview": self.value_preview,
            "confidence": self.confidence,
            "review": self.review,
            "valid": self.valid,
            "coordinate_issue": self.coordinate_issue,
        }


@dataclass
class UnresolvedRef:
    """A source_ref or field_path that could not be resolved."""

    ref: str = ""
    reason: str = "not_found_in_graph"
    field_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "reason": self.reason,
            "field_path": self.field_path,
        }


class SourceRefResolver:
    """Resolves source_refs, field_paths, and node IDs to concrete locations.

    Consumes a VisualEvidenceGraph and provides:
    - ``resolve(ref)`` → ResolvedLocation or None
    - ``resolve_field(field_path)`` → ResolvedLocation or None
    - ``validate_coordinates()`` → list of coordinate issues
    - ``unresolved_refs`` → accumulated unresolved references
    - ``needs_review_fields`` → fields that need human review
    """

    def __init__(self, graph: VisualEvidenceGraph) -> None:
        self._graph = graph
        self._unresolved: list[UnresolvedRef] = []
        self._coordinate_issues: list[dict[str, Any]] = []

        # Build lookup indices
        self._by_source_ref: dict[str, str] = {}
        self._by_field_path: dict[str, str] = {}
        self._by_node_id: dict[str, VisualNode] = {}

        for nid, node in graph.nodes.items():
            self._by_node_id[nid] = node
            for sr in node.source_refs:
                if sr and sr not in self._by_source_ref:
                    self._by_source_ref[sr] = nid
            if node.field_path and node.field_path not in self._by_field_path:
                self._by_field_path[node.field_path] = nid

        self._page_dims: dict[int, tuple[float, float]] = {}
        for pg in graph.pages:
            pn = pg.get("page", 0)
            if pn:
                self._page_dims[pn] = (
                    float(pg.get("width", 595.0) or 595.0),
                    float(pg.get("height", 842.0) or 842.0),
                )

    # ── Public API ──────────────────────────────────────────────────────

    def resolve(self, ref: str) -> ResolvedLocation | None:
        """Resolve a source_ref, field_path, or node ID to a location.

        Tries in order: source_ref index → field_path index → node_id lookup.
        """
        # Try as source_ref
        if ref in self._by_source_ref:
            return self._resolve_node(self._by_source_ref[ref], source_ref=ref)

        # Try as field_path
        if ref in self._by_field_path:
            return self._resolve_node(self._by_field_path[ref], source_ref=ref)

        # Try as node_id
        if ref in self._by_node_id:
            return self._resolve_node(ref, source_ref=ref)

        # Not found — register as unresolved
        self._unresolved.append(UnresolvedRef(ref=ref, reason="not_found_in_graph"))
        return None

    def resolve_field(self, field_path: str) -> ResolvedLocation | None:
        """Resolve a field_path to a location."""
        if field_path in self._by_field_path:
            return self._resolve_node(self._by_field_path[field_path],
                                      source_ref=field_path)
        # Try graph.resolve_field as fallback
        node = self._graph.resolve_field(field_path)
        if node:
            return self._resolve_node(node.id, source_ref=field_path)

        self._unresolved.append(UnresolvedRef(
            ref=field_path, reason="field_not_found_in_graph",
            field_path=field_path,
        ))
        return None

    def resolve_all_field_paths(self) -> list[ResolvedLocation]:
        """Resolve every field_path in the graph."""
        locations: list[ResolvedLocation] = []
        seen: set[str] = set()
        for nid, node in self._graph.nodes.items():
            if node.kind == "field" and node.field_path:
                fp = node.field_path
                if fp not in seen:
                    seen.add(fp)
                    locations.append(self._resolve_node(nid, source_ref=fp))
        return locations

    def validate_coordinates(self) -> list[dict[str, Any]]:
        """Validate all bbox coordinates against page bounds (W1-05).

        Returns a list of coordinate issues with node_id, page, bbox, and
        the specific violation.
        """
        issues: list[dict[str, Any]] = []
        for nid, node in self._graph.nodes.items():
            if not node.bbox or not node.page:
                continue
            dims = self._page_dims.get(node.page)
            if not dims:
                continue
            pw, ph = dims
            x0, y0, x1, y1 = node.bbox

            problems: list[str] = []
            if x0 < -pw * 0.1:
                problems.append(f"bbox x0={x0} exceeds negative margin")
            if y0 < -ph * 0.1:
                problems.append(f"bbox y0={y0} exceeds negative margin")
            if x1 > pw * 1.5:
                problems.append(f"bbox x1={x1} far exceeds page width {pw}")
            if y1 > ph * 1.5:
                problems.append(f"bbox y1={y1} far exceeds page height {ph}")
            if x0 >= x1:
                problems.append(f"bbox x0={x0} >= x1={x1}, bbox is empty or inverted")
            if y0 >= y1:
                problems.append(f"bbox y0={y0} >= y1={y1}, bbox is empty or inverted")

            if problems:
                issues.append({
                    "node_id": nid,
                    "page": node.page,
                    "bbox": node.bbox,
                    "page_width": pw,
                    "page_height": ph,
                    "violations": problems,
                    "kind": node.kind,
                    "severity": "error" if any(
                        "x0 >=" in p or "y0 >=" in p for p in problems
                    ) else "warning",
                })

        self._coordinate_issues = issues
        return issues

    @property
    def unresolved_refs(self) -> list[UnresolvedRef]:
        return list(self._unresolved)

    @property
    def needs_review_fields(self) -> list[dict[str, Any]]:
        """Fields that need human review (low confidence, missing evidence)."""
        results: list[dict[str, Any]] = []
        for nid, node in self._graph.nodes.items():
            if node.review in ("needs_review", "needs_evidence"):
                loc = self._resolve_node(nid)
                results.append({
                    "node_id": nid,
                    "kind": node.kind,
                    "label": node.label,
                    "field_path": node.field_path,
                    "page": loc.page if loc else node.page,
                    "bbox": node.bbox,
                    "confidence": node.confidence,
                    "review": node.review,
                    "reason": "low_confidence" if node.confidence < 0.5 else "no_evidence",
                })
        # Also add unresolved references
        for ur in self._unresolved:
            results.append({
                "node_id": "",
                "kind": "unresolved",
                "label": ur.ref,
                "field_path": ur.field_path,
                "page": 0,
                "bbox": None,
                "confidence": 0.0,
                "review": "needs_evidence",
                "reason": ur.reason,
            })
        return results

    @property
    def coordinate_issues(self) -> list[dict[str, Any]]:
        return list(self._coordinate_issues)

    @property
    def summary(self) -> dict[str, Any]:
        total_nodes = len(self._graph.nodes)
        resolved = total_nodes - len(self._unresolved)
        return {
            "total_nodes": total_nodes,
            "resolved": resolved,
            "unresolved": len(self._unresolved),
            "coordinate_issues": len(self._coordinate_issues),
            "needs_review": len(self.needs_review_fields),
            "resolvability": round(resolved / total_nodes, 4) if total_nodes else 0.0,
        }

    # ── Internal ────────────────────────────────────────────────────────

    def _resolve_node(
        self,
        node_id: str,
        source_ref: str = "",
    ) -> ResolvedLocation | None:
        node = self._by_node_id.get(node_id)
        if not node:
            return None
        dims = self._page_dims.get(node.page, (0.0, 0.0))
        pw, ph = dims

        # Coordinate validation for this node
        coord_issue = self._validate_single_bbox(node.bbox, pw, ph)

        return ResolvedLocation(
            source_ref=source_ref or node_id,
            node_id=node_id,
            page=node.page,
            bbox=node.bbox,
            page_width=pw,
            page_height=ph,
            kind=node.kind,
            label=node.label,
            value_preview=node.value_preview,
            confidence=node.confidence,
            review=node.review,
            valid=not coord_issue,
            coordinate_issue=coord_issue,
        )

    @staticmethod
    def _validate_single_bbox(
        bbox: list[float] | None,
        page_width: float,
        page_height: float,
    ) -> str:
        if not bbox or page_width <= 0 or page_height <= 0:
            return ""
        if len(bbox) < 4:
            return "bbox has fewer than 4 coordinates"
        x0, y0, x1, y1 = bbox[:4]
        if x0 >= x1:
            return f"bbox x0={x0} >= x1={x1}, width is non-positive"
        if y0 >= y1:
            return f"bbox y0={y0} >= y1={y1}, height is non-positive"
        if x1 > page_width * 1.5:
            return f"bbox x1={x1} exceeds page width {page_width}"
        if y1 > page_height * 1.5:
            return f"bbox y1={y1} exceeds page height {page_height}"
        return ""


__all__ = [
    "ResolvedLocation",
    "UnresolvedRef",
    "SourceRefResolver",
]
