# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG oracle for Page-Centric Mirror (PCM) regions."""

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.report import GateReport
from docmirror.models.mirror.page_access import (
    get_page_canvas,
    iter_all_blocks,
    iter_all_regions,
    iter_page_blocks,
    iter_page_regions,
    resolve_block_ref,
)


def _doc(mirror_or_api: Any) -> dict[str, Any]:
    if hasattr(mirror_or_api, "to_api_dict"):
        api = mirror_or_api.to_api_dict(mirror_level="forensic", include_text=True)
        return ((api.get("data") or {}).get("document") or {}) if isinstance(api, dict) else {}
    if isinstance(mirror_or_api, dict):
        return (mirror_or_api.get("data") or {}).get("document") or {}
    return {}


def run_page_canvas_oracle(
    mirror_or_api: Any,
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "regression",
) -> GateReport:
    report = GateReport(case_id=case_id, track=track, tier=tier)
    doc = _doc(mirror_or_api)
    page = int(spec.get("page") or 0)
    if page:
        regions = list(iter_page_regions(doc, page))
    else:
        regions = list(iter_all_regions(doc))

    min_regions = int(spec.get("min_regions", 0) or 0)
    if min_regions:
        ok = len(regions) >= min_regions
        report.checks["page_canvas_min_regions"] = ok
        report.metrics["region_count"] = len(regions)
        if not ok:
            report.passed = False
            report.failures.append(f"region_count expected >= {min_regions}, got {len(regions)}")

    max_regions = spec.get("max_regions")
    if max_regions is not None:
        ok = len(regions) <= int(max_regions)
        report.checks["page_canvas_max_regions"] = ok
        report.metrics["region_count"] = len(regions)
        if not ok:
            report.passed = False
            report.failures.append(f"region_count expected <= {max_regions}, got {len(regions)}")

    required_kinds = list(spec.get("required_kinds") or [])
    if required_kinds:
        kinds = {r.get("kind") for r in regions}
        ok = all(kind in kinds for kind in required_kinds)
        report.checks["page_canvas_required_kinds"] = ok
        report.metrics["region_kinds"] = sorted(k for k in kinds if k)
        if not ok:
            report.passed = False
            report.failures.append(f"expected region kinds {required_kinds}, got {sorted(kinds)}")

    min_field_grid_cells = int(spec.get("min_field_grid_cells", 0) or 0)
    if min_field_grid_cells:
        cell_count = 0
        for region in regions:
            if region.get("kind") != "field_grid":
                continue
            structure = region.get("structure") or {}
            cell_count += len(structure.get("cells") or [])
        ok = cell_count >= min_field_grid_cells
        report.checks["page_canvas_min_field_grid_cells"] = ok
        report.metrics["field_grid_cell_count"] = cell_count
        if not ok:
            report.passed = False
            report.failures.append(f"field_grid cells expected >= {min_field_grid_cells}, got {cell_count}")

    if spec.get("require_flow_texts"):
        api_page = get_page_canvas(doc, page)
        flow = (api_page or {}).get("flow") or {}
        ok = bool(flow.get("texts"))
        report.checks["page_canvas_require_flow_texts"] = ok
        if not ok:
            report.passed = False
            report.failures.append("expected pages[n].flow.texts")

    min_tables = int(spec.get("min_tables", 0) or 0)
    if min_tables:
        if page:
            api_page = get_page_canvas(doc, page) or {}
            count = len(api_page.get("tables") or [])
        else:
            count = sum(len(p.get("tables") or []) for p in doc.get("pages") or [] if isinstance(p, dict))
        ok = count >= min_tables
        report.checks["page_canvas_min_tables"] = ok
        report.metrics["table_count"] = count
        if not ok:
            report.passed = False
            report.failures.append(f"table_count expected >= {min_tables}, got {count}")

    min_blocks = int(spec.get("min_blocks", 0) or 0)
    if min_blocks:
        if page:
            blocks = list(iter_page_blocks(doc, page))
        else:
            blocks = list(iter_all_blocks(doc))
        ok = len(blocks) >= min_blocks
        report.checks["page_canvas_min_blocks"] = ok
        report.metrics["block_count"] = len(blocks)
        if not ok:
            report.passed = False
            report.failures.append(f"block_count expected >= {min_blocks}, got {len(blocks)}")

    require_morphology = list(spec.get("require_morphology") or [])
    if require_morphology:
        if page:
            morphs = {b.get("morphology") for b in iter_page_blocks(doc, page)}
        else:
            morphs = {b.get("morphology") for b in iter_all_blocks(doc)}
        ok = all(m in morphs for m in require_morphology)
        report.checks["page_canvas_require_morphology"] = ok
        report.metrics["block_morphologies"] = sorted(m for m in morphs if m)
        if not ok:
            report.passed = False
            report.failures.append(f"expected block morphologies {require_morphology}, got {sorted(morphs)}")

    if spec.get("blocks_region_parity"):
        if page:
            blocks = list(iter_page_blocks(doc, page))
            regions = list(iter_page_regions(doc, page))
        else:
            blocks = list(iter_all_blocks(doc))
            regions = list(iter_all_regions(doc))
        region_refs = {f"region:{r.get('region_id')}" for r in regions if r.get("region_id")}
        block_region_refs = {b.get("ref") for b in blocks if str(b.get("ref", "")).startswith("region:")}
        ok = region_refs == block_region_refs and len(region_refs) == len(block_region_refs)
        report.checks["page_canvas_blocks_region_parity"] = ok
        report.metrics["region_ref_count"] = len(region_refs)
        report.metrics["block_region_ref_count"] = len(block_region_refs)
        if not ok:
            report.passed = False
            report.failures.append(
                f"blocks/regions parity failed: regions={sorted(region_refs)} blocks={sorted(block_region_refs)}"
            )

    if spec.get("require_block_ref_resolve"):
        if page:
            api_page = get_page_canvas(doc, page) or {}
            blocks = list(iter_page_blocks(doc, page))
        else:
            blocks = list(iter_all_blocks(doc))
            api_page = {}
        unresolved = []
        for block in blocks:
            ref = str(block.get("ref") or "")
            pnum = page or int(block.get("_page", 0) or 0)
            pg = get_page_canvas(doc, pnum) if pnum else api_page
            if pg and resolve_block_ref(pg, ref) is None:
                unresolved.append(ref)
        ok = not unresolved
        report.checks["page_canvas_block_ref_resolve"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"unresolved block refs: {unresolved}")

    return report
