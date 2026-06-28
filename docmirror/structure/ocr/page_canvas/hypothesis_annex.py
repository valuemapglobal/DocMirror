# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hypothesis annex for unmaterialized detect candidates (Design 20 Phase 5 / EFMP C-2)."""

from __future__ import annotations

from typing import Any


def build_hypothesis_annex_for_page(
    evidence_bundle: dict[str, Any] | None,
    *,
    page: int,
) -> list[dict[str, Any]]:
    if not evidence_bundle or int(evidence_bundle.get("page") or 0) != page:
        return []
    audit = evidence_bundle.get("audit") or {}
    detect_only = audit.get("detect_only") or []
    annex: list[dict[str, Any]] = []
    for item in detect_only:
        if not isinstance(item, dict):
            continue
        annex.append(
            {
                "hypothesis_kind": "region_detect_candidate",
                "page": page,
                "candidate_id": item.get("candidate_id"),
                "kind": item.get("kind"),
                "score": item.get("score"),
                "status": "unselected",
                "reason": item.get("materialize_skipped_reason") or "detect_only",
            }
        )
    annex.extend(_quarantine_cells_from_bundle(evidence_bundle, page=page))
    return annex


def _quarantine_cells_from_bundle(bundle: dict[str, Any], *, page: int) -> list[dict[str, Any]]:
    """Collect quarantined field_grid cells into hypothesis annex (EFMP C-2)."""
    annex: list[dict[str, Any]] = []
    local = bundle.get("local_structure_evidence")
    if not isinstance(local, dict):
        return annex
    for structure in local.get("structures") or []:
        if not isinstance(structure, dict):
            continue
        structure_id = str(structure.get("structure_id") or "")
        for cell in structure.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            if cell.get("geometry_status") != "quarantined" and not cell.get("quarantine_reason"):
                continue
            annex.append(
                {
                    "hypothesis_kind": "quarantined_cell",
                    "page": page,
                    "structure_id": structure_id,
                    "cell_id": cell.get("cell_id"),
                    "label_text": cell.get("label_text"),
                    "text": cell.get("text"),
                    "status": "quarantined",
                    "reason": cell.get("quarantine_reason") or "geometry_status",
                }
            )
    return annex


def build_document_hypothesis_annex(
    domain_specific: dict[str, Any] | None,
    *,
    page_regions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    ds = domain_specific or {}
    annex: list[dict[str, Any]] = []
    for bundle in ds.get("_page_evidence_bundles") or []:
        if not isinstance(bundle, dict):
            continue
        page = int(bundle.get("page") or 0)
        annex.extend(build_hypothesis_annex_for_page(bundle, page=page))
    if page_regions:
        seen = {
            (a.get("structure_id"), a.get("cell_id")) for a in annex if a.get("hypothesis_kind") == "quarantined_cell"
        }
        for region in page_regions:
            if not isinstance(region, dict):
                continue
            page = int(region.get("page") or region.get("structure", {}).get("page") or 0)
            structure = region.get("structure") or {}
            structure_id = str(structure.get("structure_id") or region.get("region_id") or "")
            for cell in structure.get("cells") or []:
                if not isinstance(cell, dict):
                    continue
                if cell.get("geometry_status") != "quarantined" and not cell.get("quarantine_reason"):
                    continue
                key = (structure_id, cell.get("cell_id"))
                if key in seen:
                    continue
                annex.append(
                    {
                        "hypothesis_kind": "quarantined_cell",
                        "page": page,
                        "structure_id": structure_id,
                        "cell_id": cell.get("cell_id"),
                        "label_text": cell.get("label_text"),
                        "text": cell.get("text"),
                        "status": "quarantined",
                        "reason": cell.get("quarantine_reason") or "geometry_status",
                    }
                )
    return annex
