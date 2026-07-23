# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG oracle for vNext page topology regions."""

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.mirror_input import mirror_api
from docmirror.eval.tqg.report import GateReport
from docmirror.models.mirror.vnext_access import (
    get_page,
    iter_blocks,
    iter_regions,
    pages,
    resolve_ref,
)


def _doc(mirror_or_api: Any) -> dict[str, Any]:
    api = mirror_api(mirror_or_api)
    if api.get("pages"):
        return api
    if isinstance(mirror_or_api, dict):
        if mirror_or_api.get("pages"):
            return mirror_or_api
        if isinstance(mirror_or_api.get("document"), dict) and mirror_or_api["document"].get("pages"):
            return mirror_or_api["document"]
        return (mirror_or_api.get("data") or {}).get("document") or {}
    return {}


def run_vnext_page_topology_oracle(
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
        regions = list(iter_regions(doc, page))
    else:
        regions = list(iter_regions(doc))

    min_regions = int(spec.get("min_regions", 0) or 0)
    if min_regions:
        ok = len(regions) >= min_regions
        report.checks["vnext_page_topology_min_regions"] = ok
        report.metrics["region_count"] = len(regions)
        if not ok:
            report.passed = False
            report.failures.append(f"region_count expected >= {min_regions}, got {len(regions)}")

    max_regions = spec.get("max_regions")
    if max_regions is not None:
        ok = len(regions) <= int(max_regions)
        report.checks["vnext_page_topology_max_regions"] = ok
        report.metrics["region_count"] = len(regions)
        if not ok:
            report.passed = False
            report.failures.append(f"region_count expected <= {max_regions}, got {len(regions)}")

    required_kinds = list(spec.get("required_kinds") or [])
    if required_kinds:
        kinds = {r.get("kind") for r in regions}
        ok = all(kind in kinds for kind in required_kinds)
        report.checks["vnext_page_topology_required_kinds"] = ok
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
        report.checks["vnext_page_topology_min_field_grid_cells"] = ok
        report.metrics["field_grid_cell_count"] = cell_count
        if not ok:
            report.passed = False
            report.failures.append(f"field_grid cells expected >= {min_field_grid_cells}, got {cell_count}")

    if spec.get("require_flow_texts"):
        api_page = get_page(doc, page)
        flow = (api_page or {}).get("flow") or {}
        ok = bool(flow.get("texts"))
        report.checks["vnext_page_topology_require_flow_texts"] = ok
        if not ok:
            report.passed = False
            report.failures.append("expected pages[n].flow.texts")

    min_tables = int(spec.get("min_tables", 0) or 0)
    if min_tables:
        if page:
            api_page = get_page(doc, page) or {}
            count = len(api_page.get("tables") or [])
        else:
            count = sum(len(p.get("tables") or []) for p in pages(doc) if isinstance(p, dict))
        ok = count >= min_tables
        report.checks["vnext_page_topology_min_tables"] = ok
        report.metrics["table_count"] = count
        if not ok:
            report.passed = False
            report.failures.append(f"table_count expected >= {min_tables}, got {count}")

    min_blocks = int(spec.get("min_blocks", 0) or 0)
    if min_blocks:
        if page:
            blocks = list(iter_blocks(doc, page))
        else:
            blocks = list(iter_blocks(doc))
        ok = len(blocks) >= min_blocks
        report.checks["vnext_page_topology_min_blocks"] = ok
        report.metrics["block_count"] = len(blocks)
        if not ok:
            report.passed = False
            report.failures.append(f"block_count expected >= {min_blocks}, got {len(blocks)}")

    require_morphology = list(spec.get("require_morphology") or [])
    if require_morphology:
        if page:
            morphs = {b.get("morphology") for b in iter_blocks(doc, page)}
        else:
            morphs = {b.get("morphology") for b in iter_blocks(doc)}
        ok = all(m in morphs for m in require_morphology)
        report.checks["vnext_page_topology_require_morphology"] = ok
        report.metrics["block_morphologies"] = sorted(m for m in morphs if m)
        if not ok:
            report.passed = False
            report.failures.append(f"expected block morphologies {require_morphology}, got {sorted(morphs)}")

    if spec.get("blocks_region_parity"):
        if page:
            blocks = list(iter_blocks(doc, page))
            regions = list(iter_regions(doc, page))
        else:
            blocks = list(iter_blocks(doc))
            regions = list(iter_regions(doc))
        region_refs = {f"region:{r.get('region_id')}" for r in regions if r.get("region_id")}
        block_region_refs = {b.get("ref") for b in blocks if str(b.get("ref", "")).startswith("region:")}
        ok = region_refs == block_region_refs and len(region_refs) == len(block_region_refs)
        report.checks["vnext_page_topology_blocks_region_parity"] = ok
        report.metrics["region_ref_count"] = len(region_refs)
        report.metrics["block_region_ref_count"] = len(block_region_refs)
        if not ok:
            report.passed = False
            report.failures.append(
                f"blocks/regions parity failed: regions={sorted(region_refs)} blocks={sorted(block_region_refs)}"
            )

    if spec.get("require_block_ref_resolve"):
        if page:
            blocks = list(iter_blocks(doc, page))
        else:
            blocks = list(iter_blocks(doc))
        unresolved = []
        for block in blocks:
            ref = str(block.get("ref") or "")
            pnum = page or int(block.get("_page", 0) or 0)
            if pnum and resolve_ref(doc, pnum, ref) is None:
                unresolved.append(ref)
        ok = not unresolved
        report.checks["vnext_page_topology_block_ref_resolve"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"unresolved block refs: {unresolved}")

    return report
