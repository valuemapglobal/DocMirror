# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
ParseResult — unified document parsing output contract (Mirror Object Contract).
=================================================================================

The **single standard output model** for all document parsers in DocMirror.
All parsers (PDF, image, Excel, Word, etc.) produce this structure.

Architecture zones::

    Zone 1 (pages)       Content: "What I saw" — pages, blocks, tables, cells
    Zone 2 (entities)    Entities: "What I recognized" — document_type, KV fields
    Zone 3 (parser_info) Meta: "How I did it" — parser name, timing, middleware trace
    Zone 4 (trust)       Trust: "How much to trust it" — forgery detection, scores
    Zone 5 (provenance)  Provenance: "Where it came from" — file path, hash, MIME
    annex (optional)     EHL debug/eval data — hypotheses, evidence, quality reports

Design principles::

    - **Strong typing**: Every field has a Pydantic type (no bare ``Dict[str, Any]``).
    - **Confidence penetration**: Cell → Row → Table → Page → Document.
    - **Separation of concerns**: Content / Entities / Meta are independent zones.
    - **Parser-agnostic**: DocMirror, Docling, PaddleOCR all output this structure.
    - **Canonical-built**: adapters emit evidence/basic facts; the canonical
      assembler constructs typed ``ParseResult`` objects.

Usage::

    from docmirror.models.entities.parse_result import ParseResult, PageContent

    result = ParseResult(
        pages=[PageContent(...)],
        entities=DocumentEntities(document_type="example_document"),
        parser_info=ParserInfo(parser_name="docmirror"),
    )
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from docmirror.models.mirror.document_flow import DocumentFlowGraph
from docmirror.models.mirror.vnext import EvidenceAtom, EvidenceStore, SourceInfo
from docmirror.models.tracking.mutation import Mutation

if TYPE_CHECKING:
    from docmirror.models.entities.evidence import EvidenceSummary
    from docmirror.models.entities.hypothesis import ParseHypothesis
    from docmirror.models.entities.quality_report import ParseQualityReport

# ══════════════════════════════════════════════════════════════════════════════
# Enumerations
# ══════════════════════════════════════════════════════════════════════════════


class DataType(str, Enum):
    """Cell data type classification."""

    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    CURRENCY = "currency"
    EMPTY = "empty"
    MIXED = "mixed"


class RowType(str, Enum):
    """Table row semantic role."""

    HEADER = "header"
    DATA = "data"
    SUMMARY = "summary"
    SEPARATOR = "separator"
    SUBHEADER = "subheader"


class TextLevel(str, Enum):
    """Text hierarchy level."""

    TITLE = "title"
    H1 = "h1"
    H2 = "h2"
    H3 = "h3"
    BODY = "body"
    FOOTER = "footer"
    WATERMARK = "watermark"


class ExtractionMethod(str, Enum):
    """Document extraction method."""

    DIGITAL = "digital"
    OCR = "ocr"
    HYBRID = "hybrid"
    IMAGE = "image"


class ResultStatus(str, Enum):
    """Parse result status."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


# ══════════════════════════════════════════════════════════════════════════════
# Zone 1: Content — "What I saw"
# ══════════════════════════════════════════════════════════════════════════════


class CellValue(BaseModel):
    """
    Atomic unit of extraction — a single table cell.

    - ``text``: Raw OCR/extraction text, kept as-is.
    - ``cleaned``: Pre-cleaned text (stripped thousand separators, currency symbols).
    - ``numeric``: Parsed numeric value (if applicable).
    - ``confidence``: Extraction/OCR confidence [0.0, 1.0].
    """

    text: str = ""
    cleaned: str | None = None
    numeric: float | None = None
    confidence: float = 1.0
    bbox: list[float] | None = None
    bbox_norm: list[float] | None = None
    row_index: int | None = None
    col_index: int | None = None
    row_span: int = 1
    col_span: int = 1
    geometry_status: Literal["exact", "estimated", "missing", "logical_only", "derived"] = "missing"
    geometry_source: str = ""
    geometry_confidence: float | None = None
    geometry_loss_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    token_ids: list[str] = Field(default_factory=list)
    source_cell_refs: list[dict[str, Any]] = Field(default_factory=list)
    data_type: DataType = DataType.TEXT
    slm_entities: dict[str, Any] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": "15,000.00",
                    "cleaned": "15000.00",
                    "numeric": 15000.0,
                    "confidence": 0.97,
                    "data_type": "currency",
                },
            ]
        }
    )


class TableRow(BaseModel):
    """
    A single table row with typed cells and semantic role.

    ``row_type`` distinguishes:
        - ``header``: Column name definition row.
        - ``data``: Core content row.
        - ``summary``: Aggregation row (e.g. "Total", "本页合计").
        - ``separator``: Divider/empty row.
        - ``subheader``: Sub-group title (e.g. "2024年7月").
    """

    cells: list[CellValue] = Field(default_factory=list)
    row_type: RowType = RowType.DATA
    confidence: float = 1.0
    source_page: int = 0
    source_physical_id: str = ""
    source_row_index: int = -1
    source_cell_refs: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def cell_texts(self) -> list[str]:
        """Convenience: list of all cell text values."""
        return [c.text for c in self.cells]


class TableBlock(BaseModel):
    """
    A complete table with headers, typed rows, and metadata.

    ``headers`` may be empty if the parser cannot determine the header row.
    ``rows`` contain all rows (data + summary + separators).
    """

    table_id: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[TableRow] = Field(default_factory=list)
    page: int = 1
    page_span: int = 1
    bbox: list[float] | None = None
    confidence: float = 1.0
    caption: str | None = None
    reading_order: int = 0
    extraction_layer: str = ""
    extraction_confidence: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def data_rows(self) -> list[TableRow]:
        """Only data rows (excluding headers, summaries, separators)."""
        return [r for r in self.rows if r.row_type == RowType.DATA]

    @property
    def summary_rows(self) -> list[TableRow]:
        """Only summary/aggregation rows."""
        return [r for r in self.rows if r.row_type == RowType.SUMMARY]

    @property
    def row_count(self) -> int:
        """Number of data rows."""
        return len(self.data_rows)

    def to_dicts(self) -> list[dict[str, str]]:
        """
        Flatten data rows to ``[{column_name: cell_value}]``.

        Uses ``cleaned`` text if available, otherwise raw ``text``.
        """
        if not self.headers:
            return []
        return [
            {self.headers[i]: (c.cleaned or c.text) for i, c in enumerate(row.cells) if i < len(self.headers)}
            for row in self.data_rows
        ]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "table_id": "page1_table0",
                "headers": ["交易日期", "摘要", "交易金额", "余额"],
                "rows": [
                    {
                        "cells": [
                            {"text": "2024-06-20", "data_type": "date", "confidence": 0.99},
                            {"text": "工资", "data_type": "text", "confidence": 0.95},
                            {"text": "15,000.00", "numeric": 15000.0, "data_type": "currency"},
                            {"text": "135,530.00", "numeric": 135530.0, "data_type": "currency"},
                        ],
                        "row_type": "data",
                        "confidence": 0.95,
                    }
                ],
                "confidence": 0.96,
            }
        }
    )


class RowProvenance(BaseModel):
    """Provenance metadata for a logical table row — tracks physical origin."""

    source_page: int = 1
    source_table_id: str = ""
    source_row_index: int = 0
    is_continuation: bool = False


class LogicalTable(BaseModel):
    """A cross-page logical table — result of TableComposer composition.

    Unlike ``TableBlock`` (which is per-page physical), ``LogicalTable``
    represents the **inferred** complete table after cross-page merge.

    Design:
      - ``logical_id`` / ``table_id`` identify the composed table (e.g. ``lt_0``).
      - ``source_physical_ids`` reference per-page physical tables (``pt_N_0``).
      - ``headers`` are the deduplicated, merged header row.
      - ``rows`` carry per-row provenance (source_page, source_physical_id).
      - ``merge_confidence`` reflects cross-page merge quality.
      - ``merge_log`` / ``merge_audit`` record composition decisions.
    """

    table_id: str = ""
    logical_id: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[TableRow] = Field(default_factory=list)
    confidence: float = 1.0
    source_physical_ids: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    page_span: tuple[int, int] = (1, 1)
    row_count: int = 0
    merge_method: str = "none"
    merge_confidence: float = 1.0
    provenance: list[RowProvenance] = Field(default_factory=list)
    merge_log: list[dict] = Field(default_factory=list)
    merge_audit: list[dict] = Field(default_factory=list)
    # LTQG (Mirror compose) — defaults preserve pre-LTQG behavior
    quality_score: float = 1.0
    quality_passed: bool = True
    quality_skip_reason: str | None = None
    data_row_estimate: int = 0
    quality_signals: dict[str, Any] = Field(default_factory=dict)


class TextBlock(BaseModel):
    """A text paragraph or heading with hierarchy level."""

    content: str = ""
    level: TextLevel = TextLevel.BODY
    confidence: float = 1.0
    bbox: list[float] | None = None
    reading_order: int = 0
    role: str = "body"
    slm_entities: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class KeyValuePair(BaseModel):
    """
    A key-value pair extracted from the document.

    Examples: "开户行: 建设银行", "纳税人识别号: 91110..."
    """

    key: str = ""
    value: str = ""
    confidence: float = 1.0
    bbox: list[float] | None = None
    reading_order: int = 0
    evidence_ids: list[str] = Field(default_factory=list)


class PageContent(BaseModel):
    """
    Content of a single page — maintains page-level organization.

    Each page contains typed collections of tables, text blocks, and KV pairs.
    """

    page_number: int = 1
    tables: list[TableBlock] = Field(default_factory=list)
    texts: list[TextBlock] = Field(default_factory=list)
    key_values: list[KeyValuePair] = Field(default_factory=list)
    page_confidence: float = 1.0
    page_mode: str | None = Field(default=None, description="Page content mode (native_text, scanned, mixed)")
    pcs: str | None = Field(default=None, description="Page complexity score")
    routing_confidence: float | None = Field(default=None, description="Routing confidence score")
    width: int | None = None
    height: int | None = None
    source_page_number: int | None = None
    coordinate_transform: dict[str, Any] = Field(default_factory=dict)
    source_member: str = Field(
        default="",
        description="Relative path inside a parent archive/container, if applicable.",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Zone 2: Entities — "What I recognized"
# ══════════════════════════════════════════════════════════════════════════════


class DocumentEntities(BaseModel):
    """
    Structured entities recognized from the document.

    Two layers:
        1. Universal fields — applicable to all document types.
        2. ``domain_specific`` — populated per document_type for domain-specific data.
    """

    document_type: str = "unknown"
    organization: str | None = None
    subject_name: str | None = None
    subject_id: str | None = None
    document_date: str | None = None
    period_start: str | None = None
    period_end: str | None = None

    domain_specific: dict[str, Any] = Field(
        default_factory=dict,
        description="Parser-owned structured extensions and domain-specific record collections.",
    )

    @property
    def mirror_metadata(self) -> dict[str, Any]:
        """Alias for domain_specific — Mirror debug/metadata keys only (ADR-M08)."""
        return self.domain_specific

    @mirror_metadata.setter
    def mirror_metadata(self, value: dict[str, Any]) -> None:
        self.domain_specific = value

    model_config = ConfigDict(
        json_schema_extra={
            "examples": {
                "generic_document": {
                    "document_type": "example_document",
                    "organization": "Example Organization",
                    "subject_name": "Example Subject",
                    "subject_id": "SUBJECT-001",
                    "document_date": "2026-01-01",
                    "domain_specific": {
                        "source_category": "example",
                    },
                },
            }
        }
    )


# ══════════════════════════════════════════════════════════════════════════════
# Zone 3: Meta — "How I did it"
# ══════════════════════════════════════════════════════════════════════════════


class ParserInfo(BaseModel):
    """
    Parser self-description metadata.

    Middleware uses this to decide enhancement strategies:
        - ``extraction_method="ocr"`` → enable OCR repair middleware
        - ``overall_confidence < 0.7`` → trigger re-parse or degradation
        - ``table_engine="camelot"`` → skip table re-detection
    """

    parser_name: str = ""
    parser_version: str = ""
    elapsed_ms: float = 0
    page_count: int = 0

    extraction_method: ExtractionMethod = ExtractionMethod.DIGITAL
    ocr_engine: str | None = None
    table_engine: str | None = None

    overall_confidence: float = 1.0
    warnings: list[str] = Field(default_factory=list)

    # ADR-M13-02: Structure Provenance Envelope (SSO / SDU audit)
    structure: dict[str, Any] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# Zone 4: Trust — "How much to trust it"
# (Absorbed from PerceptionResult.provenance.validation)
# ══════════════════════════════════════════════════════════════════════════════


class TrustResult(BaseModel):
    """
    Trust and validation assessment of the parsed content.

    Populated by the Validator middleware after the enhancement pipeline.
    """

    validation_score: float = 0.0
    validation_passed: bool = False
    trust_score: float = 0.0
    is_forged: bool | None = None
    forgery_reasons: list[str] = Field(default_factory=list)

    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-check validation breakdown (e.g. balance_continuity, date_order)",
    )


class TableOperation(BaseModel):
    """Cross-page table merge/split audit entry (Zone 1 debug)."""

    model_config = ConfigDict(extra="allow")

    logical_id: str = ""
    merge_method: str = ""
    merge_confidence: float = 0.0
    source_physical_ids: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    row_count: int = 0
    merge_log: list[dict[str, Any]] = Field(default_factory=list)
    merge_audit: list[dict[str, Any]] = Field(default_factory=list)
    quality_score: float = 1.0
    quality_passed: bool = True
    quality_skip_reason: str | None = None
    data_row_estimate: int = 0


class DocumentSection(BaseModel):
    """Section tree node (section_dominant documents; debug/eval)."""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    title: str = ""
    name: str = ""
    page_start: int = 1
    page_end: int | None = None


# ══════════════════════════════════════════════════════════════════════════════
# Zone 5: Provenance — "Where it came from"
# (Absorbed from PerceptionResult.provenance.source)
# ══════════════════════════════════════════════════════════════════════════════


class ProvenanceInfo(BaseModel):
    """Source file provenance for audit trail."""

    file_path: str = ""
    file_id: str = ""
    file_hash: str = ""
    file_type: str = ""
    file_size: int = 0
    checksum: str = ""
    mime_type: str = ""
    capability_id: str = ""
    content_model: str = ""
    source_member: str = Field(
        default="",
        description="Relative path when this file was extracted from an archive.",
    )
    document_properties: dict[str, Any] = Field(
        default_factory=dict,
        description="PDF metadata, EXIF data, etc.",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Envelope — Error handling
# ══════════════════════════════════════════════════════════════════════════════


class ErrorDetail(BaseModel):
    """Structured error information for failed parses."""

    code: str = ""
    message: str = ""
    details: str | None = None


# ══════════════════════════════════════════════════════════════════════════════
# EHL Annex (debug / eval only — exclude from mirror.json)
# ══════════════════════════════════════════════════════════════════════════════


class MirrorAnnex(BaseModel):
    """Optional Evidence & Hypothesis Layer — serialized through vNext mirror output."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    evidence_summary: EvidenceSummary | None = None
    hypotheses: list[ParseHypothesis] = Field(default_factory=list)
    quality_report: ParseQualityReport | None = None
    pipeline_debug: dict[str, Any] = Field(
        default_factory=dict,
        description="Middleware/orchestrator debug payloads (mutation_analysis, etc.)",
    )
    quarantine: dict[str, Any] = Field(
        default_factory=dict,
        description="Unified quarantine summary/details for forensic/debug export.",
    )


class EvidencePageSnapshot(BaseModel):
    """Serializable page index for the canonical source evidence plane."""

    page_id: str
    page_index: int
    page_number: int
    width: float | None = None
    height: float | None = None
    original_rotation: int = 0
    normalized_rotation: int = 0
    coordinate_transform: dict[str, Any] = Field(default_factory=dict)
    normalization_trace: dict[str, Any] = Field(default_factory=dict)
    content_mode: str = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)


class CanonicalEvidencePlane(BaseModel):
    """Cache-safe lossless evidence owned by ``ParseResult``.

    The runtime EvidencePlane is an extraction data structure.  This model is
    its canonical, serializable representation and therefore survives cache
    round-trips without requiring Mirror or source-file reconstruction.
    """

    source: SourceInfo = Field(default_factory=SourceInfo)
    pages: list[EvidencePageSnapshot] = Field(default_factory=list)
    evidence: EvidenceStore = Field(default_factory=EvidenceStore)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_runtime(cls, plane: Any | None) -> CanonicalEvidencePlane | None:
        if plane is None:
            return None
        if isinstance(plane, cls):
            return plane
        runtime_source = getattr(plane, "source", None)
        if not isinstance(runtime_source, SourceInfo):
            runtime_source = SourceInfo.model_validate(runtime_source if isinstance(runtime_source, dict) else {})
        runtime_evidence = getattr(plane, "evidence", None)
        if not isinstance(runtime_evidence, EvidenceStore):

            def _atoms(name: str) -> list[EvidenceAtom]:
                atoms: list[EvidenceAtom] = []
                for atom in list(getattr(runtime_evidence, name, []) or []):
                    if isinstance(atom, EvidenceAtom):
                        atoms.append(atom)
                        continue
                    payload = (
                        atom
                        if isinstance(atom, dict)
                        else {
                            key: getattr(atom, key)
                            for key in (
                                "id",
                                "kind",
                                "source_kind",
                                "page_id",
                                "text",
                                "bbox",
                                "source_bbox",
                                "coordinate_transform",
                                "confidence",
                                "style",
                                "source_refs",
                                "metadata",
                            )
                            if hasattr(atom, key)
                        }
                    )
                    atoms.append(EvidenceAtom.model_validate(payload))
                return atoms

            runtime_evidence = EvidenceStore(
                text_atoms=_atoms("text_atoms"),
                visual_atoms=_atoms("visual_atoms"),
                image_atoms=_atoms("image_atoms"),
                vector_atoms=_atoms("vector_atoms"),
                indexes=dict(getattr(runtime_evidence, "indexes", {}) or {}),
            )
        return cls(
            source=runtime_source,
            pages=[
                EvidencePageSnapshot.model_validate(
                    {
                        "page_id": str(getattr(page, "page_id", "")),
                        "page_index": int(getattr(page, "page_index", 0)),
                        "page_number": int(getattr(page, "page_number", 0)),
                        "width": getattr(page, "width", None),
                        "height": getattr(page, "height", None),
                        "original_rotation": int(getattr(page, "original_rotation", 0) or 0),
                        "normalized_rotation": int(getattr(page, "normalized_rotation", 0) or 0),
                        "coordinate_transform": dict(getattr(page, "coordinate_transform", {}) or {}),
                        "normalization_trace": dict(getattr(page, "normalization_trace", {}) or {}),
                        "content_mode": str(getattr(page, "content_mode", "unknown") or "unknown"),
                        "evidence_ids": list(getattr(page, "evidence_ids", []) or []),
                    }
                )
                for page in getattr(plane, "pages", [])
            ],
            evidence=runtime_evidence,
            diagnostics=list(getattr(plane, "diagnostics", []) or []),
        )

    def to_runtime(self) -> Any:
        from docmirror.evidence.plane import EvidencePage, EvidencePlane

        return EvidencePlane(
            source=self.source,
            pages=[EvidencePage(**page.model_dump(mode="python")) for page in self.pages],
            evidence=self.evidence,
            diagnostics=list(self.diagnostics),
        )


# ══════════════════════════════════════════════════════════════════════════════
# Top-Level: ParseResult
# ══════════════════════════════════════════════════════════════════════════════


class ParseResult(BaseModel):
    """
    Universal document parsing output contract.

    **The single standard output model for all DocMirror parsers.**

    Five source/trust zones and the envelope:
        - Envelope: ``status``, ``confidence``, ``error``
        - Zone 1 (pages): Content — "What I saw"
        - Zone 2 (entities): Entities — "What I recognized"
        - Zone 3 (parser_info): Meta — "How I did it"
        - Zone 4 (trust): Trust — "How much to trust it"
        - Zone 5 (provenance): Provenance — "Where it came from"

    Usage::

        result = ParseResult(
            pages=[PageContent(page_number=1, tables=[...])],
            entities=DocumentEntities(document_type="example_document", ...),
            parser_info=ParserInfo(parser_name="docmirror", ...),
        )

        # Convenience accessors
        result.total_tables   # → 3
        result.total_rows     # → 45
        result.flatten_rows() # → [{col: val}, ...]
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # ── Envelope ──
    status: ResultStatus = ResultStatus.SUCCESS
    confidence: float = 1.0
    error: ErrorDetail | None = None

    # ── Zone 1: Content ──
    pages: list[PageContent] = Field(default_factory=list)
    logical_tables: list[LogicalTable] = Field(
        default_factory=list,
        description="Cross-page logical tables (composed from physical pages). "
        "Plugin reads here; physical pages[].tables are raw per-page.",
    )
    table_operations: list[TableOperation] = Field(
        default_factory=list, description="Cross-page merge/split audit trail (debug / enterprise QA)."
    )
    document_flow: DocumentFlowGraph | None = Field(
        default=None,
        description="Canonical source-complete reading flow consumed by all output projectors.",
    )
    evidence_plane: CanonicalEvidencePlane | None = Field(
        default=None,
        description="Lossless canonical source evidence; included in cache serialization.",
    )

    # ── Zone 2: Entities ──
    entities: DocumentEntities = Field(default_factory=DocumentEntities)

    # ── Zone 3: Meta ──
    parser_info: ParserInfo = Field(default_factory=ParserInfo)

    # ── Zone 4: Trust ──
    trust: TrustResult | None = None

    # ── Zone 5: Provenance ──
    provenance: ProvenanceInfo | None = None

    # ── Pipeline state (populated by middleware) ──
    mutations: list[Mutation] = Field(default_factory=list)
    processing_time: float = Field(default=0.0, exclude=True)
    errors: list[str] = Field(default_factory=list, exclude=True)
    raw_text: str = Field(default="")

    # ── EHL annex (debug/eval only) ──
    annex: MirrorAnnex | None = Field(default=None)

    # ── Section tree (populated by UDTR section analysis) ──
    sections: list[DocumentSection] = Field(default_factory=list)

    @field_validator("sections", mode="before")
    @classmethod
    def _coerce_sections(cls, value: Any) -> list[Any]:
        if not value:
            return []
        out: list[Any] = []
        for item in value:
            if isinstance(item, DocumentSection):
                out.append(item)
            elif isinstance(item, dict):
                out.append(DocumentSection.model_validate(item))
            else:
                out.append(item)
        return out

    @field_validator("table_operations", mode="before")
    @classmethod
    def _coerce_table_operations(cls, value: Any) -> list[Any]:
        if not value:
            return []
        out: list[Any] = []
        for item in value:
            if isinstance(item, TableOperation):
                out.append(item)
            elif isinstance(item, dict):
                out.append(TableOperation.model_validate(item))
            else:
                out.append(item)
        return out

    # ── Computed properties ──

    @property
    def success(self) -> bool:
        """Whether parsing succeeded (fully or partially)."""
        return self.status in (ResultStatus.SUCCESS, ResultStatus.PARTIAL)

    def fact_fingerprint(self) -> str:
        """Return the deterministic digest of facts, excluding runtime metadata."""
        from docmirror.models.fingerprint import canonical_fact_fingerprint

        return canonical_fact_fingerprint(self)

    @property
    def total_tables(self) -> int:
        """Total number of tables across all pages."""
        return sum(len(p.tables) for p in self.pages)

    @property
    def total_rows(self) -> int:
        """Total number of data rows across all tables."""
        return sum(t.row_count for p in self.pages for t in p.tables)

    @property
    def page_count(self) -> int:
        """Number of pages."""
        return len(self.pages)

    @property
    def full_text(self) -> str:
        """Reconstruct full text from all pages (texts + table markdown)."""
        return self._build_full_text()

    @property
    def file_path(self) -> str:
        """Source path recorded in provenance, if available."""
        return str(getattr(self.provenance, "file_path", "") or "")

    def get(self, key: str, default: Any = None) -> Any:
        """Temporary mapping compatibility for edition plugins.

        Edition plugins now receive ParseResult directly. Existing commercial
        plugins historically called ``document_context.get(...)``; this shim
        keeps those packages working while their signatures migrate without
        reintroducing a second context object or data source.
        """
        if key in {"parse_result", "result"}:
            return self
        if key in {"full_text", "text"}:
            return self.full_text or self.raw_text or default
        if key in {"file_path", "file"}:
            return self.file_path or default
        if key == "tables":
            return [table.model_dump(mode="json") for table in self.all_tables()]
        if key == "metadata":
            return self.entities.model_dump(mode="json", exclude_none=True)
        return getattr(self, key, default)

    def all_tables(self) -> list[TableBlock]:
        """Collect all tables across pages."""
        return [t for p in self.pages for t in p.tables]

    @property
    def kv_entities(self) -> dict[str, str]:
        """Key-value entities from all pages for semantic extraction."""
        return self.all_key_values()

    @property
    def mutation_count(self) -> int:
        return len(self.mutations)

    @property
    def mutation_summary(self) -> dict[str, int]:
        """Summarize mutations per middleware."""
        summary: dict[str, int] = {}
        for m in self.mutations:
            summary[m.middleware_name] = summary.get(m.middleware_name, 0) + 1
        return summary

    # ── Middleware helper methods ──

    def record_mutation(
        self,
        middleware_name: str,
        target_block_id: str,
        field_changed: str,
        old_value: Any,
        new_value: Any,
        confidence: float = 1.0,
        reason: str = "",
    ) -> None:
        """Create and attach a Mutation audit record."""
        self.mutations.append(
            Mutation.create(
                middleware_name=middleware_name,
                target_block_id=target_block_id,
                field_changed=field_changed,
                old_value=old_value,
                new_value=new_value,
                confidence=confidence,
                reason=reason,
            )
        )

    def add_mutation(self, mutation: Mutation) -> None:
        """Append a pre-built Mutation object."""
        self.mutations.append(mutation)

    def add_error(self, error: str) -> None:
        """Record an error and downgrade status."""
        self.errors.append(error)
        if self.status == ResultStatus.SUCCESS:
            self.status = ResultStatus.PARTIAL

    def flatten_rows(self) -> list[dict[str, str]]:
        """
        Flatten all data rows into ``[{column_name: cell_value}]``.

        This is the direct data source for downstream structured consumers.
        """
        rows: list[dict[str, str]] = []
        for table in self.all_tables():
            rows.extend(table.to_dicts())
        return rows

    def all_key_values(self) -> dict[str, str]:
        """Collect all key-value pairs across pages into a single dict."""
        result: dict[str, str] = {}
        for page in self.pages:
            for kv in page.key_values:
                if kv.key:
                    result[kv.key] = kv.value
        return result

    # ── Internal helpers ──

    def _build_full_text(self) -> str:
        """Reconstruct full document text from page content."""
        flow_text = self._build_full_text_from_document_flow()
        if flow_text:
            return flow_text
        parts: list[str] = []
        for page in self.pages:
            for text in page.texts:
                if text.content.strip():
                    if text.level in (TextLevel.TITLE, TextLevel.H1):
                        parts.append(f"# {text.content}")
                    elif text.level == TextLevel.H2:
                        parts.append(f"## {text.content}")
                    elif text.level == TextLevel.H3:
                        parts.append(f"### {text.content}")
                    else:
                        parts.append(text.content)
            for kv in page.key_values:
                parts.append(f"**{kv.key}**: {kv.value}")
            for table in page.tables:
                rendered = self._table_to_markdown(table)
                if rendered:
                    parts.append(rendered)
        return "\n\n".join(parts)

    def _build_full_text_from_document_flow(self) -> str:
        """Render canonical facts in the same source order used by outputs."""
        flow = self.document_flow
        reading_flows = list(getattr(flow, "reading_flow", None) or [])
        nodes = list(getattr(flow, "nodes", None) or [])
        if not reading_flows or not nodes:
            return ""
        node_by_id = {str(node.node_id): node for node in nodes}
        table_by_id = {
            str(table.table_id): table for page in self.pages for table in page.tables if str(table.table_id or "")
        }
        parts: list[str] = []
        for node_id in reading_flows[0].node_ids:
            node = node_by_id.get(str(node_id))
            if node is None:
                continue
            if node.type == "physical_table":
                table = table_by_id.get(str((node.metadata or {}).get("table_id") or ""))
                rendered = self._table_to_markdown(table) if table is not None else ""
                if rendered:
                    parts.append(rendered)
                continue
            if node.role == "key_value":
                key = str((node.metadata or {}).get("key") or "")
                value = str((node.metadata or {}).get("value") or "")
                if key or value:
                    parts.append(f"**{key}**: {value}")
                continue
            text = str(node.text or "")
            if not text:
                continue
            level = str((node.metadata or {}).get("level") or "")
            prefix = {"title": "# ", "h1": "# ", "h2": "## ", "h3": "### "}.get(level, "")
            parts.append(prefix + text)
        return "\n\n".join(parts)

    @staticmethod
    def _table_to_markdown(table: TableBlock) -> str:
        """Render a table as Markdown."""
        if not table.headers:
            physical_rows: list[str] = []
            for row in table.data_rows:
                cells = [
                    "" if cell.geometry_loss_reason == "covered_by_merged_cell" else cell.text for cell in row.cells
                ]
                while cells and not str(cells[-1]).strip():
                    cells.pop()
                if any(str(cell).strip() for cell in cells):
                    physical_rows.append("\t".join(str(cell) for cell in cells))
            return "\n".join(physical_rows)
        lines = []
        lines.append("| " + " | ".join(table.headers) + " |")
        lines.append("|" + "|".join("---" for _ in table.headers) + "|")
        for row in table.data_rows:
            cells = [c.text for c in row.cells]
            # Pad to header count
            while len(cells) < len(table.headers):
                cells.append("")
            lines.append("| " + " | ".join(cells[: len(table.headers)]) + " |")
        return "\n".join(lines)


def _rebuild_parse_result_models() -> None:
    """Resolve forward refs on MirrorAnnex after dependent models load."""
    from docmirror.models.entities.evidence import EvidenceSummary
    from docmirror.models.entities.hypothesis import ParseHypothesis
    from docmirror.models.entities.quality_report import ParseQualityReport

    MirrorAnnex.model_rebuild(
        _types_namespace={
            "EvidenceSummary": EvidenceSummary,
            "ParseHypothesis": ParseHypothesis,
            "ParseQualityReport": ParseQualityReport,
        }
    )
    ParseResult.model_rebuild()


_rebuild_parse_result_models()


__all__ = [
    # Enums
    "DataType",
    "RowType",
    "TextLevel",
    "ExtractionMethod",
    "ResultStatus",
    # Zone 1: Content
    "CellValue",
    "TableRow",
    "TableBlock",
    "TextBlock",
    "KeyValuePair",
    "PageContent",
    # Zone 2: Entities
    "DocumentEntities",
    # Zone 3: Meta
    "ParserInfo",
    # Zone 4: Trust
    "TrustResult",
    # Zone 5: Provenance
    "ProvenanceInfo",
    # Envelope
    "ErrorDetail",
    # Top-level
    "ParseResult",
]
