# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Visual overlay data builder — field-level bbox, confidence, and source_refs.

GA 1.0 design §8.4 EV-6 / OUT4-1: Generates structured overlay data that the
visual_debug.html renderer consumes to display bbox, confidence, source_refs,
and needs_review markers for every field in the document.

Usage::

    from docmirror.evidence.visual import build_visual_overlay
    overlay = build_visual_overlay(result, editions, evidence_bundle)
"""

from __future__ import annotations

from typing import Any


def build_visual_overlay(
    result: Any,
    editions: dict[str, Any] | None = None,
    evidence_bundle: dict[str, Any] | None = None,
    *,
    include_sensitive: bool = False,
) -> dict[str, Any]:
    """Build structured visual overlay data for field-level bbox rendering.

    Returns:
        Dict with ``pages`` array, each containing fields with bbox,
        confidence, source_refs, needs_review, and visualization hints.
    """
    pages: list[dict[str, Any]] = []

    # Collect from evidence bundle ledger
    ledger = (evidence_bundle or {}).get("ledger") or []

    # Group ledger entries by page
    ledger_by_page: dict[int, list[dict[str, Any]]] = {}
    for entry in ledger:
        page = entry.get("page")
        if page is not None:
            ledger_by_page.setdefault(int(page), []).append(entry)

    # Collect from result pages
    result_pages = list(getattr(result, "pages", []) or [])
    for page_idx, page in enumerate(result_pages, start=1):
        page_no = int(getattr(page, "page_number", page_idx) or page_idx)
        page_fields: list[dict[str, Any]] = []

        # Text fields
        for text_idx, text in enumerate(getattr(page, "texts", []) or []):
            content = str(getattr(text, "content", "") or "")
            if not content.strip():
                continue
            role = str(getattr(text, "mirror_role", "") or getattr(text, "level", "") or "").lower()
            confidence = float(getattr(text, "confidence", 1.0) or 1.0)

            page_fields.append({
                "field_path": f"mirror.pages[{page_no - 1}].texts[{text_idx}]",
                "value": content[:200],
                "confidence": confidence,
                "bbox": getattr(text, "bbox", None) or getattr(text, "bbox_norm", None),
                "source_refs": list(getattr(text, "source_refs", []) or []),
                "role": role,
                "needs_review": confidence < 0.8 or role in ("header", "footer", "watermark"),
                "kind": "text",
            })

        # Table fields
        for table_idx, table in enumerate(getattr(page, "tables", []) or []):
            headers = list(getattr(table, "headers", []) or [])
            data_rows = list(getattr(table, "data_rows", []) or getattr(table, "rows", []) or [])

            for row_idx, row in enumerate(data_rows):
                for col_idx, cell in enumerate(getattr(row, "cells", []) or []):
                    value = str(getattr(cell, "cleaned", None) or getattr(cell, "text", "") or "")
                    if not value:
                        continue
                    conf = float(getattr(cell, "confidence", 1.0) or 0.0)

                    col_name = headers[col_idx] if col_idx < len(headers) else f"col_{col_idx}"
                    page_fields.append({
                        "field_path": f"mirror.pages[{page_no - 1}].tables[{table_idx}].rows[{row_idx}].{col_name}",
                        "value": value[:200] if include_sensitive else _redact_value(value),
                        "confidence": conf,
                        "bbox": getattr(cell, "bbox", None) or getattr(cell, "bbox_norm", None),
                        "source_refs": list(
                            getattr(cell, "source_cell_refs", [])
                            or getattr(cell, "evidence_ids", [])
                            or []
                        ),
                        "role": col_name,
                        "needs_review": conf < 0.8,
                        "kind": "cell",
                        "row_index": row_idx,
                        "col_index": col_idx,
                    })

        # Key-value fields
        for kv_idx, kv in enumerate(getattr(page, "key_values", []) or []):
            key = str(getattr(kv, "key", "") or "")
            value = str(getattr(kv, "value", "") or "")
            if not key and not value:
                continue
            conf = float(getattr(kv, "confidence", 1.0) or 0.0)

            page_fields.append({
                "field_path": f"mirror.pages[{page_no - 1}].key_values[{kv_idx}]",
                "value": f"{key}: {value}"[:200] if include_sensitive else f"{key}: {_redact_value(value)}",
                "confidence": conf,
                "bbox": getattr(kv, "bbox", None),
                "source_refs": list(getattr(kv, "source_refs", []) or []),
                "role": "key_value",
                "needs_review": conf < 0.8,
                "kind": "key_value",
            })

        # Fields from edition projections
        if editions:
            for edition_name, payload in (editions or {}).items():
                if not isinstance(payload, dict):
                    continue
                fields = (payload.get("data") or {}).get("fields") or {}
                if isinstance(fields, dict):
                    for field_key, field_value in fields.items():
                        rendered = str(field_value)[:200] if include_sensitive else _redact_value(str(field_value))
                        conf = float((payload.get("quality") or {}).get("confidence", 0.0) or 0.0)

                        page_fields.append({
                            "field_path": f"{edition_name}.data.fields.{field_key}",
                            "value": rendered,
                            "confidence": conf,
                            "bbox": (payload.get("metadata") or {}).get("source_bbox"),
                            "source_refs": (payload.get("metadata") or {}).get("source_fact_ids", []),
                            "role": field_key,
                            "needs_review": conf < 0.8 or not (payload.get("metadata") or {}).get("source_fact_ids"),
                            "kind": "edition_field",
                            "edition": edition_name,
                            "support_level": (payload.get("metadata") or {}).get("support_level", "unknown"),
                        })

        # Add ledger entries that match this page
        for entry in ledger_by_page.get(page_no, []):
            fact_id = entry.get("fact_id", "")
            bbox = entry.get("bbox")
            if not bbox:
                continue
            conf = float(entry.get("confidence", 1.0) or 0.0)
            page_fields.append({
                "field_path": f"ledger.{fact_id}",
                "value": str(entry.get("normalized_value") or entry.get("raw_value", ""))[:200],
                "confidence": conf,
                "bbox": bbox,
                "source_refs": list(entry.get("source_refs", []) or []),
                "role": entry.get("kind", "unknown"),
                "needs_review": entry.get("review", "") in ("needs_review", "needs_evidence"),
                "kind": "ledger_entry",
                "ledger_kind": entry.get("kind", "unknown"),
            })

        pages.append({
            "page_number": page_no,
            "fields": page_fields,
            "field_count": len(page_fields),
            "needs_review_count": sum(1 for f in page_fields if f.get("needs_review")),
        })

    # Add unresolved evidence entries
    unresolved_fields: list[dict[str, Any]] = []
    for entry in (evidence_bundle or {}).get("unresolved") or []:
        unresolved_fields.append({
            "field_path": entry.get("field_path", "unknown"),
            "value": _redact_value(entry.get("value", "")),
            "confidence": float(entry.get("confidence", 0.0) or 0.0),
            "bbox": None,
            "source_refs": [],
            "role": "unresolved",
            "needs_review": True,
            "kind": "unresolved_evidence",
            "reason": entry.get("reason", "no_page_or_bbox_or_source_refs"),
        })

    # Build summary
    total_fields = sum(p["field_count"] for p in pages) + len(unresolved_fields)
    total_needs_review = sum(p["needs_review_count"] for p in pages) + len(unresolved_fields)
    has_bbox = sum(1 for p in pages for f in p["fields"] if f.get("bbox"))
    has_source_refs = sum(1 for p in pages for f in p["fields"] if f.get("source_refs"))

    return {
        "version": 2,
        "pages": pages,
        "unresolved_fields": unresolved_fields,
        "summary": {
            "page_count": len(pages),
            "total_fields": total_fields,
            "total_fields_with_bbox": has_bbox,
            "total_fields_with_source_refs": has_source_refs,
            "total_needs_review": total_needs_review,
            "bbox_coverage": round(has_bbox / total_fields, 4) if total_fields else 0.0,
            "source_ref_coverage": round(has_source_refs / total_fields, 4) if total_fields else 0.0,
        },
        "review_fields": [
            {
                "field_path": f["field_path"],
                "reason": "low_confidence" if f.get("confidence", 1.0) < 0.8 else "no_evidence",
            }
            for p in pages
            for f in p["fields"]
            if f.get("needs_review")
        ],
    }


def _redact_value(value: str) -> str:
    """Redact sensitive values for default-safe display.

    Replaces numeric values with their length and alphabetic characters
    with asterisks, preserving hints about the value structure.
    """
    if not value:
        return "[empty]"
    if len(value) <= 3:
        return "*" * len(value)
    if value.replace(".", "").replace(",", "").replace("-", "").isdigit():
        return f"[{len(value)} chars numeric]"
    if value.isalpha():
        return value[0] + "*" * (len(value) - 2) + value[-1] if len(value) > 2 else "*" * len(value)
    return "[redacted]"


__all__ = [
    "build_visual_overlay",
]
