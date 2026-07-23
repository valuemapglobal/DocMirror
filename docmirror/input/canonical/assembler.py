# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Assemble physical adapter facts directly into the ParseResult SSOT."""

from __future__ import annotations

from typing import Any

from docmirror.input.canonical.page_assembler import assemble_pages
from docmirror.models.entities.parse_result import (
    CanonicalEvidencePlane,
    ExtractionMethod,
    ParseResult,
    ParserInfo,
    ResultStatus,
)


def assemble_parse_result(
    page_layouts: list[Any] | tuple[Any, ...],
    metadata: dict[str, Any] | None,
    raw_text: str,
) -> ParseResult:
    """Create the canonical ParseResult directly from physical adapter facts."""
    meta = dict(metadata or {})
    pages = assemble_pages(page_layouts, meta)
    structure = meta.get("structure")
    if isinstance(structure, dict):
        structure = dict(structure)
        structure.setdefault("raw_full_text_length", len(raw_text or ""))
    try:
        extraction_method = ExtractionMethod(str(meta.get("extraction_method") or "digital"))
    except ValueError:
        extraction_method = ExtractionMethod.DIGITAL
    confidence = float(meta.get("overall_confidence") or 0.0)
    if confidence <= 0.0 and pages:
        confidence = sum(float(page.page_confidence or 0.0) for page in pages) / len(pages)
    result = ParseResult(
        status=(
            ResultStatus.PARTIAL
            if "native_table_evidence_not_reconstructed" in (meta.get("warnings") or [])
            else ResultStatus.SUCCESS
        ),
        pages=pages,
        raw_text=raw_text or "",
        confidence=max(0.0, min(1.0, confidence)),
        parser_info=ParserInfo(
            parser_name=str(meta.get("parser") or ""),
            elapsed_ms=float(meta.get("elapsed_ms") or 0.0),
            page_count=len(pages),
            extraction_method=extraction_method,
            ocr_engine=meta.get("ocr_engine"),
            table_engine=meta.get("table_engine"),
            overall_confidence=max(0.0, min(1.0, confidence)),
            warnings=[str(item) for item in meta.get("warnings", []) or []],
            structure=structure,
            options={
                key: meta.get(key)
                for key in (
                    "parse_policy",
                    "parse_policy_fingerprint",
                    "selected_pages",
                    "selected_source_pages",
                    "ocr_mode",
                    "page_split_mode",
                    "page_split_rotation",
                    "source_page_count",
                    "logical_page_count",
                    "page_decomposition",
                    "doc_type_hint",
                    "doc_type_hint_strength",
                    "ocr_correction_mode",
                    "ocr_correction_language",
                    "ocr_correction_country",
                    "ocr_correction_locale",
                    "ocr_correction_pack_ids",
                    "ocr_corrections",
                    "evidence_counts",
                    "native_table_candidate_count",
                )
            },
        ),
        sections=meta.get("sections", []),
        evidence_plane=CanonicalEvidencePlane.from_runtime(meta.get("_runtime_evidence_plane")),
    )

    from docmirror.topology.canonical_document_flow import build_canonical_document_flow

    result.document_flow = build_canonical_document_flow(result.pages)
    _attach_page_evidence(result, meta)

    _compose_canonical_tables(result, meta, list(page_layouts))
    attach_parse_policy(
        result,
        doc_type_hint=meta.get("doc_type_hint"),
        doc_type_hint_strength=meta.get("doc_type_hint_strength"),
        parse_policy=meta.get("parse_policy"),
        parse_policy_fingerprint=meta.get("parse_policy_fingerprint"),
    )
    _attach_scene_hint(result, meta)
    return result


def _attach_page_evidence(result: ParseResult, meta: dict[str, Any]) -> None:
    if not any(
        meta.get(key)
        for key in (
            "micro_grids",
            "page_evidence_bundles",
            "scanned_micro_grid_evidence",
            "scanned_local_structure_evidence",
        )
    ):
        return
    domain = dict(result.entities.domain_specific or {})
    if meta.get("micro_grids"):
        from docmirror.models.mirror.page_evidence_bundles import merge_micro_grid_structures_into_bundles

        merge_micro_grid_structures_into_bundles(domain, list(meta.get("micro_grids") or []))
    if meta.get("page_evidence_bundles"):
        domain["_page_evidence_bundles"] = list(meta["page_evidence_bundles"])
    elif meta.get("scanned_micro_grid_evidence") or meta.get("scanned_local_structure_evidence"):
        from docmirror.models.mirror.page_evidence_bundles import bundles_from_extractor_meta

        bundles = bundles_from_extractor_meta(
            scanned_micro_grid_evidence=list(meta.get("scanned_micro_grid_evidence") or []),
            scanned_local_structure_evidence=list(meta.get("scanned_local_structure_evidence") or []),
        )
        if bundles:
            domain["_page_evidence_bundles"] = bundles
    result.entities.domain_specific = domain


def attach_parse_policy(
    result: ParseResult,
    *,
    doc_type_hint: Any = None,
    doc_type_hint_strength: Any = None,
    parse_policy: Any = None,
    parse_policy_fingerprint: Any = None,
) -> ParseResult:
    """Attach request policy at the canonical boundary for every adapter.

    Backends are allowed to emit evidence and basic facts only; they do not own
    request policy propagation. A ``force`` hint is therefore applied here,
    before generic classification and plugin recognition, so adapter choice can
    never change the fact-affecting policy semantics.
    """
    domain = dict(result.entities.domain_specific or {})
    hint = str(doc_type_hint or "").strip()
    strength = str(doc_type_hint_strength or "prefer").strip().lower()
    if hint:
        domain["user_doc_type_hint"] = hint
        domain["user_doc_type_hint_strength"] = strength
        domain["doc_type_hint_source"] = "user"
        if strength == "force" and result.entities.document_type != hint:
            old_type = result.entities.document_type
            result.entities.document_type = hint
            result.record_mutation(
                middleware_name="ParsePolicy",
                target_block_id="document",
                field_changed="entities.document_type",
                old_value=old_type,
                new_value=hint,
                confidence=1.0,
                reason="forced request document type",
            )
    if parse_policy is not None:
        result.parser_info.options["parse_policy"] = parse_policy
    if parse_policy_fingerprint:
        result.parser_info.options["parse_policy_fingerprint"] = str(parse_policy_fingerprint)
    if hint:
        result.parser_info.options["doc_type_hint"] = hint
        result.parser_info.options["doc_type_hint_strength"] = strength
    result.entities.domain_specific = domain
    return result


def _attach_scene_hint(result: ParseResult, meta: dict[str, Any]) -> None:
    domain = dict(result.entities.domain_specific or {})
    scene = meta.get("document_scene")
    if scene and scene not in {"unknown", "generic"}:
        domain["extractor_scene_hint"] = scene
        domain["extractor_scene_confidence"] = float(meta.get("scene_confidence") or 0.0)
    result.entities.domain_specific = domain


def _compose_canonical_tables(
    result: ParseResult,
    metadata: dict[str, Any],
    page_layouts: list[Any],
) -> None:
    """Compose the canonical logical-table view inside the fact pipeline."""
    from docmirror.tables.compose.composer import TableComposer, build_table_operations

    scanned = [
        table
        for page in result.pages
        for table in page.tables
        if str((table.metadata or {}).get("source") or "") == "scanned_bordered_table_reconstructor"
        or str(table.extraction_layer or "") == "scanned_image_line_grid"
    ]
    if scanned:
        logical = TableComposer.clone_physical_from_page_content(result.pages)
        result.logical_tables = logical
        result.table_operations = build_table_operations(logical)
        result.parser_info.structure = {
            **dict(result.parser_info.structure or {}),
            "logical_table_count": len(logical),
            "physical_table_count": len(scanned),
            "dual_view": True,
            "logical_table_policy": "physical_1to1_scanned_grid",
        }
        return

    from docmirror.tables.compose.export_pipeline import compose_logical_export_from_layouts

    pre = metadata.get("pre_analysis") if isinstance(metadata.get("pre_analysis"), dict) else {}
    exported = compose_logical_export_from_layouts(
        page_layouts,
        layout_profile_id=metadata.get("layout_profile_id"),
        full_text=result.full_text or "",
        scene_hint=pre.get("scene_hint"),
        content_type=pre.get("content_type"),
    )
    logical = [*exported.export_logical, *exported.skipped_logical]
    if logical:
        result.logical_tables = logical
        result.table_operations = build_table_operations(exported.export_logical or logical)
    if exported.quarantined_physical:
        metadata["quarantined_tables"] = exported.quarantined_physical
    if exported.skipped_payload:
        metadata["quarantined_logical_tables"] = exported.skipped_payload
    if exported.ltqg_summary is not None and exported.ltqg_summary.enabled:
        metadata["ltqg"] = exported.ltqg_summary.to_dict()
    from docmirror.quality.mirror_ltqg import attach_mirror_ltqg

    attach_mirror_ltqg(result, metadata)


__all__ = ["assemble_parse_result", "attach_parse_policy"]
