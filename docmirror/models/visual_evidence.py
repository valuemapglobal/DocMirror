# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Visual Evidence Graph — canonical explainability data model.

Forms the core of the Explainability & Visualization Contract (XVC).
Every visual element (page, block, table, cell, field, quality, diff)
is represented as a node with edges tracking derivation chains.

Usage::

    from docmirror.models.visual_evidence import (
        VisualNode,
        VisualEdge,
        VisualEvidenceGraph,
    )
    graph = VisualEvidenceGraph(document_id="doc_001")
    graph.add_node(VisualNode(
        id="block:p1:b0",
        kind="block",
        label="Block #1",
        page=1,
        bbox=[20, 40, 520, 90],
    ))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class VisualNode:
    """A single explainable element in the Visual Evidence Graph."""

    id: str = ""
    kind: Literal[
        "page",
        "block",
        "span",
        "token",
        "table",
        "cell",
        "field",
        "record",
        "quality_issue",
        "needs_review",
        "diff_change",
        "fallback",
        "unresolved",
        "section",
        "reading_order",
        "key_value",
        "image",
        "formula",
    ] = "block"
    label: str = ""
    value_preview: str = ""
    raw_preview: str = ""
    normalized_preview: dict[str, Any] | None = None
    page: int = 0
    bbox: list[float] | None = None
    confidence: float = 1.0
    review: Literal["auto_accepted", "manual_optional", "needs_review", "needs_evidence"] = "auto_accepted"
    source_refs: list[str] = field(default_factory=list)
    field_path: str = ""
    edition: str = ""
    support_level: str = ""
    data_classification: str = "internal"
    redaction: str = "none"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "value_preview": self.value_preview,
            "raw_preview": self.raw_preview,
            "normalized_preview": self.normalized_preview,
            "page": self.page,
            "bbox": self.bbox,
            "confidence": self.confidence,
            "review": self.review,
            "source_refs": self.source_refs,
            "field_path": self.field_path,
            "edition": self.edition,
            "support_level": self.support_level,
            "data_classification": self.data_classification,
            "redaction": self.redaction,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualNode:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class VisualEdge:
    """A derivation edge between two VisualNodes."""

    id: str = ""
    type: Literal["derived_from", "contains", "references", "depends_on", "conflicts_with"] = "derived_from"
    from_node: str = ""
    to_node: str = ""
    method: str = ""
    confidence: float = 1.0
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "from": self.from_node,
            "to": self.to_node,
            "method": self.method,
            "confidence": self.confidence,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualEdge:
        d = dict(data)
        d["from_node"] = d.pop("from", "")
        d["to_node"] = d.pop("to", "")
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class VisualEvidenceGraph:
    """The single explainability fact source for a document parse."""

    version: int = 1
    document_id: str = ""
    task_id: str = ""
    coordinate_system: str = "pdf_points_top_left"

    pages: list[dict[str, Any]] = field(default_factory=list)
    nodes: dict[str, VisualNode] = field(default_factory=dict)
    edges: list[VisualEdge] = field(default_factory=list)
    layers: list[dict[str, Any]] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    outcomes: dict[str, Any] = field(default_factory=dict)
    redaction: dict[str, Any] = field(default_factory=dict)

    def add_page(self, page: int, width: float = 0, height: float = 0, image_ref: str = "") -> None:
        self.pages.append(
            {
                "page": page,
                "width": width,
                "height": height,
                "image_ref": image_ref,
                "nodes": [],
            }
        )

    def add_node(self, node: VisualNode) -> None:
        self.nodes[node.id] = node
        for pg in self.pages:
            if pg["page"] == node.page:
                pg["nodes"].append(node.id)
                break

    def add_edge(self, edge: VisualEdge) -> None:
        self.edges.append(edge)

    def resolve_node(self, node_id: str) -> VisualNode | None:
        return self.nodes.get(node_id)

    def resolve_field(self, field_path: str) -> VisualNode | None:
        for node in self.nodes.values():
            if node.field_path == field_path and node.kind == "field":
                return node
        return None

    def nodes_by_page(self, page: int) -> list[VisualNode]:
        return [n for n in self.nodes.values() if n.page == page]

    def nodes_by_kind(self, kind: str) -> list[VisualNode]:
        return [n for n in self.nodes.values() if n.kind == kind]

    def nodes_needing_review(self) -> list[VisualNode]:
        return [n for n in self.nodes.values() if n.review in ("needs_review", "needs_evidence")]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "document_id": self.document_id,
            "task_id": self.task_id,
            "coordinate_system": self.coordinate_system,
            "pages": self.pages,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "layers": self.layers,
            "quality": self.quality,
            "outcomes": self.outcomes,
            "redaction": self.redaction,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualEvidenceGraph:
        graph = cls(
            version=data.get("version", 1),
            document_id=data.get("document_id", ""),
            task_id=data.get("task_id", ""),
            coordinate_system=data.get("coordinate_system", "pdf_points_top_left"),
            pages=data.get("pages", []),
            layers=data.get("layers", []),
            quality=data.get("quality", {}),
            outcomes=data.get("outcomes", {}),
            redaction=data.get("redaction", {}),
        )
        for node_id, node_data in data.get("nodes", {}).items():
            graph.nodes[node_id] = VisualNode.from_dict(node_data)
        for edge_data in data.get("edges", []):
            graph.edges.append(VisualEdge.from_dict(edge_data))
        return graph


__all__ = [
    "VisualNode",
    "VisualEdge",
    "VisualEvidenceGraph",
]
