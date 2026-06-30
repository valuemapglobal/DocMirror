# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Document Flow Graph (DFG) v2 schemas — document-level structure bus.

The DFG is the single source of truth for document-level structure:
nodes, edges, reading flow, outline, cross-page flows, relations, and noise.

Design principles:
  - DFG never rewrites Mirror facts — only builds indices and relationships.
  - Structure is a graph, not just a tree.
  - All outputs (Markdown, RAG, Evidence) must read the same graph.
  - Uncertain repairs are downgraded, never hallucinated.
  - Existing structure fields are preserved for output contract stability.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Node types ──────────────────────────────────────────────────────────────

NodeType = Literal[
    "heading",
    "paragraph",
    "list_item",
    "physical_table",
    "logical_table",
    "image",
    "caption",
    "footnote",
    "formula",
    "header",
    "footer",
    "watermark",
]


class StructureNode(BaseModel):
    """A single document-level structure node — readable, referenceable, auditable.

    Maps directly from physical blocks or inferred logical units (e.g., logical tables).
    Every node must carry fact_refs (Mirror fact identities) and evidence_refs (audit trail).
    """

    node_id: str = ""
    type: NodeType = "paragraph"
    role: str = "body"  # body, header, footer, watermark, caption, footnote, title
    page: int = 1
    bbox: list[float] | None = None
    text: str = ""
    fact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    reading_order: int = 0
    confidence: float = 1.0
    quality_flags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "node_id": "node:p1:b3",
                "type": "paragraph",
                "role": "body",
                "page": 1,
                "bbox": [72.0, 180.0, 520.0, 220.0],
                "text": "本报告期内...",
                "fact_refs": ["text:p1:b3"],
                "evidence_refs": ["text_p1_blk_3"],
                "reading_order": 12,
                "confidence": 0.96,
                "quality_flags": [],
            }
        }
    )


# ── Edge types ───────────────────────────────────────────────────────────────

EdgeType = Literal[
    "reading_next",
    "section_child",
    "continues",
    "caption_of",
    "title_of",
    "footnote_of",
    "formula_number_of",
    "references",
    "suppressed_as_noise",
]


class StructureEdge(BaseModel):
    """A directed relationship between two structure nodes.

    Every edge must carry a relation type, confidence, and policy attribution.
    No edge is silently established — each must be auditable.
    """

    edge_id: str = ""
    type: EdgeType = "reading_next"
    from_node: str = ""  # node_id
    to_node: str = ""  # node_id
    confidence: float = 1.0
    policy: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "edge_id": "edge:p1_b3:p1_b4",
                "type": "reading_next",
                "from_node": "node:p1:b3",
                "to_node": "node:p1:b4",
                "confidence": 0.98,
                "policy": "column_aware_reading_order",
                "evidence_refs": ["layout:p1"],
            }
        }
    )


# ── Reading flow ─────────────────────────────────────────────────────────────


class ReadingFlow(BaseModel):
    """A linear reading sequence through the document — the single source for output order.

    Markdown, RAG, and other consumers must use reading_flow to determine output order.
    Excluded nodes (e.g., headers, footers) are tracked for auditability.
    """

    flow_id: str = ""
    type: str = "main_reading_order"  # main_reading_order, column_flow, etc.
    node_ids: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    confidence: float = 1.0
    profile: str = "human_default"
    excluded_node_ids: list[str] = Field(default_factory=list)
    policy: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossPageFlow(BaseModel):
    """A cross-page continuity flow — paragraph or table spanning multiple pages.

    merged_view is a convenience view for consumers; source nodes remain intact.
    Below-threshold confidence produces candidate_continuation, not auto-merge.
    """

    flow_id: str = ""
    type: str = "cross_page_paragraph"  # cross_page_paragraph, cross_page_table
    node_ids: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    confidence: float = 1.0
    policy: str = ""
    merged_view: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Outline / Section ────────────────────────────────────────────────────────


class SectionNode(BaseModel):
    """Section node in the document outline tree — hierarchical.

    Sections are inferred from heading nodes and bound to page ranges
    and content node ranges.
    """

    node_id: str = ""
    type: str = "section"
    title: str = ""
    level: int = 1
    page_start: int = 1
    page_end: int = 1
    child_ids: list[str] = Field(default_factory=list)
    content_node_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Relation types ───────────────────────────────────────────────────────────

RelationType = Literal[
    "caption_of",
    "title_of",
    "footnote_of",
    "formula_number_of",
    "references",
]


class StructureRelation(BaseModel):
    """A named semantic relation between structure nodes — e.g., caption_of, title_of.

    Relations are distinct from edges: edges are structural (reading order, hierarchy),
    relations are semantic (caption, footnote, formula numbering).
    """

    relation_id: str = ""
    type: RelationType = "caption_of"
    from_node: str = ""  # node_id
    to_node: str = ""  # node_id
    confidence: float = 1.0
    policy: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Noise ────────────────────────────────────────────────────────────────────


class SuppressedNoise(BaseModel):
    """A noise element (header, footer, watermark) that has been suppressed.

    Suppressed noise is excluded from human/rag profiles but preserved
    for forensic auditability.
    """

    node_id: str = ""
    type: str = "header"  # header, footer, watermark
    pages: list[int] = Field(default_factory=list)
    policy: str = "excluded_from_markdown"
    evidence_refs: list[str] = Field(default_factory=list)
    text_sample: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── DFG envelope ─────────────────────────────────────────────────────────────


class DocumentFlowGraph(BaseModel):
    """Complete Document Flow Graph v2 — the structure bus for all outputs.

    This is the top-level DFG object placed in document_structure.version = 2.
    It includes all nodes, edges, flows, outline, relations, and noise.
    """

    version: int = 2
    profile: str = "human_default"
    nodes: list[StructureNode] = Field(default_factory=list)
    edges: list[StructureEdge] = Field(default_factory=list)
    reading_flow: list[ReadingFlow] = Field(default_factory=list)
    outline: list[SectionNode] = Field(default_factory=list)
    cross_page_flows: list[CrossPageFlow] = Field(default_factory=list)
    relations: list[StructureRelation] = Field(default_factory=list)
    suppressed_noise: list[SuppressedNoise] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": 2,
                "profile": "human_default",
                "nodes": [],
                "edges": [],
                "reading_flow": [],
                "outline": [],
                "cross_page_flows": [],
                "relations": [],
                "suppressed_noise": [],
                "quality": {},
            }
        }
    )


# ── Profile enum ─────────────────────────────────────────────────────────────

ProfileType = Literal[
    "raw",
    "structure_v2",
    "ga_full",
    "forensic",
]


__all__ = [
    "CrossPageFlow",
    "DocumentFlowGraph",
    "EdgeType",
    "NodeType",
    "ProfileType",
    "ReadingFlow",
    "RelationType",
    "SectionNode",
    "StructureEdge",
    "StructureNode",
    "StructureRelation",
    "SuppressedNoise",
]
