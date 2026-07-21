# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standalone, lossless-enough source view for Community credit reports."""

from __future__ import annotations

from typing import Any


def _page_bundles(parse_result: Any) -> dict[int, dict[str, Any]]:
    ds = getattr(getattr(parse_result, "entities", None), "domain_specific", {})
    if not isinstance(ds, dict):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for bundle in ds.get("_page_evidence_bundles") or []:
        if not isinstance(bundle, dict):
            continue
        page = int(bundle.get("page") or 0)
        if page > 0:
            out[page] = bundle
    return out


def _cell_payload(cell: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "text": str(getattr(cell, "text", "") or ""),
        "data_type": str(getattr(getattr(cell, "data_type", None), "value", "") or "unknown"),
        "row_index": getattr(cell, "row_index", None),
        "col_index": getattr(cell, "col_index", None),
        "row_span": int(getattr(cell, "row_span", 1) or 1),
        "col_span": int(getattr(cell, "col_span", 1) or 1),
        "geometry_status": str(getattr(cell, "geometry_status", "") or "missing"),
        "evidence_ids": list(getattr(cell, "evidence_ids", []) or []),
        "token_ids": list(getattr(cell, "token_ids", []) or []),
    }
    bbox = getattr(cell, "bbox", None)
    if bbox and len(bbox) == 4:
        payload["bbox"] = [round(float(value), 4) for value in bbox]
    confidence = getattr(cell, "geometry_confidence", None)
    if confidence is not None:
        payload["confidence"] = round(float(confidence), 4)
    loss_reason = getattr(cell, "geometry_loss_reason", None)
    if loss_reason:
        payload["geometry_loss_reason"] = str(loss_reason)
    return payload


def _table_payload(table: Any, *, logical_page: int, source_page: int) -> dict[str, Any]:
    headers = [str(value or "") for value in (getattr(table, "headers", []) or [])]
    rows = [
        [_cell_payload(cell) for cell in (getattr(row, "cells", []) or [])] for row in getattr(table, "rows", []) or []
    ]
    payload: dict[str, Any] = {
        "table_id": str(getattr(table, "table_id", "") or f"source_table:p{logical_page:04d}"),
        "logical_page": logical_page,
        "source_page": source_page,
        "headers": headers,
        "rows": rows,
        "row_count": len(rows),
        "column_count": max([len(headers), *(len(row) for row in rows)], default=0),
        "confidence": round(float(getattr(table, "confidence", 0.0) or 0.0), 4),
        "extraction_layer": str(getattr(table, "extraction_layer", "") or ""),
        "evidence_ids": list(getattr(table, "evidence_ids", []) or []),
    }
    bbox = getattr(table, "bbox", None)
    if bbox and len(bbox) == 4:
        payload["bbox"] = [round(float(value), 4) for value in bbox]
    metadata = getattr(table, "metadata", None) or {}
    if isinstance(metadata, dict) and isinstance(metadata.get("raw_rows"), list):
        payload["raw_rows"] = [
            [str(value or "") for value in row] for row in metadata["raw_rows"] if isinstance(row, list)
        ]
    return payload


def build_credit_source_content(parse_result: Any) -> dict[str, Any]:
    """Preserve recognized logical-page text and every physical table/cell."""
    bundles = _page_bundles(parse_result)
    pages_payload: list[dict[str, Any]] = []
    tables_payload: list[dict[str, Any]] = []
    non_empty_cell_count = 0
    for index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        logical_page = int(getattr(page, "page_number", 0) or index)
        source_page = int(getattr(page, "source_page_number", 0) or logical_page)
        bundle = bundles.get(logical_page, {})
        local = bundle.get("local_structure_evidence") if isinstance(bundle, dict) else {}
        raw_tokens = list(bundle.get("tokens") or []) if isinstance(bundle, dict) else []
        lines = local.get("lines") if isinstance(local, dict) else None
        text_blocks: list[dict[str, Any]] = []
        if isinstance(lines, list) and lines:
            for line in lines:
                if not isinstance(line, dict) or not str(line.get("text") or line.get("content") or "").strip():
                    continue
                item = {
                    "text": str(line.get("text") or line.get("content") or ""),
                    "bbox": list(line.get("bbox") or []),
                    "confidence": float(line.get("confidence") or 0.0),
                    "evidence_ids": list(line.get("evidence_ids") or []),
                }
                text_blocks.append(item)
        else:
            for text in getattr(page, "texts", []) or []:
                value = str(getattr(text, "content", "") or "").strip()
                if not value:
                    continue
                text_blocks.append(
                    {
                        "text": value,
                        "bbox": list(getattr(text, "bbox", None) or []),
                        "confidence": float(getattr(text, "confidence", 0.0) or 0.0),
                        "evidence_ids": list(getattr(text, "evidence_ids", []) or []),
                    }
                )

        page_table_ids: list[str] = []
        for table in getattr(page, "tables", []) or []:
            table_payload = _table_payload(table, logical_page=logical_page, source_page=source_page)
            page_table_ids.append(table_payload["table_id"])
            non_empty_cell_count += sum(
                bool(str(cell.get("text") or "").strip()) for row in table_payload["rows"] for cell in row
            )
            non_empty_cell_count += sum(bool(str(value or "").strip()) for value in table_payload["headers"])
            tables_payload.append(table_payload)

        pages_payload.append(
            {
                "logical_page": logical_page,
                "source_page": source_page,
                "width": getattr(page, "width", None),
                "height": getattr(page, "height", None),
                "text": "\n".join(item["text"] for item in text_blocks),
                "text_blocks": text_blocks,
                "ocr_tokens": [dict(token) for token in raw_tokens if isinstance(token, dict)],
                "key_values": [
                    {
                        "key": str(getattr(item, "key", "") or ""),
                        "value": str(getattr(item, "value", "") or ""),
                        "evidence_ids": list(getattr(item, "evidence_ids", []) or []),
                    }
                    for item in getattr(page, "key_values", []) or []
                ],
                "local_structures": list(local.get("structures") or []) if isinstance(local, dict) else [],
                "micro_grids": list(bundle.get("micro_grid_structures") or []) if isinstance(bundle, dict) else [],
                "source_table_ids": page_table_ids,
                "coordinate_transform": dict(getattr(page, "coordinate_transform", None) or {}),
            }
        )

    source_pages = {int(item["source_page"]) for item in pages_payload if int(item["source_page"]) > 0}
    source_token_count = sum(len(item["ocr_tokens"]) for item in pages_payload)
    captured_token_count = sum(
        bool(str(token.get("text") or token.get("content") or "").strip())
        for item in pages_payload
        for token in item["ocr_tokens"]
    )
    captured_table_count = len({table["table_id"] for table in tables_payload})
    conservation_passed = (
        len(pages_payload) == len(list(getattr(parse_result, "pages", []) or []))
        and captured_table_count == len(tables_payload)
        and captured_token_count == source_token_count
    )
    return {
        "schema_version": "credit_report.source_content.v1",
        "source_page_count": len(source_pages),
        "logical_page_count": len(pages_payload),
        "table_count": len(tables_payload),
        "non_empty_table_cell_count": non_empty_cell_count,
        "ocr_token_count": source_token_count,
        "conservation_audit": {
            "status": "pass" if conservation_passed else "review",
            "logical_page_coverage": 1.0 if pages_payload else None,
            "ocr_token_coverage": round(captured_token_count / source_token_count, 4) if source_token_count else None,
            "physical_table_coverage": 1.0 if tables_payload else None,
            "captured_physical_table_count": captured_table_count,
            "captured_non_empty_table_cell_count": non_empty_cell_count,
        },
        "pages": pages_payload,
        "source_tables": tables_payload,
    }


__all__ = ["build_credit_source_content"]
