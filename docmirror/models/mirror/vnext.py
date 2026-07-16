# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror JSON vNext schema models.

This module defines the canonical UDTR-era ``_mirror.json`` envelope. The
schema is intentionally document-shaped, not API-response-shaped: no
``code/message/data/meta`` wrapper lives here.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MirrorBaseModel(BaseModel):
    """Base model for forward-compatible Mirror JSON sections."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)


class QualityStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class AtomKind(str, Enum):
    TEXT_TOKEN = "text_token"
    TEXT_LINE = "text_line"
    LINE = "line"
    RECTANGLE = "rectangle"
    EMBEDDED_IMAGE = "embedded_image"
    RENDERED_IMAGE = "rendered_image"
    VISUAL_ARTIFACT = "visual_artifact"
    UNKNOWN = "unknown"


class RegionKind(str, Enum):
    TEXT = "text"
    HEADING = "heading"
    TABLE_LIKE = "table_like"
    FIGURE = "figure"
    IMAGE = "image"
    SEAL = "seal"
    SIGNATURE = "signature"
    BARCODE = "barcode"
    HEADER = "header"
    FOOTER = "footer"
    FOOTNOTE = "footnote"
    MARGIN_NOTE = "margin_note"
    RESIDUAL = "residual"
    UNKNOWN = "unknown"


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    KEY_VALUE_GROUP = "key_value_group"
    TABLE = "table"
    TOC = "toc"
    FIGURE = "figure"
    ARTIFACT = "artifact"
    FOOTNOTE = "footnote"
    HEADER = "header"
    FOOTER = "footer"
    RESIDUAL = "residual"
    UNKNOWN = "unknown"


class GraphNodeKind(str, Enum):
    DOCUMENT = "document"
    PAGE = "page"
    REGION = "region"
    BLOCK = "block"
    FACT = "fact"
    ENTITY = "entity"
    ASSET = "asset"


class GraphEdgeType(str, Enum):
    CONTAINS = "contains"
    READING_NEXT = "reading_next"
    DERIVED_FROM = "derived_from"
    METADATA_OF = "metadata_of"
    CAPTION_OF = "caption_of"
    FOOTNOTE_OF = "footnote_of"
    CONTINUES = "continues"
    SAME_TABLE = "same_table"
    SAME_ENTITY = "same_entity"
    OVERLAYS = "overlays"
    REFERENCES = "references"
    TOC_POINTS_TO = "toc_points_to"
    SECTION_CHILD = "section_child"


class ReadingFlowKind(str, Enum):
    MAIN_READING_ORDER = "main_reading_order"
    COLUMN_FLOW = "column_flow"
    TABLE_FLOW = "table_flow"
    CANDIDATE_FLOW = "candidate_flow"


class CoordinateSystem(MirrorBaseModel):
    unit: str = "pt"
    origin: str = "top_left"
    rotation_normalized: bool = True
    bbox_order: str = "x0_y0_x1_y1"


class IdPolicy(MirrorBaseModel):
    stable_with_same_source_and_config: bool = True
    id_namespace: str = "document"


class MirrorInfo(MirrorBaseModel):
    schema_: str = Field(default="docmirror.mirror_json", alias="schema")
    schema_version: str = "1.0.2"
    engine: str = "udtr"
    engine_version: str = "0.1.0"
    generated_at: str = ""
    profile: str = "canonical_full"
    coordinate_system: CoordinateSystem = Field(default_factory=CoordinateSystem)
    id_policy: IdPolicy = Field(default_factory=IdPolicy)


class SourceInfo(MirrorBaseModel):
    source_id: str = "src:0001"
    filename: str = ""
    mime_type: str = ""
    sha256: str = ""
    size_bytes: int | None = None
    page_count: int = 0
    input_kind: str = "unknown"
    provenance: dict[str, Any] = Field(default_factory=dict)


class TypedValue(MirrorBaseModel):
    raw: Any = ""
    normalized: Any = None
    type: str = "string"
    unit: str | None = None
    confidence: float = 1.0


class DocumentTypeCandidate(MirrorBaseModel):
    type: str = "unknown"
    confidence: float = 1.0
    evidence_ids: list[str] = Field(default_factory=list)


class DocumentInfo(MirrorBaseModel):
    document_id: str = ""
    title: dict[str, Any] | None = None
    languages: list[str] = Field(default_factory=list)
    content_mode: str = "unknown"
    document_type_candidates: list[DocumentTypeCandidate] = Field(default_factory=list)
    root_block_ids: list[str] = Field(default_factory=list)
    outline_block_ids: list[str] = Field(default_factory=list)
    primary_reading_flow_id: str = "flow:main"


class PageInfo(MirrorBaseModel):
    page_id: str = ""
    page_index: int = 0
    page_number: int = 1
    width: float | None = None
    height: float | None = None
    original_rotation: int = 0
    normalized_rotation: int = 0
    coordinate_transform: dict[str, Any] = Field(default_factory=dict)
    content_mode: str = "unknown"
    asset_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    region_ids: list[str] = Field(default_factory=list)
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)


class EvidenceAtom(MirrorBaseModel):
    id: str = ""
    kind: AtomKind = "text_token"
    source_kind: str = "parse_result"
    page_id: str = ""
    text: str | None = None
    bbox: list[float] | None = None
    source_bbox: list[float] | None = None
    coordinate_transform: dict[str, Any] | None = None
    confidence: float = 1.0
    style: dict[str, Any] | None = None
    source_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceStore(MirrorBaseModel):
    text_atoms: list[EvidenceAtom] = Field(default_factory=list)
    visual_atoms: list[EvidenceAtom] = Field(default_factory=list)
    image_atoms: list[EvidenceAtom] = Field(default_factory=list)
    vector_atoms: list[EvidenceAtom] = Field(default_factory=list)
    indexes: dict[str, Any] = Field(default_factory=dict)


class RegionInfo(MirrorBaseModel):
    id: str = ""
    page_id: str = ""
    kind: RegionKind = "unknown"
    role: str = "unknown"
    bbox: list[float] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    parent_region_id: str | None = None
    child_region_ids: list[str] = Field(default_factory=list)
    reading_order: int = 0
    confidence: float = 1.0
    quality: dict[str, Any] = Field(default_factory=dict)


class BlockInfo(MirrorBaseModel):
    id: str = ""
    type: BlockType = "unknown"
    role: str = "body"
    page_ids: list[str] = Field(default_factory=list)
    region_ids: list[str] = Field(default_factory=list)
    bbox: list[float] | None = None
    text: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)
    children: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    quality: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class GraphNode(MirrorBaseModel):
    id: str = ""
    kind: GraphNodeKind = "block"


class GraphEdge(MirrorBaseModel):
    id: str = ""
    type: GraphEdgeType = "reading_next"
    from_: str = Field(default="", alias="from")
    to: str = ""
    confidence: float = 1.0
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReadingFlowInfo(MirrorBaseModel):
    flow_id: str = "flow:main"
    kind: ReadingFlowKind = "main_reading_order"
    node_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class GraphInfo(MirrorBaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    reading_flows: list[ReadingFlowInfo] = Field(default_factory=list)
    outline: list[dict[str, Any]] = Field(default_factory=list)


class EntityInfo(MirrorBaseModel):
    id: str = ""
    type: str = "unknown"
    name: str = ""
    normalized_name: str | None = None
    mention_block_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class FactInfo(MirrorBaseModel):
    id: str = ""
    subject_id: str = ""
    predicate: str = ""
    object: TypedValue = Field(default_factory=TypedValue)
    source_block_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class SemanticsInfo(MirrorBaseModel):
    entities: list[EntityInfo] = Field(default_factory=list)
    facts: list[FactInfo] = Field(default_factory=list)
    views: dict[str, Any] = Field(default_factory=dict)


class OverallQuality(MirrorBaseModel):
    score: float = 0.0
    status: QualityStatus = "warn"
    confidence: float = 0.0


class QualityInfo(MirrorBaseModel):
    overall: OverallQuality = Field(default_factory=OverallQuality)
    coverage: dict[str, Any] = Field(default_factory=dict)
    tables: dict[str, Any] = Field(default_factory=dict)
    reading_order: dict[str, Any] = Field(default_factory=dict)
    gates: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    event_summary: dict[str, Any] = Field(default_factory=dict)


class DiagnosticsInfo(MirrorBaseModel):
    pipeline: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class AssetStore(MirrorBaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class MirrorJsonVNext(MirrorBaseModel):
    mirror: MirrorInfo = Field(default_factory=MirrorInfo)
    source: SourceInfo = Field(default_factory=SourceInfo)
    document: DocumentInfo = Field(default_factory=DocumentInfo)
    pages: list[PageInfo] = Field(default_factory=list)
    evidence: EvidenceStore = Field(default_factory=EvidenceStore)
    regions: list[RegionInfo] = Field(default_factory=list)
    blocks: list[BlockInfo] = Field(default_factory=list)
    graph: GraphInfo = Field(default_factory=GraphInfo)
    semantics: SemanticsInfo = Field(default_factory=SemanticsInfo)
    quality: QualityInfo = Field(default_factory=QualityInfo)
    diagnostics: DiagnosticsInfo = Field(default_factory=DiagnosticsInfo)
    assets: AssetStore = Field(default_factory=AssetStore)

    @property
    def full_text(self) -> str:
        """Best-effort text projection for plugin compatibility."""
        texts: list[str] = []
        for block in self.blocks:
            text = str(block.text or "").strip()
            if text:
                texts.append(text)
        if texts:
            return "\n".join(texts)
        for atom in self.evidence.text_atoms:
            text = str(atom.text or "").strip()
            if text:
                texts.append(text)
        return "\n".join(texts)

    @property
    def entities(self) -> Any:
        """ParseResult-compatible entity projection for plugin runners."""
        from docmirror.models.entities.parse_result import DocumentEntities

        candidates = list(self.document.document_type_candidates or [])
        best = max(candidates, key=lambda item: float(item.confidence or 0.0), default=None)
        provenance_entities = self.source.provenance.get("entities") if isinstance(self.source.provenance, dict) else {}
        provenance_type = ""
        provenance_specific: dict[str, Any] = {}
        if isinstance(provenance_entities, dict):
            provenance_type = str(provenance_entities.get("document_type") or "")
            specific = provenance_entities.get("domain_specific")
            if isinstance(specific, dict):
                provenance_specific = dict(specific)
        document_type = provenance_type or str(best.type if best is not None else "unknown")
        if document_type == "commercial_invoice" and _looks_like_vat_invoice_text(self.full_text):
            document_type = "vat_invoice"
        return DocumentEntities(
            document_type=document_type or "unknown",
            domain_specific={
                **provenance_specific,
                "document_type_candidates": [candidate.model_dump() for candidate in candidates],
                "mirror_source": "mirror_json_vnext",
            },
        )

    @property
    def logical_tables(self) -> list[Any]:
        """ParseResult-compatible logical table projection."""
        return []


def _looks_like_vat_invoice_text(text: str) -> bool:
    normalized = str(text or "").lower()
    return (
        "增值税" in normalized
        or "value-added tax invoice" in normalized
        or ("invoice code" in normalized and "invoice number" in normalized and "tax id" in normalized)
    )


def mirror_json_vnext_schema() -> dict[str, Any]:
    """Return the JSON Schema for canonical Mirror JSON vNext."""

    return MirrorJsonVNext.model_json_schema(by_alias=True)


__all__ = [
    "AssetStore",
    "AtomKind",
    "BlockInfo",
    "BlockType",
    "DiagnosticsInfo",
    "DocumentInfo",
    "DocumentTypeCandidate",
    "EntityInfo",
    "EvidenceAtom",
    "EvidenceStore",
    "FactInfo",
    "GraphEdge",
    "GraphEdgeType",
    "GraphInfo",
    "GraphNode",
    "GraphNodeKind",
    "MirrorInfo",
    "MirrorJsonVNext",
    "PageInfo",
    "QualityInfo",
    "QualityStatus",
    "ReadingFlowKind",
    "RegionInfo",
    "RegionKind",
    "SemanticsInfo",
    "SourceInfo",
    "TypedValue",
    "mirror_json_vnext_schema",
]
