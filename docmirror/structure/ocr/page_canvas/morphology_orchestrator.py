# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Morphology Orchestrator (MO) — unified detect → materialize gate (Design 20 Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from docmirror.structure.ocr.page_canvas.block_index import pcm_mo_enabled
from docmirror.structure.ocr.page_canvas.models import PageBlock, PageFlow, PageRegion


@dataclass
class MorphologyOrchestratorResult:
    regions: list[PageRegion] = field(default_factory=list)
    blocks: list[PageBlock] = field(default_factory=list)
    morphology_summary: dict[str, int] = field(default_factory=dict)
    reading_order: list[str] = field(default_factory=list)
    reading_order_v1: list[str] = field(default_factory=list)
    flow: PageFlow | None = None
    audit: dict[str, Any] = field(default_factory=dict)


def _content_type_prior(content_type: str | None) -> str:
    ct = str(content_type or "").lower()
    if "table" in ct:
        return "table_led"
    if "section" in ct:
        return "section_led"
    if "scan" in ct:
        return "scan_led"
    if "text" in ct or "prose" in ct:
        return "prose_led"
    return "mixed"


def _materialized_region_ids(regions: list[PageRegion]) -> set[str]:
    return {r.region_id for r in regions}


def _detect_only_candidates(
    bundle: dict[str, Any],
    *,
    materialized_ids: set[str],
) -> list[dict[str, Any]]:
    detect = bundle.get("region_detect") or {}
    candidates = detect.get("region_detect_candidates") or []
    detect_only: list[dict[str, Any]] = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        cand_id = str(cand.get("candidate_id") or "")
        bbox = cand.get("bbox")
        matched = False
        if isinstance(bbox, list) and len(bbox) == 4:
            for region_id in materialized_ids:
                if cand_id and cand_id in region_id:
                    matched = True
                    break
        if not matched:
            detect_only.append(
                {
                    "candidate_id": cand_id,
                    "kind": cand.get("kind"),
                    "score": cand.get("score"),
                    "reason_codes": list(cand.get("reason_codes") or []),
                    "materialize_skipped_reason": "not_materialized",
                }
            )
    return detect_only


def _should_skip_field_materialize(*, content_type: str | None, page_has_tables: bool) -> bool:
    """SPE table_led pages with tables must not FGR-materialize (Design 20 §2.2.1)."""
    if not pcm_mo_enabled():
        return False
    prior = _content_type_prior(content_type)
    if prior == "table_led" and page_has_tables:
        return True
    return False


def orchestrate_page_morphology(
    page_number: int,
    *,
    regions: list[PageRegion],
    flow_texts: list[dict[str, Any]],
    flow_key_values: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    evidence_bundle: dict[str, Any] | None = None,
    content_type: str | None = None,
    document_type: str | None = None,
) -> MorphologyOrchestratorResult:
    """Build UBI blocks and reconcile detect candidates against materialized regions."""
    from docmirror.structure.ocr.page_canvas.block_index import (
        build_page_blocks,
        reading_order_v1_from_blocks,
    )
    from docmirror.structure.ocr.page_canvas.flow_filter import filter_flow_texts_not_in_regions
    from docmirror.structure.ocr.structure_project import assign_schema_hints_to_regions

    audit: dict[str, Any] = {}
    active_regions = list(regions)
    if _should_skip_field_materialize(content_type=content_type, page_has_tables=bool(tables)):
        audit["mo_skip_field_materialize"] = "table_led_with_tables"
        active_regions = [r for r in active_regions if r.morphology != "S4" or r.kind == "micro_grid"]

    assign_schema_hints_to_regions(active_regions, document_type=document_type)

    filtered_texts = filter_flow_texts_not_in_regions(flow_texts, active_regions)
    blocks, summary, reading_order = build_page_blocks(
        page_number,
        regions=active_regions,
        flow_texts=filtered_texts,
        flow_key_values=flow_key_values,
        tables=tables,
        document_type=document_type,
    )

    if evidence_bundle:
        detect_only = _detect_only_candidates(
            evidence_bundle,
            materialized_ids=_materialized_region_ids(active_regions),
        )
        if detect_only:
            audit["detect_only"] = detect_only

    return MorphologyOrchestratorResult(
        regions=active_regions,
        blocks=blocks,
        morphology_summary=summary,
        reading_order=reading_order,
        reading_order_v1=reading_order_v1_from_blocks(blocks),
        flow=PageFlow(texts=filtered_texts, key_values=list(flow_key_values)),
        audit=audit,
    )


def merge_orchestrator_audit_into_bundle(bundle: dict[str, Any], audit: dict[str, Any]) -> None:
    if not audit:
        return
    existing = bundle.setdefault("audit", {})
    if not isinstance(existing, dict):
        bundle["audit"] = dict(audit)
        return
    for key, value in audit.items():
        existing[key] = value


def materialized_region_ids_from_bundle(bundle: dict[str, Any]) -> set[str]:
    """Map persisted L1 structures in a page bundle to PCM region ids."""
    ids: set[str] = set()
    for grid in bundle.get("micro_grid_structures") or []:
        if not isinstance(grid, dict):
            continue
        grid_id = str(grid.get("grid_id") or "")
        if grid_id.startswith("mg_"):
            ids.add(f"rg_{grid_id[3:]}")
    local = bundle.get("local_structure_evidence")
    if isinstance(local, dict):
        for structure in local.get("structures") or []:
            if not isinstance(structure, dict):
                continue
            structure_id = str(structure.get("structure_id") or "")
            if structure_id.startswith("ls_"):
                ids.add(f"rg_{structure_id[3:]}")
    return ids


def write_detect_audit_to_bundle(bundle: dict[str, Any]) -> None:
    """Record detect-only candidates on bundle audit (parse-time MO hook)."""
    if not isinstance(bundle, dict):
        return
    materialized = materialized_region_ids_from_bundle(bundle)
    detect_only = _detect_only_candidates(bundle, materialized_ids=materialized)
    if detect_only:
        merge_orchestrator_audit_into_bundle(bundle, {"detect_only": detect_only})
