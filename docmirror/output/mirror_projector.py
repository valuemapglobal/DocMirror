# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read-only Mirror projection from a sealed canonical snapshot."""

from __future__ import annotations

from typing import Any

from docmirror.models.entities.parse_result import CellValue, ParseResult
from docmirror.models.sealed import SealedParseResult


def _profile(mirror_level: str | None) -> str:
    level = str(mirror_level or "").strip().lower()
    if level in {"forensic", "ga_full", "full"}:
        return "forensic"
    if level in {"compact", "canonical_compact"}:
        return "canonical_compact"
    return "canonical_full"


def _build_scanned_ocr_page_pool(*evidence_groups: Any) -> tuple[list[dict[str, Any]], dict[tuple[Any, Any], str]]:
    pages: list[dict[str, Any]] = []
    refs: dict[tuple[Any, Any], str] = {}
    seen: set[tuple[Any, Any]] = set()
    for group in evidence_groups:
        if not isinstance(group, list):
            continue
        for evidence in group:
            if not isinstance(evidence, dict) or ("lines" not in evidence and "tokens" not in evidence):
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
                    "line_count": len(evidence.get("lines") or []),
                    "token_count": len(evidence.get("tokens") or []),
                    "payload": "external_evidence_bundle",
                }
            )
    return pages, refs


def _strip_scanned_ocr_payload(
    evidence_group: Any,
    refs: dict[tuple[Any, Any], str],
) -> list[dict[str, Any]]:
    if not isinstance(evidence_group, list):
        return []
    out: list[dict[str, Any]] = []
    for evidence in evidence_group:
        if not isinstance(evidence, dict):
            continue
        item = {key: value for key, value in evidence.items() if key not in {"lines", "tokens"}}
        source = item.get("source") or "scanned_page_ocr"
        ref = refs.get((item.get("page"), source))
        if ref:
            item["ocr_page_ref"] = ref
        out.append(item)
    return out


def _strip_inline_page_evidence_bundles(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_inline_page_evidence_bundles(item)
            for key, item in value.items()
            if key not in {"_page_evidence_bundles", "page_evidence_bundles"}
        }
    if isinstance(value, list):
        return [_strip_inline_page_evidence_bundles(item) for item in value]
    return value


def _strip_ocr_text_atoms(payload: dict[str, Any], *, include_text: bool | None) -> None:
    if include_text is not False:
        return
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict) or not isinstance(evidence.get("text_atoms"), list):
        return
    kept: list[Any] = []
    removed_ids: set[str] = set()
    for atom in evidence["text_atoms"]:
        if not isinstance(atom, dict):
            kept.append(atom)
            continue
        metadata = atom.get("metadata") if isinstance(atom.get("metadata"), dict) else {}
        source_kind = str(atom.get("source_kind") or "")
        if metadata.get("ocr_evidence_key") or source_kind.endswith("_evidence_token"):
            if atom.get("id"):
                removed_ids.add(str(atom["id"]))
            continue
        kept.append(atom)
    if not removed_ids:
        return
    evidence["text_atoms"] = kept
    indexes = evidence.get("indexes")
    if isinstance(indexes, dict):
        for key, value in list(indexes.items()):
            if isinstance(value, list):
                indexes[key] = [item for item in value if str(item) not in removed_ids]
            elif isinstance(value, dict):
                indexes[key] = {
                    sub_key: [item for item in sub_value if str(item) not in removed_ids]
                    for sub_key, sub_value in value.items()
                    if isinstance(sub_value, list)
                }


def _strip_redundant_structures(evidence_group: Any, api_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(evidence_group, list):
        return []
    pages_with_structures = {
        int(page.get("page_number") or 0)
        for page in api_pages
        if isinstance(page, dict)
        and any(
            isinstance(region, dict) and region.get("kind") in {"field_grid", "label_value_graph"}
            for region in page.get("regions") or []
        )
    }
    out: list[dict[str, Any]] = []
    for evidence in evidence_group:
        if not isinstance(evidence, dict):
            continue
        if int(evidence.get("page") or 0) in pages_with_structures and evidence.get("structures"):
            item = {key: value for key, value in evidence.items() if key != "structures"}
            item["structures_in_regions"] = True
            out.append(item)
        else:
            out.append(dict(evidence))
    return out


def _serialize_cell(cell: CellValue, *, forensic: bool) -> dict[str, Any]:
    output: dict[str, Any] = {
        "text": cell.text,
        "data_type": (cell.data_type.value if hasattr(cell.data_type, "value") else cell.data_type) or "text",
    }
    if not forensic and cell.geometry_status:
        output["geometry_status"] = cell.geometry_status
    if not forensic and cell.source_cell_refs:
        output["source_cell_refs"] = cell.source_cell_refs
    if forensic:
        optional = {
            "cleaned": cell.cleaned,
            "numeric": cell.numeric,
            "bbox": cell.bbox,
            "bbox_norm": cell.bbox_norm,
            "row_index": cell.row_index,
            "col_index": cell.col_index,
            "geometry_source": cell.geometry_source,
            "geometry_confidence": cell.geometry_confidence,
            "geometry_loss_reason": cell.geometry_loss_reason,
            "evidence_ids": cell.evidence_ids,
            "token_ids": cell.token_ids,
            "source_cell_refs": cell.source_cell_refs,
        }
        output.update({key: value for key, value in optional.items() if value not in (None, "", [], {})})
        if cell.confidence != 1.0:
            output["confidence"] = cell.confidence
        if cell.row_span != 1:
            output["row_span"] = cell.row_span
        if cell.col_span != 1:
            output["col_span"] = cell.col_span
        if cell.geometry_status != "missing":
            output["geometry_status"] = cell.geometry_status
    if getattr(cell, "slm_entities", None):
        output["slm_entities"] = cell.slm_entities
    return output


def _build_api_pages(result: ParseResult, *, forensic: bool) -> list[dict[str, Any]]:
    api_pages: list[dict[str, Any]] = []
    for page in result.pages:
        api_page: dict[str, Any] = {"page_number": page.page_number}
        if page.width is not None:
            api_page["width"] = page.width
        if page.height is not None:
            api_page["height"] = page.height
        if page.tables:
            api_page["tables"] = []
            for table in page.tables:
                table_out: dict[str, Any] = {
                    "table_id": table.table_id,
                    "headers": table.headers,
                    "rows": [
                        {
                            "cells": [_serialize_cell(cell, forensic=forensic) for cell in row.cells],
                            "row_type": row.row_type.value,
                            "confidence": row.confidence,
                            "source_page": row.source_page,
                            "source_physical_id": row.source_physical_id,
                            "source_row_index": row.source_row_index,
                            **({"source_cell_refs": row.source_cell_refs} if forensic and row.source_cell_refs else {}),
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
                if (table.metadata or {}).get("raw_rows"):
                    table_out["raw_rows"] = table.metadata["raw_rows"]
                if forensic:
                    if table.evidence_ids:
                        table_out["evidence_ids"] = table.evidence_ids
                    if table.metadata:
                        table_out["metadata"] = table.metadata
                api_page["tables"].append(table_out)
        if page.texts:
            api_page["texts"] = [
                {
                    "content": text.content,
                    "level": text.level.value,
                    "confidence": text.confidence,
                    **({"bbox": text.bbox} if forensic and text.bbox else {}),
                    **({"evidence_ids": text.evidence_ids} if forensic and text.evidence_ids else {}),
                    **({"slm_entities": text.slm_entities} if getattr(text, "slm_entities", None) else {}),
                }
                for text in page.texts
            ]
        if page.key_values:
            api_page["key_values"] = [
                {
                    "key": item.key,
                    "value": item.value,
                    "confidence": item.confidence,
                    **({"bbox": item.bbox} if forensic and item.bbox else {}),
                    **({"evidence_ids": item.evidence_ids} if forensic and item.evidence_ids else {}),
                }
                for item in page.key_values
            ]
        api_pages.append(api_page)
    return api_pages


def _apply_page_projection(
    result: ParseResult,
    payload: dict[str, Any],
    *,
    mirror_level: str | None,
    include_text: bool | None,
) -> dict[str, Any]:
    from docmirror.models.mirror.domain_access import (
        raw_local_structure_evidence_from_domain_specific,
        raw_micro_grid_evidence_from_domain_specific,
    )
    from docmirror.models.mirror.vnext_page_projection import project_vnext_pages

    domain_specific = result.entities.domain_specific or {}
    raw_micro = raw_micro_grid_evidence_from_domain_specific(domain_specific)
    raw_local = raw_local_structure_evidence_from_domain_specific(domain_specific)
    scanned_ocr_pages, refs = _build_scanned_ocr_page_pool(raw_micro, raw_local)
    forensic = _profile(mirror_level) == "forensic"
    source_pages = {
        int(page.get("page_number") or 0): page
        for page in _build_api_pages(result, forensic=forensic)
        if int(page.get("page_number") or 0) > 0
    }
    mirror_pages = {
        int(page.get("page_number") or 0): page
        for page in payload.get("pages", [])
        if isinstance(page, dict) and int(page.get("page_number") or 0) > 0
    }
    merged_pages: list[dict[str, Any]] = []
    for page_num in sorted(set(mirror_pages) | set(source_pages)):
        base = dict(mirror_pages.get(page_num) or {"page_number": page_num})
        raw = source_pages.get(page_num) or {}
        for key in ("width", "height", "tables", "texts", "key_values"):
            if key in raw and (key not in base or key in {"texts", "key_values"} or (key == "tables" and forensic)):
                base[key] = raw[key]
        merged_pages.append(base)
    enriched_pages = project_vnext_pages(
        merged_pages,
        domain_specific=domain_specific,
        mirror_level="forensic" if forensic else "standard",
        scanned_ocr_pages=scanned_ocr_pages,
        include_text=include_text,
        document_type=str(result.entities.document_type or ""),
    )
    if enriched_pages:
        payload["pages"] = enriched_pages
    if forensic:
        if scanned_ocr_pages:
            payload["scanned_ocr_pages"] = scanned_ocr_pages
        local_evidence = _strip_redundant_structures(
            _strip_scanned_ocr_payload(raw_local, refs),
            payload.get("pages", []),
        )
        if local_evidence:
            payload["scanned_local_structure_evidence"] = local_evidence
        micro_evidence = _strip_scanned_ocr_payload(raw_micro, refs)
        if micro_evidence:
            payload["scanned_micro_grid_evidence"] = micro_evidence
        payload["source"] = _strip_inline_page_evidence_bundles(payload.get("source"))
        _strip_ocr_text_atoms(payload, include_text=include_text)
    return payload


def project_mirror(
    result: SealedParseResult,
    *,
    source_filename: str = "",
    mirror_level: str | None = None,
    include_text: bool | None = None,
) -> dict[str, Any]:
    """Project Mirror JSON from an isolated read view of the sealed SSOT."""
    if not isinstance(result, SealedParseResult):
        raise TypeError(f"project_mirror expects SealedParseResult; got {type(result).__name__}")
    from docmirror.models.mirror.core import MirrorCoreVNext, MirrorOptions, MirrorResult

    read_view = result.to_read_view()
    options = MirrorOptions(
        source_filename=source_filename or read_view.file_path,
        profile=_profile(mirror_level),
    )
    projected = MirrorCoreVNext().process(read_view, options=options)
    if isinstance(projected, MirrorResult):
        payload = projected.to_dict()
    elif isinstance(projected, dict):
        payload = projected
    else:
        return {"error": f"unexpected result type: {type(projected).__name__}"}
    return _apply_page_projection(
        read_view,
        payload,
        mirror_level=mirror_level or "standard",
        include_text=include_text,
    )


__all__ = ["project_mirror"]
