# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Structure Provenance Envelope (SPE) — Mirror audit metadata for table routing.

Written to ``ParseResult.parser_info.structure`` (ADR-M13-02).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from docmirror.core.table.structure_detect import PipeGridSignal, detect_pipe_grid_in_text

SSO_VERSION = "1.0"

PrimaryStructure = Literal[
    "section_led",
    "table_led",
    "scan_led",
    "mixed",
    "prose_led",
    "unknown",
]

TableExtractionMode = Literal["full", "skipped", "enrich_only"]

CONTENT_TYPE_TO_PRIMARY: dict[str, PrimaryStructure] = {
    "section_dominant": "section_led",
    "table_dominant": "table_led",
    "scanned": "scan_led",
    "mixed": "mixed",
    "text_dominant": "prose_led",
    "unknown": "unknown",
}


@dataclass
class StructureProvenanceEnvelope:
    primary: PrimaryStructure
    competitors: dict[str, float]
    veto_applied: list[str] = field(default_factory=list)
    table_extraction: TableExtractionMode = "full"
    table_extraction_skipped_reason: str | None = None
    extraction_layer: str | None = None
    layout_profile_id: str | None = None
    sso_version: str = SSO_VERSION
    logical_table_count: int | None = None
    physical_table_count: int | None = None
    dual_view: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_skipped_reason(
    *,
    content_type: str,
    pipe_signal: PipeGridSignal,
    table_count: int,
) -> str | None:
    """Derive MX-3 skip reason code."""
    if table_count > 0:
        return None
    if content_type == "section_dominant":
        if pipe_signal.confidence >= 0.85:
            return "route_section_dominant_mismatch"
        return "route_section_dominant"
    if content_type == "scanned":
        return "scan_only"
    if pipe_signal.confidence < 0.3:
        return "no_tabular_signal"
    if content_type in ("table_dominant", "mixed"):
        return "extraction_failed"
    return "no_tabular_signal"


def build_structure_provenance(
    *,
    content_type: str,
    sample_text: str,
    table_count: int = 0,
    extraction_layer: str | None = None,
    layout_profile_id: str | None = None,
    competitors: dict[str, float] | None = None,
    veto_applied: list[str] | None = None,
    table_extraction: TableExtractionMode | None = None,
) -> StructureProvenanceEnvelope:
    """Build SPE from pre-analysis + SDU (Phase 0/1 shared)."""
    pipe_signal = detect_pipe_grid_in_text(sample_text)
    primary = CONTENT_TYPE_TO_PRIMARY.get(content_type, "unknown")

    comp = dict(competitors or {})
    if "H_pipe_grid" not in comp:
        comp["H_pipe_grid"] = pipe_signal.confidence
    if "H_section" not in comp:
        comp["H_section"] = 0.0

    if table_extraction is None:
        if content_type == "section_dominant":
            table_extraction = "skipped"
        else:
            table_extraction = "full"

    reason = None
    if table_extraction == "enrich_only":
        reason = None
    else:
        reason = build_skipped_reason(
            content_type=content_type,
            pipe_signal=pipe_signal,
            table_count=table_count,
        )

    return StructureProvenanceEnvelope(
        primary=primary,
        competitors=comp,
        veto_applied=list(veto_applied or []),
        table_extraction=table_extraction,
        table_extraction_skipped_reason=reason,
        extraction_layer=extraction_layer,
        layout_profile_id=layout_profile_id,
    )


def apply_pipe_enrich_spe(spe: dict[str, Any]) -> dict[str, Any]:
    """Mark SPE after SectionDrivenStrategy embedded pipe grid enrich (Phase 3)."""
    out = dict(spe)
    out["table_extraction"] = "enrich_only"
    out["table_extraction_skipped_reason"] = None
    if out.get("primary") not in ("section_led", "mixed"):
        out["primary"] = "section_led"
    return out


def apply_logical_tables_spe(
    spe: dict[str, Any],
    *,
    logical_table_count: int | None = None,
    physical_table_count: int | None = None,
    dual_view: bool | None = None,
    ltqg_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """M11: attach dual-view / logical compose stats after extraction."""
    out = dict(spe)
    if logical_table_count is not None:
        out["logical_table_count"] = logical_table_count
    if physical_table_count is not None:
        out["physical_table_count"] = physical_table_count
    if dual_view is not None:
        out["dual_view"] = dual_view
    if ltqg_summary:
        out["ltqg_enabled"] = bool(ltqg_summary.get("enabled"))
        if ltqg_summary.get("enabled"):
            out["ltqg_expected_data_rows"] = int(ltqg_summary.get("expected_data_rows") or 0)
            out["ltqg_passed_tables"] = int(ltqg_summary.get("passed_tables") or 0)
            out["ltqg_skipped_tables"] = int(ltqg_summary.get("skipped_tables") or 0)
            legacy = int(ltqg_summary.get("legacy_max_rows") or 0)
            if legacy:
                out["ltqg_legacy_max_rows"] = legacy
            skipped_ids = ltqg_summary.get("skipped_logical_ids")
            if skipped_ids:
                out["ltqg_skipped_logical_ids"] = list(skipped_ids)
            export_n = ltqg_summary.get("export_logical_tables")
            if export_n is not None:
                out["ltqg_export_logical_tables"] = int(export_n)
    return out


def apply_page_morphology_spe(
    spe: dict[str, Any],
    *,
    pages: list[dict[str, Any]] | None = None,
    domain_specific: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach page-level morphology stats to SPE (Design 20 Phase 4)."""
    from docmirror.core.analyze.structural_classifier import (
        enrich_competitors_with_page_morphology,
        score_page_morphology_from_bundles,
    )
    from docmirror.core.ocr.page_canvas.block_index import document_morphology_stats

    out = dict(spe)
    page_list = pages or []
    stats = document_morphology_stats(page_list)
    if stats:
        out["page_morphology_stats"] = stats
        out["H_field_grid"] = float(stats.get("S4", 0))
        out["H_micro_grid"] = float(stats.get("S3", 0))
    bundles = (domain_specific or {}).get("_page_evidence_bundles") or []
    competitors = dict(out.get("competitors") or {})
    if bundles:
        out["competitors"] = enrich_competitors_with_page_morphology(competitors, bundles=bundles)
        morph = score_page_morphology_from_bundles(bundles)
        if morph.get("H_field_grid", 0) > 0:
            out["H_field_grid"] = max(float(out.get("H_field_grid") or 0), morph["H_field_grid"])
        if morph.get("H_micro_grid", 0) > 0:
            out["H_micro_grid"] = max(float(out.get("H_micro_grid") or 0), morph["H_micro_grid"])
    per_page: list[dict[str, Any]] = []
    for page in page_list:
        if not isinstance(page, dict):
            continue
        summary = page.get("morphology_summary")
        if summary:
            per_page.append(
                {
                    "page": int(page.get("page_number") or 0),
                    "morphology_summary": dict(summary),
                    "block_count": len(page.get("blocks") or []),
                    "region_count": len(page.get("regions") or []),
                }
            )
    if per_page:
        out["page_morphology_detail"] = per_page
    return out
