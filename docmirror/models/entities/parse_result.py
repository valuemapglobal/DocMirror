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
    - **Backward compatible**: ``from_legacy_parser_output()`` bridges old formats.

Usage::

    from docmirror.models.entities.parse_result import ParseResult, PageContent

    result = ParseResult(
        pages=[PageContent(...)],
        entities=DocumentEntities(document_type="bank_statement"),
        parser_info=ParserInfo(parser_name="docmirror"),
    )
"""

from __future__ import annotations

import os
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from docmirror.models.tracking.mutation import Mutation
from docmirror.structure.ocr.page_canvas.models import PageCanvas

if TYPE_CHECKING:
    from docmirror.models.entities.evidence import EvidenceSummary
    from docmirror.models.entities.hypothesis import ParseHypothesis
    from docmirror.models.entities.quality_report import ParseQualityReport

# Keys from domain_specific / mirror_metadata allowed in REST properties (ADR-M08)
MIRROR_METADATA_KEYS = frozenset(
    {
        "currency",
        "institution",
        "account_number",
        "opening_balance",
        "closing_balance",
        "transaction_count",
        "layout_profile_id",
        "layout_profile_id_refined",
        "mirror_expected_data_rows",
        "mirror_ltqg_enabled",
        "language",
        "region",
        "query_period",
    }
)


def _is_debug_mode() -> bool:
    """Return whether debug-only Mirror fields should be emitted."""
    return os.environ.get("DOCMIRROR_DEBUG", "").strip().lower() in {"1", "true", "yes"}


def _build_scanned_ocr_page_pool(*evidence_groups: Any) -> tuple[list[dict[str, Any]], dict[tuple[Any, Any], str]]:
    """Build shared OCR page evidence from scanned forensic evidence groups."""
    pages: list[dict[str, Any]] = []
    refs: dict[tuple[Any, Any], str] = {}
    seen: set[tuple[Any, Any]] = set()
    for group in evidence_groups:
        if not isinstance(group, list):
            continue
        for evidence in group:
            if not isinstance(evidence, dict):
                continue
            if "lines" not in evidence and "tokens" not in evidence:
                continue
            page = evidence.get("page")
            source = evidence.get("source") or "scanned_page_ocr"
            key = (page, source)
            if key in seen:
                continue
            seen.add(key)
            ref = f"ocr_p{page}_{len(pages)}"
            refs[key] = ref
            pages.append(
                {
                    "ocr_page_id": ref,
                    "page": page,
                    **({"page_width": evidence.get("page_width")} if evidence.get("page_width") is not None else {}),
                    **({"page_height": evidence.get("page_height")} if evidence.get("page_height") is not None else {}),
                    "source": source,
                    "lines": evidence.get("lines") or [],
                    "tokens": evidence.get("tokens") or [],
                }
            )
    return pages, refs


def _strip_scanned_ocr_payload_from_evidence(
    evidence_group: Any, refs: dict[tuple[Any, Any], str]
) -> list[dict[str, Any]]:
    """Replace duplicated scanned OCR payloads with shared OCR page refs."""
    if not isinstance(evidence_group, list):
        return []
    out: list[dict[str, Any]] = []
    for evidence in evidence_group:
        if not isinstance(evidence, dict):
            continue
        item = {k: v for k, v in evidence.items() if k not in {"lines", "tokens"}}
        source = item.get("source") or "scanned_page_ocr"
        ref = refs.get((item.get("page"), source))
        if ref:
            item["ocr_page_ref"] = ref
        out.append(item)
    return out


def _pages_with_region_kinds(api_pages: list[dict[str, Any]], kinds: set[str]) -> set[int]:
    pages: set[int] = set()
    for page in api_pages:
        if not isinstance(page, dict):
            continue
        page_num = int(page.get("page_number") or 0)
        for region in page.get("regions") or []:
            if isinstance(region, dict) and region.get("kind") in kinds:
                pages.add(page_num)
                break
    return pages


def _strip_structure_payload_from_local_structure_evidence(
    evidence_group: Any,
    api_pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop duplicated structures from forensic evidence when PCM regions already carry them."""
    if not isinstance(evidence_group, list):
        return []
    pages_with_structures = _pages_with_region_kinds(
        api_pages,
        {"field_grid", "label_value_graph"},
    )
    out: list[dict[str, Any]] = []
    for evidence in evidence_group:
        if not isinstance(evidence, dict):
            continue
        page_num = int(evidence.get("page") or 0)
        if page_num in pages_with_structures and evidence.get("structures"):
            item = {k: v for k, v in evidence.items() if k != "structures"}
            item["structures_in_regions"] = True
            out.append(item)
        else:
            out.append(dict(evidence))
    return out


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
    page_canvas: PageCanvas | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="In-memory PCM canvas (regions + flow); populated by sync_page_canvases()",
    )
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
        description="Mirror-only metadata (use mirror_metadata alias); not plugin records",
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
                "bank_statement": {
                    "document_type": "bank_statement",
                    "organization": "中国建设银行",
                    "subject_name": "张三",
                    "subject_id": "6217XXXXXXXXXXXX",
                    "period_start": "2024-06-20",
                    "period_end": "2025-06-20",
                    "domain_specific": {
                        "account_number": "6217001820010XXXXXX",
                        "opening_balance": 12345.67,
                        "closing_balance": 135530.00,
                        "transaction_count": 347,
                        "currency": "CNY",
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


# ══════════════════════════════════════════════════════════════════════════════
# Top-Level: ParseResult
# ══════════════════════════════════════════════════════════════════════════════


class ParseResult(BaseModel):
    """
    Universal document parsing output contract.

    **The single standard output model for all DocMirror parsers.**

    Five zones + envelope:
        - Envelope: ``status``, ``confidence``, ``error``
        - Zone 1 (pages): Content — "What I saw"
        - Zone 2 (entities): Entities — "What I recognized"
        - Zone 3 (parser_info): Meta — "How I did it"
        - Zone 4 (trust): Trust — "How much to trust it"
        - Zone 5 (provenance): Provenance — "Where it came from"

    Usage::

        result = ParseResult(
            pages=[PageContent(page_number=1, tables=[...])],
            entities=DocumentEntities(document_type="bank_statement", ...),
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

    # ── Zone 2: Entities ──
    entities: DocumentEntities = Field(default_factory=DocumentEntities)

    # ── Zone 3: Meta ──
    parser_info: ParserInfo = Field(default_factory=ParserInfo)

    # ── Zone 4: Trust ──
    trust: TrustResult | None = None

    # ── Zone 5: Provenance ──
    provenance: ProvenanceInfo | None = None

    # ── Pipeline state (populated by middleware) ──
    mutations: list[Mutation] = Field(default_factory=list, exclude=True)
    processing_time: float = Field(default=0.0, exclude=True)
    errors: list[str] = Field(default_factory=list, exclude=True)
    raw_text: str = Field(default="", exclude=True)

    # ── EHL annex (debug/eval only) ──
    annex: MirrorAnnex | None = Field(default=None, exclude=True)

    # ── Section tree (populated by UDTR section analysis) ──
    sections: list[DocumentSection] = Field(default_factory=list, exclude=True)

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

    def to_mirror_json_vnext(
        self,
        *,
        source_filename: str = "",
        mirror_level: str | None = None,
        include_text: bool | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Produce vNext MirrorJson via MirrorCoreVNext.

        This is the canonical output path for DocMirror 3.x.  The result
        is a document digital twin containing evidence, topology, blocks,
        graph, quality gates, and semantic facts.

        Args:
            source_filename: Optional source identifier for provenance.
            mirror_level: Deprecated compatibility alias for the vNext
                profile. It does not re-enable legacy output fields.
            include_text: Deprecated compatibility flag. vNext always emits
                content through blocks/evidence instead of a legacy top-level
                text field.

        Returns:
            vNext MirrorJson dict (top-level keys: mirror, source,
            document, pages, evidence, regions, blocks, graph, quality,
            semantics).
        """
        from docmirror.output.mirror import MirrorCoreVNext, MirrorOptions, MirrorResult

        _ = include_text
        options = MirrorOptions(
            source_filename=source_filename or "",
            profile=_vnext_profile_from_mirror_level(mirror_level),
        )
        core = MirrorCoreVNext()
        result = core.process(self, options=options)
        if isinstance(result, MirrorResult):
            return result.to_dict()
        if isinstance(result, dict):
            return result
        return {"error": f"unexpected result type: {type(result).__name__}"}

    # ── Legacy bridge ──

    @classmethod
    def from_legacy_parser_output(cls, output: Any) -> ParseResult:
        """
        Bridge from legacy ``ParserOutput`` — for gradual migration.

        Converts the old ``document_structure`` list and ``key_entities``
        dict into the typed ParseResult structure.
        """
        pages: list[PageContent] = []
        current_page = PageContent(page_number=1)

        for item in getattr(output, "document_structure", None) or []:
            if not isinstance(item, dict):
                continue

            page_num = item.get("page", 1)
            if page_num != current_page.page_number:
                pages.append(current_page)
                current_page = PageContent(page_number=page_num)

            block_type = item.get("type", "")

            if block_type == "table":
                headers = item.get("headers", [])
                raw_rows = item.get("rows", [])
                if not headers and "data" in item:
                    data = item["data"]
                    if data:
                        headers = data[0]
                        raw_rows = data[1:]

                table = TableBlock(
                    table_id=f"page{page_num}_table{len(current_page.tables)}",
                    headers=headers,
                    page=page_num,
                )
                for r in raw_rows:
                    cells = [CellValue(text=str(v)) for v in (r if isinstance(r, list) else [])]
                    table.rows.append(TableRow(cells=cells))
                current_page.tables.append(table)

            elif block_type in ("text", "title", "heading"):
                level = {
                    "title": TextLevel.TITLE,
                    "heading": TextLevel.H1,
                }.get(block_type, TextLevel.BODY)
                current_page.texts.append(TextBlock(content=item.get("content", ""), level=level))

            elif block_type == "key_value":
                for k, v in (item.get("pairs") or {}).items():
                    current_page.key_values.append(KeyValuePair(key=k, value=str(v)))

        pages.append(current_page)

        # Entities from key_entities
        ent = DocumentEntities()
        ke = getattr(output, "key_entities", None) or {}
        ent.subject_name = ke.get("户名") or ke.get("account_holder", "")
        ent.organization = ke.get("银行") or ke.get("bank_name", "")
        ent.domain_specific = ke

        return cls(
            pages=pages,
            entities=ent,
            parser_info=ParserInfo(
                overall_confidence=getattr(output, "confidence", 1.0),
                page_count=len(pages),
            ),
        )

    # ── Internal helpers ──

    def _build_full_text(self) -> str:
        """Reconstruct full document text from page content."""
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
                parts.append(self._table_to_markdown(table))
        return "\n\n".join(parts)

    @staticmethod
    def _table_to_markdown(table: TableBlock) -> str:
        """Render a table as Markdown."""
        if not table.headers:
            return ""
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

    def sync_page_canvases(
        self,
        *,
        scanned_ocr_pages: list[dict[str, Any]] | None = None,
    ) -> None:
        """Materialize PageCanvas on each page from domain_specific evidence."""
        from docmirror.structure.ocr.page_canvas.sync import sync_parse_result_page_canvases

        sync_parse_result_page_canvases(self, scanned_ocr_pages=scanned_ocr_pages)

    def _build_api_pages(self, *, forensic: bool = False) -> list[dict[str, Any]]:
        """Build API pages structure with full CellValue serialization."""
        api_pages: list[dict[str, Any]] = []
        for page in self.pages:
            api_page: dict[str, Any] = {
                "page_number": page.page_number,
            }
            if page.width is not None:
                api_page["width"] = page.width
            if page.height is not None:
                api_page["height"] = page.height

            # Tables with typed CellValue objects
            if page.tables:
                api_page["tables"] = []
                for table in page.tables:
                    table_out: dict[str, Any] = {
                        "table_id": table.table_id,
                        "headers": table.headers,
                        "rows": [
                            {
                                "cells": [self._serialize_cell(c, forensic=forensic) for c in row.cells],
                                "row_type": row.row_type.value,
                                "confidence": row.confidence,
                                "source_page": row.source_page,
                                "source_physical_id": row.source_physical_id,
                                "source_row_index": row.source_row_index,
                                **(
                                    {"source_cell_refs": row.source_cell_refs}
                                    if forensic and row.source_cell_refs
                                    else {}
                                ),
                            }
                            for row in table.rows
                        ],
                        "page": table.page,
                        "page_span": table.page_span,
                        "row_count": table.row_count,
                        "confidence": table.confidence,
                    }
                    if table.bbox:
                        table_out["bbox"] = table.bbox
                    if table.extraction_layer:
                        table_out["extraction_layer"] = table.extraction_layer
                    if table.extraction_confidence is not None:
                        table_out["extraction_confidence"] = table.extraction_confidence
                    raw_rows = (table.metadata or {}).get("raw_rows")
                    if raw_rows:
                        table_out["raw_rows"] = raw_rows
                    if forensic:
                        if table.evidence_ids:
                            table_out["evidence_ids"] = table.evidence_ids
                        if table.metadata:
                            table_out["metadata"] = table.metadata
                    api_page["tables"].append(table_out)

            # Text blocks with level
            if page.texts:
                texts_out = []
                for text in page.texts:
                    d = {
                        "content": text.content,
                        "level": text.level.value,
                        "confidence": text.confidence,
                    }
                    if forensic and text.bbox:
                        d["bbox"] = text.bbox
                    if forensic and text.evidence_ids:
                        d["evidence_ids"] = text.evidence_ids
                    if getattr(text, "slm_entities", None):
                        d["slm_entities"] = text.slm_entities
                    texts_out.append(d)
                api_page["texts"] = texts_out

            # Key-value pairs
            if page.key_values:
                api_page["key_values"] = [
                    {
                        "key": kv.key,
                        "value": kv.value,
                        "confidence": kv.confidence,
                        **({"bbox": kv.bbox} if forensic and kv.bbox else {}),
                        **({"evidence_ids": kv.evidence_ids} if forensic and kv.evidence_ids else {}),
                    }
                    for kv in page.key_values
                ]

            api_pages.append(api_page)
        return api_pages

    @staticmethod
    def _serialize_cell(cell: CellValue, *, forensic: bool = False) -> dict[str, Any]:
        """Serialize CellValue to API dict — minimal output."""
        d: dict[str, Any] = {"text": cell.text}
        dt = cell.data_type.value if hasattr(cell.data_type, "value") else cell.data_type
        d["data_type"] = dt or "text"
        if not forensic and cell.geometry_status:
            d["geometry_status"] = cell.geometry_status
        if not forensic and cell.source_cell_refs:
            d["source_cell_refs"] = cell.source_cell_refs
        if forensic:
            if cell.cleaned is not None:
                d["cleaned"] = cell.cleaned
            if cell.numeric is not None:
                d["numeric"] = cell.numeric
            if cell.confidence != 1.0:
                d["confidence"] = cell.confidence
            if cell.bbox:
                d["bbox"] = cell.bbox
            if cell.bbox_norm:
                d["bbox_norm"] = cell.bbox_norm
            if cell.row_index is not None:
                d["row_index"] = cell.row_index
            if cell.col_index is not None:
                d["col_index"] = cell.col_index
            if cell.row_span != 1:
                d["row_span"] = cell.row_span
            if cell.col_span != 1:
                d["col_span"] = cell.col_span
            if cell.geometry_status != "missing":
                d["geometry_status"] = cell.geometry_status
            if cell.geometry_source:
                d["geometry_source"] = cell.geometry_source
            if cell.geometry_confidence is not None:
                d["geometry_confidence"] = cell.geometry_confidence
            if cell.geometry_loss_reason:
                d["geometry_loss_reason"] = cell.geometry_loss_reason
            if cell.evidence_ids:
                d["evidence_ids"] = cell.evidence_ids
            if cell.token_ids:
                d["token_ids"] = cell.token_ids
            if cell.source_cell_refs:
                d["source_cell_refs"] = cell.source_cell_refs
        if getattr(cell, "slm_entities", None):
            d["slm_entities"] = cell.slm_entities
        return d


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


def _vnext_profile_from_mirror_level(mirror_level: str | None) -> str:
    level = str(mirror_level or "").strip().lower()
    if level in {"forensic", "ga_full", "full"}:
        return "forensic"
    if level in {"compact", "canonical_compact"}:
        return "canonical_compact"
    return "canonical_full"


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
