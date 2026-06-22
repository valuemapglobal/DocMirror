# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Source Span Ledger — field-to-source traceability contract.

GA 1.0 design §5.5 / §6.2: Every Edition field, record, and key field that
appears in output MUST be traceable back to a page, bbox, source_ref, token,
or cell.  Fields without any evidence enter ``unresolved_fields`` with
``reason`` and ``needs_evidence`` review status.

The SourceSpanLedger is one projection of the Visual Evidence Graph; it is
consumed by the quality decision report, the visualizer inspector, and the
diff engine.

Usage::

    from docmirror.evidence.source_span import (
        SourceSpanEntry,
        UnresolvedField,
        SourceSpanLedger,
    )
    ledger = SourceSpanLedger()
    ledger.add_span(SourceSpanEntry(
        field_path="finance.data.fields.total_amount",
        source_refs=["cell:p3:t0:r42:c3"],
        page=3,
        bbox=[100, 210, 180, 230],
        raw="1234.56",
        normalized="1234.56",
        confidence=0.97,
    ))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class SourceSpanEntry:
    """A traceable field with its source evidence.

    Every field that appears in any Edition output SHOULD have a
    corresponding SourceSpanEntry.  Fields that lack evidence are tracked
    as ``UnresolvedField`` entries instead.
    """

    field_path: str = ""
    source_refs: list[str] = field(default_factory=list)
    page: int = 0
    bbox: list[float] | None = None
    tokens: list[str] = field(default_factory=list)
    raw: str = ""
    normalized: str = ""
    confidence: float = 1.0
    review: Literal["auto_accepted", "needs_review", "needs_evidence"] = "auto_accepted"
    edition: str = ""
    kind: str = "field"
    transform_chain: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "source_refs": self.source_refs,
            "page": self.page,
            "bbox": self.bbox,
            "tokens": self.tokens,
            "raw": self.raw,
            "normalized": self.normalized,
            "confidence": self.confidence,
            "review": self.review,
            "edition": self.edition,
            "kind": self.kind,
            "transform_chain": self.transform_chain,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceSpanEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class UnresolvedField:
    """A field for which no source evidence could be resolved."""

    field_path: str = ""
    reason: str = "no_source_ref"
    review: Literal["needs_review", "needs_evidence"] = "needs_evidence"
    suggestion: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "reason": self.reason,
            "review": self.review,
            "suggestion": self.suggestion,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnresolvedField:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SourceSpanLedger:
    """The authoritative field-to-source traceability record.

    The ledger collects every ``SourceSpanEntry`` (fields with evidence) and
    ``UnresolvedField`` (fields without evidence) for a single parse task.
    It is the primary data source for span visualization, the quality
    decision report's evidence-coverage gate, and the diff engine's
    field-level comparison.
    """

    version: int = 1
    document_id: str = ""
    task_id: str = ""

    field_spans: list[SourceSpanEntry] = field(default_factory=list)
    unresolved_fields: list[UnresolvedField] = field(default_factory=list)

    def add_span(self, span: SourceSpanEntry) -> None:
        self.field_spans.append(span)

    def add_unresolved(self, uf: UnresolvedField) -> None:
        self.unresolved_fields.append(uf)

    @property
    def total_fields(self) -> int:
        return len(self.field_spans) + len(self.unresolved_fields)

    @property
    def has_evidence_count(self) -> int:
        return sum(1 for s in self.field_spans if s.source_refs or s.bbox or s.page)

    @property
    def needs_review_count(self) -> int:
        return sum(
            1 for s in self.field_spans
            if s.review in ("needs_review", "needs_evidence")
        ) + len(self.unresolved_fields)

    @property
    def coverage_ratio(self) -> float:
        total = self.total_fields
        if total == 0:
            return 0.0
        return round(self.has_evidence_count / total, 4)

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "total_fields": self.total_fields,
            "has_evidence": self.has_evidence_count,
            "needs_review": self.needs_review_count,
            "unresolved": len(self.unresolved_fields),
            "coverage_ratio": self.coverage_ratio,
        }

    def spans_by_edition(self, edition: str) -> list[SourceSpanEntry]:
        return [s for s in self.field_spans if s.edition == edition]

    def spans_by_page(self, page: int) -> list[SourceSpanEntry]:
        return [s for s in self.field_spans if s.page == page]

    def spans_needing_review(self) -> list[SourceSpanEntry]:
        return [s for s in self.field_spans if s.review in ("needs_review", "needs_evidence")]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "document_id": self.document_id,
            "task_id": self.task_id,
            "field_spans": [s.to_dict() for s in self.field_spans],
            "unresolved_fields": [u.to_dict() for u in self.unresolved_fields],
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceSpanLedger:
        ledger = cls(
            version=data.get("version", 1),
            document_id=data.get("document_id", ""),
            task_id=data.get("task_id", ""),
        )
        for span_data in data.get("field_spans", []):
            ledger.field_spans.append(SourceSpanEntry.from_dict(span_data))
        for uf_data in data.get("unresolved_fields", []):
            ledger.unresolved_fields.append(UnresolvedField.from_dict(uf_data))
        return ledger


def build_source_span_ledger(
    result: Any,
    editions: dict[str, Any] | None = None,
    *,
    document_id: str = "",
    task_id: str = "",
) -> SourceSpanLedger:
    """Build a SourceSpanLedger from a ParseResult and edition payloads.

    Collects field-level evidence from:
    - Edition payloads (field path, confidence, page, source_fact_ids)
    - Mirror cell evidence (via evidence bundle paths)
    - Key-value fields on each page

    Fields without any page, bbox, or source_refs enter
    ``unresolved_fields`` as ``needs_evidence``.
    """
    ledger = SourceSpanLedger(document_id=document_id, task_id=task_id)

    # ── Collect from edition payloads ──
    for edition, payload in (editions or {}).items():
        if not isinstance(payload, dict):
            continue
        fields = (payload.get("data") or {}).get("fields") or {}
        meta = payload.get("metadata") or {}
        quality = payload.get("quality") or {}
        conf = float(quality.get("confidence", 0.0) or 0.0)
        source_page = meta.get("source_page")
        source_bbox = meta.get("source_bbox")
        source_fact_ids = meta.get("source_fact_ids", [])
        fallback_reason = meta.get("fallback_reason")

        if isinstance(fields, dict):
            for key, value in fields.items():
                field_path = f"{edition}.data.fields.{key}"
                rendered = "" if value is None else str(value)

                has_evidence = bool(source_page or source_bbox or source_fact_ids)
                review: Literal["auto_accepted", "needs_review", "needs_evidence"]
                if not has_evidence and not fallback_reason:
                    review = "needs_evidence"
                elif conf < 0.5:
                    review = "needs_review"
                elif conf < 0.8:
                    review = "auto_accepted"
                else:
                    review = "auto_accepted"

                if has_evidence:
                    ledger.add_span(SourceSpanEntry(
                        field_path=field_path,
                        source_refs=source_fact_ids,
                        page=int(source_page) if source_page else 0,
                        bbox=list(source_bbox) if source_bbox else None,
                        raw=rendered,
                        normalized=rendered,
                        confidence=conf,
                        review=review,
                        edition=edition,
                        kind="edition_field",
                        metadata={"fallback_reason": fallback_reason} if fallback_reason else {},
                    ))
                else:
                    ledger.add_unresolved(UnresolvedField(
                        field_path=field_path,
                        reason="no_source_ref" if not source_fact_ids else "no_page_or_bbox",
                        review="needs_evidence",
                    ))

        # Record-level spans
        records = (payload.get("data") or {}).get("records") or []
        for rec_idx, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            rec_source_fact_ids = record.get("source_fact_ids", [])
            rec_conf = float(record.get("confidence", conf) or 0.0)
            if rec_source_fact_ids:
                ledger.add_span(SourceSpanEntry(
                    field_path=f"{edition}.data.records[{rec_idx}]",
                    source_refs=rec_source_fact_ids,
                    page=int(source_page) if source_page else 0,
                    confidence=rec_conf,
                    review="auto_accepted" if rec_conf >= 0.8 else "needs_review",
                    edition=edition,
                    kind="record",
                ))

    # ── Collect from Mirror pages (cell evidence) ──
    for page in getattr(result, "pages", []) or []:
        page_no = int(getattr(page, "page_number", 1) or 1)

        # Text spans
        for text_idx, text in enumerate(getattr(page, "texts", []) or []):
            content = str(getattr(text, "content", "") or "")
            if not content.strip():
                continue
            src_refs = list(getattr(text, "source_refs", []) or [])
            conf = float(getattr(text, "confidence", 1.0) or 1.0)
            bbox = getattr(text, "bbox", None)

            if src_refs or bbox:
                ledger.add_span(SourceSpanEntry(
                    field_path=f"mirror.pages[{page_no - 1}].texts[{text_idx}]",
                    source_refs=src_refs,
                    page=page_no,
                    bbox=list(bbox) if bbox else None,
                    raw=content[:200],
                    normalized=content[:200],
                    confidence=conf,
                    review="auto_accepted" if conf >= 0.8 else "needs_review",
                    kind="text",
                ))

        # Table cell spans
        for table_idx, table in enumerate(getattr(page, "tables", []) or []):
            data_rows = list(getattr(table, "data_rows", []) or getattr(table, "rows", []) or [])
            for row_idx, row in enumerate(data_rows):
                for col_idx, cell in enumerate(getattr(row, "cells", []) or []):
                    value = str(getattr(cell, "cleaned", None) or getattr(cell, "text", "") or "")
                    if not value:
                        continue
                    src_refs = list(
                        getattr(cell, "source_cell_refs", [])
                        or getattr(cell, "evidence_ids", [])
                        or []
                    )
                    conf = float(getattr(cell, "confidence", 1.0) or 0.0)
                    bbox = getattr(cell, "bbox", None) or getattr(cell, "bbox_norm", None)

                    if src_refs or bbox:
                        ledger.add_span(SourceSpanEntry(
                            field_path=(
                                f"mirror.pages[{page_no - 1}].tables[{table_idx}]"
                                f".rows[{row_idx}].cells[{col_idx}]"
                            ),
                            source_refs=src_refs,
                            page=page_no,
                            bbox=list(bbox) if bbox else None,
                            raw=str(getattr(cell, "text", "") or ""),
                            normalized=value,
                            confidence=conf,
                            review="auto_accepted" if conf >= 0.8 else "needs_review",
                            kind="cell",
                        ))

        # Key-value spans
        for kv_idx, kv in enumerate(getattr(page, "key_values", []) or []):
            key = str(getattr(kv, "key", "") or "")
            val = str(getattr(kv, "value", "") or "")
            if not key and not val:
                continue
            src_refs = list(getattr(kv, "source_refs", []) or [])
            conf = float(getattr(kv, "confidence", 1.0) or 0.0)
            bbox = getattr(kv, "bbox", None)

            if src_refs or bbox:
                ledger.add_span(SourceSpanEntry(
                    field_path=f"mirror.pages[{page_no - 1}].key_values[{kv_idx}]",
                    source_refs=src_refs,
                    page=page_no,
                    bbox=list(bbox) if bbox else None,
                    raw=f"{key}: {val}",
                    normalized=f"{key}: {val}",
                    confidence=conf,
                    review="auto_accepted" if conf >= 0.8 else "needs_review",
                    kind="key_value",
                ))

    return ledger


__all__ = [
    "SourceSpanEntry",
    "UnresolvedField",
    "SourceSpanLedger",
    "build_source_span_ledger",
]
