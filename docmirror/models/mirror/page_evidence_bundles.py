# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""vNext page evidence bundle helpers."""

from __future__ import annotations

from typing import Any


def build_page_evidence_bundles(domain_specific: dict[str, Any] | None) -> list[dict[str, Any]]:
    ds = domain_specific or {}
    existing = ds.get("_page_evidence_bundles")
    if not isinstance(existing, list):
        return []
    return [dict(item) for item in existing if isinstance(item, dict)]


def bundles_from_extractor_meta(
    *,
    scanned_micro_grid_evidence: list[dict[str, Any]] | None = None,
    scanned_local_structure_evidence: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    by_page: dict[int, dict[str, Any]] = {}
    for evidence in scanned_micro_grid_evidence or []:
        _merge_evidence_into_bundle(by_page, evidence, "micro_grid_evidence")
    for evidence in scanned_local_structure_evidence or []:
        _merge_evidence_into_bundle(by_page, evidence, "local_structure_evidence")
    return [by_page[page] for page in sorted(by_page)]


def upsert_page_evidence_bundle(
    host: Any,
    *,
    page: int,
    page_width: float | None = None,
    page_height: float | None = None,
    micro_grid_evidence: dict[str, Any] | None = None,
    local_structure_evidence: dict[str, Any] | None = None,
    region_detect: dict[str, Any] | None = None,
    source: str = "scanned_page_ocr",
) -> None:
    if page <= 0:
        return
    if not hasattr(host, "_page_evidence_bundles"):
        host._page_evidence_bundles = []
    bundles: list[dict[str, Any]] = host._page_evidence_bundles
    bundle = next((item for item in bundles if int(item.get("page") or 0) == page), None)
    if bundle is None:
        bundle = {"page": page}
        bundles.append(bundle)
    if page_width is not None:
        bundle.setdefault("page_width", page_width)
    if page_height is not None:
        bundle.setdefault("page_height", page_height)
    bundle.setdefault("source", source)
    if micro_grid_evidence is not None:
        bundle["micro_grid_evidence"] = dict(micro_grid_evidence)
    if local_structure_evidence is not None:
        bundle["local_structure_evidence"] = dict(local_structure_evidence)
    if region_detect is not None:
        bundle["region_detect"] = dict(region_detect)


def attach_page_evidence_bundles(domain_specific: dict[str, Any]) -> dict[str, Any]:
    bundles = build_page_evidence_bundles(domain_specific)
    if bundles:
        domain_specific["_page_evidence_bundles"] = bundles
    return domain_specific


def page_evidence_bundle(
    page: int,
    *,
    page_width: float | int | None = None,
    page_height: float | int | None = None,
    micro_grid_evidence: dict[str, Any] | None = None,
    local_structure_evidence: dict[str, Any] | None = None,
    source: str = "scanned_page_ocr",
) -> dict[str, Any]:
    bundle: dict[str, Any] = {"page": page, "source": source}
    if page_width is not None:
        bundle["page_width"] = page_width
    if page_height is not None:
        bundle["page_height"] = page_height
    if micro_grid_evidence is not None:
        bundle["micro_grid_evidence"] = dict(micro_grid_evidence)
    if local_structure_evidence is not None:
        bundle["local_structure_evidence"] = dict(local_structure_evidence)
    return bundle


def domain_specific_with_page_bundles(*bundles: dict[str, Any], **extra: Any) -> dict[str, Any]:
    out = dict(extra)
    if bundles:
        out["_page_evidence_bundles"] = [dict(bundle) for bundle in bundles if isinstance(bundle, dict)]
    return out


def merge_micro_grid_structures_into_bundles(domain_specific: dict[str, Any], grids: list[dict[str, Any]]) -> None:
    if not grids:
        return
    by_page: dict[int, dict[str, Any]] = {}
    for bundle in domain_specific.get("_page_evidence_bundles") or []:
        if isinstance(bundle, dict):
            page_num = int(bundle.get("page") or 0)
            if page_num > 0:
                by_page[page_num] = bundle
    for grid in grids:
        if not isinstance(grid, dict):
            continue
        page_num = int(grid.get("page") or 0)
        if page_num <= 0:
            continue
        bundle = by_page.get(page_num)
        if bundle is None:
            bundle = {"page": page_num}
            domain_specific.setdefault("_page_evidence_bundles", []).append(bundle)
            by_page[page_num] = bundle
        structures: list[dict[str, Any]] = list(bundle.get("micro_grid_structures") or [])
        grid_id = str(grid.get("grid_id") or "")
        replaced = False
        for idx, existing in enumerate(structures):
            if str(existing.get("grid_id") or "") == grid_id and grid_id:
                structures[idx] = dict(grid)
                replaced = True
                break
        if not replaced:
            structures.append(dict(grid))
        bundle["micro_grid_structures"] = structures


def micro_grid_structures_from_bundles(domain_specific: dict[str, Any] | None) -> list[dict[str, Any]]:
    ds = domain_specific or {}
    out: list[dict[str, Any]] = []
    for bundle in ds.get("_page_evidence_bundles") or []:
        if not isinstance(bundle, dict):
            continue
        for grid in bundle.get("micro_grid_structures") or []:
            if isinstance(grid, dict):
                out.append(dict(grid))
    return out


def bundle_evidence_items(domain_specific: dict[str, Any] | None, *, bundle_key: str) -> list[dict[str, Any]]:
    ds = domain_specific or {}
    out: list[dict[str, Any]] = []
    for bundle in ds.get("_page_evidence_bundles") or []:
        if not isinstance(bundle, dict):
            continue
        evidence = bundle.get(bundle_key)
        if isinstance(evidence, dict):
            out.append(dict(evidence))
    return out


def micro_grid_structures_by_page(domain_specific: dict[str, Any] | None) -> dict[int, list[dict[str, Any]]]:
    by_page: dict[int, list[dict[str, Any]]] = {}
    for grid in micro_grid_structures_from_bundles(domain_specific):
        page_num = int(grid.get("page") or 0)
        if page_num > 0:
            by_page.setdefault(page_num, []).append(dict(grid))
    return by_page


def micro_grid_evidence_needing_reconstruction(domain_specific: dict[str, Any] | None) -> list[dict[str, Any]]:
    structured_pages = set(micro_grid_structures_by_page(domain_specific))
    return [
        evidence
        for evidence in bundle_evidence_items(domain_specific, bundle_key="micro_grid_evidence")
        if evidence.get("lines") and int(evidence.get("page") or 0) not in structured_pages
    ]


def merge_micro_grid_structures_into_host(host: Any, grids: list[dict[str, Any]]) -> None:
    if not grids:
        return
    if not hasattr(host, "_page_evidence_bundles"):
        host._page_evidence_bundles = []
    merge_micro_grid_structures_into_bundles({"_page_evidence_bundles": host._page_evidence_bundles}, grids)


def materialize_micro_grids_from_bundles(
    domain_specific: dict[str, Any],
    *,
    page_image_resolver: Any | None = None,
    enable_cell_ocr: bool = False,
) -> list[dict[str, Any]]:
    from docmirror.ocr.micro_grid.materialize import extract_micro_grid_structures

    materialized: list[dict[str, Any]] = []
    for evidence in micro_grid_evidence_needing_reconstruction(domain_specific):
        grids = extract_micro_grid_structures(
            evidence.get("lines") or [],
            tokens=evidence.get("tokens") or [],
            page=int(evidence.get("page") or 0),
            page_width=evidence.get("page_width"),
            page_height=evidence.get("page_height"),
            page_image_resolver=page_image_resolver,
            enable_cell_ocr=enable_cell_ocr,
        )
        if grids:
            merge_micro_grid_structures_into_bundles(domain_specific, grids)
            materialized.extend(grids)
    return materialized


def local_structure_evidence_pages_from_bundles(domain_specific: dict[str, Any] | None) -> list[dict[str, Any]]:
    ds = domain_specific or {}
    out: list[dict[str, Any]] = []
    for bundle in ds.get("_page_evidence_bundles") or []:
        if not isinstance(bundle, dict):
            continue
        local = bundle.get("local_structure_evidence")
        if not isinstance(local, dict):
            continue
        page_num = int(local.get("page") or bundle.get("page") or 0)
        structures = local.get("structures") or []
        if page_num and structures:
            out.append({"page": page_num, "structures": list(structures)})
    return out


def _merge_evidence_into_bundle(by_page: dict[int, dict[str, Any]], evidence: Any, key: str) -> None:
    if not isinstance(evidence, dict):
        return
    page = int(evidence.get("page") or 0)
    if page <= 0:
        return
    bundle = by_page.setdefault(page, {"page": page})
    bundle[key] = dict(evidence)
    bundle.setdefault("page_width", evidence.get("page_width"))
    bundle.setdefault("page_height", evidence.get("page_height"))
    bundle.setdefault("source", evidence.get("source") or "scanned_page_ocr")
