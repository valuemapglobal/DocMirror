# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Structural Signal Orchestration (SSO) — Mirror routing SSOT.

Replaces single-threshold section early exit with multi-hypothesis
competition + veto. Internal design reference: mirror layer redesign.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from docmirror.evidence.structure_provenance import (
    SSO_VERSION,
    PrimaryStructure,
    StructureProvenanceEnvelope,
)
from docmirror.layout.structure_signals import (
    PIPE_GRID_VETO_THRESHOLD,
    apply_scene_hint_prior,
    score_pipe_grid,
    score_prose,
    score_scan,
    score_section_headers,
    score_table_pdf,
)

TableExtractionMode = Literal["full", "skipped", "enrich_only"]

PRIMARY_TO_CONTENT_TYPE = {
    "section_led": "section_dominant",
    "table_led": "table_dominant",
    "scan_led": "scanned",
    "mixed": "mixed",
    "prose_led": "text_dominant",
    "unknown": "unknown",
}


@dataclass
class StructuralVerdict:
    primary: PrimaryStructure
    scores: dict[str, float]
    veto_applied: list[str]
    table_extraction: TableExtractionMode
    spe: StructureProvenanceEnvelope


def _pick_primary(scores: dict[str, float]) -> PrimaryStructure:
    mapping = {
        "H_section": "section_led",
        "H_pipe_grid": "table_led",
        "H_table_pdf": "table_led",
        "H_scan": "scan_led",
        "H_prose": "prose_led",
    }
    best_key = max(mapping, key=lambda k: scores.get(k, 0))
    best = scores.get(best_key, 0)
    if best < 0.15:
        if scores.get("H_scan", 0) >= 0.5:
            return "scan_led"
        if scores.get("H_table_pdf", 0) >= 0.3 and scores.get("H_pipe_grid", 0) >= 0.3:
            return "mixed"
        return "unknown"
    if (
        best_key in ("H_pipe_grid", "H_table_pdf")
        and abs(scores.get("H_pipe_grid", 0) - scores.get("H_table_pdf", 0)) < 0.1
    ):
        if scores.get("H_pipe_grid", 0) >= 0.5:
            return "table_led"
    return mapping[best_key]  # type: ignore[return-value]


def classify_structure(
    *,
    sample_text: str,
    scene_hint: str | None = None,
    table_pages: int = 0,
    sample_size: int = 1,
    scanned_pages: int = 0,
    has_text: bool = True,
    extraction_layer: str | None = None,
    layout_profile_id: str | None = None,
) -> StructuralVerdict:
    """Run SSO competitors and return verdict + SPE."""
    scores: dict[str, float] = {
        "H_section": score_section_headers(sample_text),
        "H_pipe_grid": score_pipe_grid(sample_text),
        "H_table_pdf": score_table_pdf(table_pages, sample_size),
        "H_scan": score_scan(scanned_pages, sample_size, has_text),
    }
    scores["H_prose"] = score_prose(
        scores["H_table_pdf"],
        scores["H_pipe_grid"],
        scores["H_section"],
    )
    scores = apply_scene_hint_prior(scores, scene_hint)

    veto_applied: list[str] = []
    if scores["H_pipe_grid"] >= PIPE_GRID_VETO_THRESHOLD and scores["H_section"] >= 0.5:
        scores["H_section"] *= 0.2
        veto_applied.append("H_pipe_grid_veto_section_monopoly")

    primary = _pick_primary(scores)

    if primary == "section_led" and scores["H_pipe_grid"] < 0.5:
        table_extraction: TableExtractionMode = "skipped"
    elif primary == "section_led" and scores["H_pipe_grid"] >= PIPE_GRID_VETO_THRESHOLD:
        primary = "table_led"
        table_extraction = "full"
        veto_applied.append("pipe_grid_promote_table_led")
    else:
        table_extraction = "full"

    skipped_reason = None
    if table_extraction == "skipped" and scores["H_pipe_grid"] >= PIPE_GRID_VETO_THRESHOLD:
        skipped_reason = "route_section_dominant_mismatch"
    elif table_extraction == "skipped":
        skipped_reason = "route_section_dominant"
    elif primary == "scan_led":
        skipped_reason = "scan_only"

    spe = StructureProvenanceEnvelope(
        primary=primary,
        competitors=scores,
        veto_applied=veto_applied,
        table_extraction=table_extraction,
        table_extraction_skipped_reason=skipped_reason,
        extraction_layer=extraction_layer,
        layout_profile_id=layout_profile_id,
        sso_version=SSO_VERSION,
    )

    return StructuralVerdict(
        primary=primary,
        scores=scores,
        veto_applied=veto_applied,
        table_extraction=table_extraction,
        spe=spe,
    )


def content_type_from_verdict(verdict: StructuralVerdict) -> str:
    """Map SSO primary structure to raw content_type."""
    return PRIMARY_TO_CONTENT_TYPE.get(verdict.primary, "unknown")


def score_page_morphology_from_bundles(
    bundles: list[dict[str, Any]] | None,
) -> dict[str, float]:
    """Derive H_field_grid / H_micro_grid from page evidence bundle detect candidates."""
    field_score = 0.0
    grid_score = 0.0
    for bundle in bundles or []:
        if not isinstance(bundle, dict):
            continue
        detect = bundle.get("region_detect") or {}
        for cand in detect.get("region_detect_candidates") or []:
            if not isinstance(cand, dict):
                continue
            score = float(cand.get("score") or 0.0)
            kind = str(cand.get("kind") or "")
            if kind == "field_grid":
                field_score = max(field_score, score)
            elif kind == "micro_grid":
                grid_score = max(grid_score, score)
        summary = bundle.get("morphology_summary") or {}
        if isinstance(summary, dict):
            if int(summary.get("S4") or 0) > 0:
                field_score = max(field_score, 0.6)
            if int(summary.get("S3") or 0) > 0:
                grid_score = max(grid_score, 0.6)
    return {"H_field_grid": field_score, "H_micro_grid": grid_score}


def enrich_competitors_with_page_morphology(
    competitors: dict[str, float],
    *,
    bundles: list[dict[str, Any]] | None = None,
) -> dict[str, float]:
    """Merge page-level morphology scores into SSO competitors (Design 20 Phase 4)."""
    out = dict(competitors)
    morph = score_page_morphology_from_bundles(bundles)
    for key, value in morph.items():
        if value > 0:
            out[key] = max(float(out.get(key) or 0.0), value)
    return out
