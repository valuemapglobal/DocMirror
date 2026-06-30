# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Evidence Ledger — unified single-source-of-truth for all Mirror fact evidence.

GA 1.0 design §7.2: Every consumable Mirror fact receives a stable
``evidence_id`` alongside ``fact_id``, and the ledger aggregates page,
bbox, source_refs, confidence, extraction_layer, quality_flags, and
review status so that downstream consumers (Markdown, Edition, Evidence
Bundle, Visual Debug) all read from one authoritative evidence source.

Usage::

    from docmirror.evidence.ledger import build_evidence_ledger
    ledger = build_evidence_ledger(result)
"""

from __future__ import annotations

from typing import Any

from docmirror.models.mirror.fact_identity import (
    fact_id_for_cell,
    fact_id_for_formula,
    fact_id_for_image,
    fact_id_for_page,
    fact_id_for_section,
    fact_id_for_table,
    fact_id_for_text_block,
)


def _review_for_confidence(confidence: float) -> str:
    if confidence <= 0.0:
        return "needs_evidence"
    if confidence < 0.5:
        return "needs_review"
    if confidence < 0.8:
        return "auto_accepted"
    return "auto_accepted"


def _normalize_sort_key(record: dict[str, Any]) -> tuple[int, int, int, int, int]:
    """Sort ledger records: page > kind priority > table_index > row > col."""
    kind_order = {"page": 0, "text": 1, "span": 2, "table": 3, "cell": 4, "formula": 5, "section": 6, "image": 7}
    page = int(record.get("page") or 0)
    kind = kind_order.get(str(record.get("kind") or ""), 99)
    table_idx = int(record.get("table_index", 0) or 0)
    row_idx = int(record.get("row_index", 0) or 0)
    col_idx = int(record.get("col_index", 0) or 0)
    return (page, kind, table_idx, row_idx, col_idx)


def _collect_page_entries(result: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pages = list(getattr(result, "pages", []) or [])
    for page_idx, page in enumerate(pages, start=1):
        fact_id = fact_id_for_page(page_idx)
        entries.append(
            {
                "evidence_id": f"ev:{fact_id}",
                "fact_id": fact_id,
                "kind": "page",
                "page": page_idx,
                "bbox": getattr(page, "bbox", None),
                "bbox_space": "page_pixels",
                "source_refs": [],
                "raw_value": "",
                "normalized_value": "",
                "confidence": float(getattr(page, "confidence", 0.0) or 0.0),
                "extraction_layer": "document_page",
                "quality_flags": [],
                "review": "auto_accepted",
                "page_count": len(pages),
            }
        )
    return entries


def _collect_text_entries(result: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pages = list(getattr(result, "pages", []) or [])
    for page_idx, page in enumerate(pages, start=1):
        for text_idx, text in enumerate(getattr(page, "texts", []) or []):
            fact_id = fact_id_for_text_block(page_idx, text_idx)
            entries.append(
                {
                    "evidence_id": f"ev:{fact_id}",
                    "fact_id": fact_id,
                    "kind": "text",
                    "page": page_idx,
                    "bbox": getattr(text, "bbox", None),
                    "bbox_space": "page_pixels",
                    "source_refs": list(getattr(text, "source_refs", []) or []),
                    "raw_value": str(getattr(text, "content", "") or ""),
                    "normalized_value": "",
                    "confidence": float(getattr(text, "confidence", 1.0) or 0.0),
                    "extraction_layer": str(
                        getattr(text, "extraction_layer", "") or getattr(text, "source", "") or "text_block"
                    ),
                    "quality_flags": list(getattr(text, "quality_flags", []) or []),
                    "review": _review_for_confidence(float(getattr(text, "confidence", 1.0) or 0.0)),
                }
            )
    return entries


def _collect_table_entries(result: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pages = list(getattr(result, "pages", []) or [])
    for page_idx, page in enumerate(pages, start=1):
        for table_idx, table in enumerate(getattr(page, "tables", []) or []):
            fact_id = fact_id_for_table(page_idx, table_idx)
            entries.append(
                {
                    "evidence_id": f"ev:{fact_id}",
                    "fact_id": fact_id,
                    "kind": "table",
                    "page": page_idx,
                    "bbox": getattr(table, "bbox", None),
                    "bbox_space": "page_pixels",
                    "source_refs": [],
                    "raw_value": "",
                    "normalized_value": "",
                    "confidence": float(getattr(table, "confidence", 1.0) or 0.0),
                    "extraction_layer": str(
                        getattr(table, "extraction_layer", "") or getattr(table, "table_source", "") or "table_detect"
                    ),
                    "quality_flags": [],
                    "review": "auto_accepted",
                    "header_columns": list(getattr(table, "headers", []) or []),
                    "rows_count": len(list(getattr(table, "data_rows", []) or getattr(table, "rows", []) or [])),
                }
            )

            data_rows = list(getattr(table, "data_rows", []) or getattr(table, "rows", []) or [])
            for row_idx, row in enumerate(data_rows):
                for col_idx, cell in enumerate(getattr(row, "cells", []) or []):
                    cell_fact_id = fact_id_for_cell(page_idx, table_idx, row_idx, col_idx)
                    raw = str(getattr(cell, "text", "") or "")
                    cleaned = str(getattr(cell, "cleaned", None) or raw)
                    entries.append(
                        {
                            "evidence_id": f"ev:{cell_fact_id}",
                            "fact_id": cell_fact_id,
                            "kind": "cell",
                            "page": page_idx,
                            "bbox": getattr(cell, "bbox", None) or getattr(cell, "bbox_norm", None),
                            "bbox_space": "page_pixels",
                            "source_refs": list(
                                getattr(cell, "source_cell_refs", []) or getattr(cell, "evidence_ids", []) or []
                            ),
                            "raw_value": raw,
                            "normalized_value": cleaned,
                            "confidence": float(getattr(cell, "confidence", 1.0) or 0.0),
                            "extraction_layer": str(
                                getattr(cell, "extraction_layer", "") or getattr(cell, "source", "") or "cell_extract"
                            ),
                            "quality_flags": list(getattr(cell, "quality_flags", []) or []),
                            "review": _review_for_confidence(float(getattr(cell, "confidence", 1.0) or 0.0)),
                            "table_index": table_idx,
                            "row_index": row_idx,
                            "col_index": col_idx,
                        }
                    )
    return entries


def _collect_section_entries(result: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    sections = list(getattr(result, "sections", []) or [])
    for sec_idx, section in enumerate(sections, start=1):
        fact_id = fact_id_for_section(sec_idx)
        entries.append(
            {
                "evidence_id": f"ev:{fact_id}",
                "fact_id": fact_id,
                "kind": "section",
                "page": int(getattr(section, "page_start", 1) or 1),
                "bbox": getattr(section, "bbox", None),
                "bbox_space": "page_pixels",
                "source_refs": [],
                "raw_value": str(getattr(section, "title", "") or getattr(section, "name", "") or ""),
                "normalized_value": "",
                "confidence": float(getattr(section, "confidence", 1.0) or 0.0),
                "extraction_layer": "document_structure",
                "quality_flags": [],
                "review": "auto_accepted",
            }
        )
    return entries


def _collect_formula_entries(result: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    formulas = list(getattr(result, "formulas", []) or [])
    for f_idx, formula in enumerate(formulas, start=1):
        page_no = int(getattr(formula, "page", 1) or 1)
        fact_id = fact_id_for_formula(page_no, f_idx)
        entries.append(
            {
                "evidence_id": f"ev:{fact_id}",
                "fact_id": fact_id,
                "kind": "formula",
                "page": page_no,
                "bbox": getattr(formula, "bbox", None),
                "bbox_space": "page_pixels",
                "source_refs": list(getattr(formula, "source_refs", []) or []),
                "raw_value": str(getattr(formula, "raw", "") or getattr(formula, "content", "") or ""),
                "normalized_value": str(getattr(formula, "latex", "") or getattr(formula, "normalized", "") or ""),
                "confidence": float(getattr(formula, "confidence", 1.0) or 0.0),
                "extraction_layer": str(
                    getattr(formula, "extraction_layer", "") or getattr(formula, "source", "") or "formula_extract"
                ),
                "quality_flags": [],
                "review": _review_for_confidence(float(getattr(formula, "confidence", 1.0) or 0.0)),
            }
        )
    return entries


def _collect_image_entries(result: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    images = list(getattr(result, "images", []) or [])
    for i_idx, image in enumerate(images, start=1):
        page_no = int(getattr(image, "page", 1) or 1)
        fact_id = fact_id_for_image(page_no, i_idx)
        entries.append(
            {
                "evidence_id": f"ev:{fact_id}",
                "fact_id": fact_id,
                "kind": "image",
                "page": page_no,
                "bbox": getattr(image, "bbox", None),
                "bbox_space": "page_pixels",
                "source_refs": list(getattr(image, "source_refs", []) or []),
                "raw_value": str(getattr(image, "alt", "") or getattr(image, "path", "") or ""),
                "normalized_value": "",
                "confidence": float(getattr(image, "confidence", 1.0) or 0.0),
                "extraction_layer": str(
                    getattr(image, "extraction_layer", "") or getattr(image, "source", "") or "image_extract"
                ),
                "quality_flags": [],
                "review": _review_for_confidence(float(getattr(image, "confidence", 1.0) or 0.0)),
            }
        )
    return entries


def build_evidence_ledger(result: Any) -> list[dict[str, Any]]:
    """Build the unified Evidence Ledger from a ParseResult.

    Collects all page, text, table, cell, section, formula, and image
    entries with stable ``evidence_id`` and ``fact_id``, sorted in a
    deterministic order for reproducible output.

    Returns:
        List of evidence ledger records.
    """
    entries: list[dict[str, Any]] = []
    entries.extend(_collect_page_entries(result))
    entries.extend(_collect_text_entries(result))
    entries.extend(_collect_table_entries(result))
    entries.extend(_collect_section_entries(result))
    entries.extend(_collect_formula_entries(result))
    entries.extend(_collect_image_entries(result))
    entries.sort(key=_normalize_sort_key)
    return entries


def ledger_summary(ledger: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics for a built ledger.

    Returns counts by kind, coverage metrics (bbox, source_refs, page),
    and review status breakdown.
    """
    by_kind: dict[str, int] = {}
    has_bbox = 0
    has_page = 0
    has_source_refs = 0
    total = len(ledger)
    review_counts: dict[str, int] = {"auto_accepted": 0, "needs_review": 0, "needs_evidence": 0}
    total_confidence = 0.0
    confidence_count = 0

    for item in ledger:
        kind = str(item.get("kind") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1

        if item.get("bbox"):
            has_bbox += 1
        if item.get("page"):
            has_page += 1
        if item.get("source_refs"):
            has_source_refs += 1

        review = str(item.get("review") or "auto_accepted")
        if review in review_counts:
            review_counts[review] += 1

        conf = item.get("confidence")
        if conf is not None:
            total_confidence += float(conf)
            confidence_count += 1

    return {
        "total_entries": total,
        "by_kind": by_kind,
        "coverage": {
            "bbox": {"count": has_bbox, "ratio": round(has_bbox / total, 4) if total else 0.0},
            "page": {"count": has_page, "ratio": round(has_page / total, 4) if total else 0.0},
            "source_refs": {"count": has_source_refs, "ratio": round(has_source_refs / total, 4) if total else 0.0},
        },
        "confidence": {
            "mean": round(total_confidence / confidence_count, 4) if confidence_count else 0.0,
            "count": confidence_count,
        },
        "review": review_counts,
    }


__all__ = [
    "build_evidence_ledger",
    "ledger_summary",
]
