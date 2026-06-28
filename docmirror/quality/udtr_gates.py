"""Typed quality gates for UDTR vNext output."""

from __future__ import annotations

from typing import Any

from docmirror.layout.normalization import is_invertible_matrix


def build_udtr_quality_gates(*, pages: list[Any], regions: list[Any], blocks: list[Any]) -> list[dict[str, Any]]:
    return [
        _page_normalization_confidence_gate(pages),
        _coordinate_transform_invertible_gate(pages),
        _region_candidate_resolution_gate(regions),
        _ownership_explainability_gate(regions),
        _overlay_relationship_consistency_gate(regions, blocks),
        _financial_header_hierarchy_gate(blocks),
        _financial_statement_formula_gate(blocks),
        _statement_note_reference_gate(blocks),
        _visual_artifact_coverage_gate(regions, blocks),
        _cross_format_projection_consistency_gate(pages, blocks),
    ]


def _page_normalization_confidence_gate(pages: list[Any]) -> dict[str, Any]:
    scores: list[float] = []
    target_ids: list[str] = []
    for page in pages:
        transform = getattr(page, "coordinate_transform", None) or {}
        normalization = transform.get("page_normalization") if isinstance(transform, dict) else {}
        if not isinstance(normalization, dict):
            continue
        scores.append(float(normalization.get("confidence", normalization.get("orientation_score", 1.0)) or 0.0))
        if getattr(page, "page_id", ""):
            target_ids.append(page.page_id)
    if not scores:
        return _gate("gate:page_normalization_confidence", "not_applicable", 1.0, 0.8)
    score = min(1.0, min(scores))
    return _gate("gate:page_normalization_confidence", "pass" if score >= 0.8 else "warn", score, 0.8, target_ids=target_ids)


def _coordinate_transform_invertible_gate(pages: list[Any]) -> dict[str, Any]:
    bad: list[str] = []
    for page in pages:
        transform = getattr(page, "coordinate_transform", None) or {}
        matrix = transform.get("matrix") if isinstance(transform, dict) else None
        if not matrix or not is_invertible_matrix(matrix):
            bad.append(str(getattr(page, "page_id", "") or ""))
    total = len(pages)
    score = (total - len(bad)) / total if total else 1.0
    return _gate(
        "gate:coordinate_transform_invertible",
        "pass" if not bad else "warn",
        score,
        1.0,
        target_ids=bad,
        details={"bad_page_ids": bad},
    )


def _region_candidate_resolution_gate(regions: list[Any]) -> dict[str, Any]:
    region_count = len(regions)
    if region_count == 0:
        return _gate("gate:region_candidate_resolution", "not_applicable", 1.0, 1.0)
    missing = [
        str(getattr(region, "id", "") or "")
        for region in regions
        if not (getattr(region, "quality", {}) or {}).get("selected_candidate_ids")
    ]
    score = (region_count - len(missing)) / region_count
    return _gate(
        "gate:region_candidate_resolution",
        "pass" if score >= 0.95 else "warn",
        score,
        0.95,
        target_ids=missing,
        details={"missing_candidate_region_ids": missing},
    )


def _ownership_explainability_gate(regions: list[Any]) -> dict[str, Any]:
    region_count = len(regions)
    if region_count == 0:
        return _gate("gate:ownership_explainability", "not_applicable", 1.0, 1.0)
    missing = [
        str(getattr(region, "id", "") or "")
        for region in regions
        if not (getattr(region, "quality", {}) or {}).get("ownership_reason")
    ]
    score = (region_count - len(missing)) / region_count
    return _gate(
        "gate:ownership_explainability",
        "pass" if score >= 0.99 else "warn",
        score,
        0.99,
        target_ids=missing,
        details={"missing_ownership_reason_region_ids": missing},
    )


def _financial_header_hierarchy_gate(blocks: list[Any]) -> dict[str, Any]:
    financial_tables = [
        block
        for block in blocks
        if str(getattr(block, "type", "")) == "table"
        and (
            getattr(block, "role", "") == "financial_statement"
            or (getattr(block, "content", {}) or {}).get("statement_structure")
        )
    ]
    if not financial_tables:
        return _gate("gate:financial_header_hierarchy", "not_applicable", 1.0, 0.8)
    scores = [
        float(((block.content.get("statement_structure") or {}).get("quality") or {}).get("header_hierarchy_confidence", 0.0))
        for block in financial_tables
    ]
    score = min(scores) if scores else 0.0
    target_ids = [block.id for block, value in zip(financial_tables, scores, strict=False) if value < 0.8]
    return _gate(
        "gate:financial_header_hierarchy",
        "pass" if score >= 0.8 else "warn",
        score,
        0.8,
        target_ids=target_ids,
        details={"financial_table_count": len(financial_tables)},
        suggested_action="review_header_bands",
    )


def _overlay_relationship_consistency_gate(regions: list[Any], blocks: list[Any]) -> dict[str, Any]:
    overlay_regions = [
        region
        for region in regions
        if str(getattr(region, "kind", "")) in {"seal", "signature"} or str(getattr(region, "role", "")) in {"seal", "signature"}
    ]
    overlay_blocks = [block for block in blocks if str(getattr(block, "role", "")) in {"seal", "signature"}]
    if not overlay_regions and not overlay_blocks:
        return _gate("gate:overlay_relationship_consistency", "not_applicable", 1.0, 0.8)
    explained = [
        region
        for region in overlay_regions
        if ((getattr(region, "quality", {}) or {}).get("ownership_relation") == "overlay")
        or (getattr(region, "quality", {}) or {}).get("overlay_target_region_id")
    ]
    score = len(explained) / len(overlay_regions) if overlay_regions else 1.0
    missing = [
        str(getattr(region, "id", "") or "")
        for region in overlay_regions
        if region not in explained
    ]
    return _gate(
        "gate:overlay_relationship_consistency",
        "pass" if score >= 0.8 else "warn",
        score,
        0.8,
        target_ids=missing,
        details={"overlay_region_count": len(overlay_regions), "unexplained_overlay_region_ids": missing},
        suggested_action="review_visual_overlay_regions",
    )


def _financial_statement_formula_gate(blocks: list[Any]) -> dict[str, Any]:
    financial_tables = _financial_statement_blocks(blocks)
    if not financial_tables:
        return _gate("gate:financial_statement_formula", "not_applicable", 1.0, 0.8)
    applicable = []
    missing = []
    validation_warn = []
    validation_not_evaluated = []
    for block in financial_tables:
        structure = (getattr(block, "content", {}) or {}).get("statement_structure") or {}
        if structure.get("statement_type") != "owners_equity_changes":
            continue
        applicable.append(block)
        rules = structure.get("rules") or []
        if not rules:
            missing.append(str(getattr(block, "id", "") or ""))
            continue
        for rule in rules:
            validation = rule.get("validation") if isinstance(rule, dict) else None
            if not isinstance(validation, dict):
                continue
            if validation.get("status") == "warn":
                validation_warn.append(str(getattr(block, "id", "") or ""))
            elif validation.get("status") == "not_evaluated":
                validation_not_evaluated.append(str(getattr(block, "id", "") or ""))
    if not applicable:
        return _gate("gate:financial_statement_formula", "not_applicable", 1.0, 0.8)
    bad = sorted(set([*missing, *validation_warn]))
    score = (len(applicable) - len(bad)) / len(applicable)
    return _gate(
        "gate:financial_statement_formula",
        "pass" if score >= 0.8 else "warn",
        score,
        0.8,
        target_ids=bad,
        details={
            "applicable_statement_count": len(applicable),
            "missing_rule_block_ids": missing,
            "validation_warn_block_ids": sorted(set(validation_warn)),
            "validation_not_evaluated_block_ids": sorted(set(validation_not_evaluated)),
        },
        suggested_action="review_statement_roll_forward_rules",
    )


def _statement_note_reference_gate(blocks: list[Any]) -> dict[str, Any]:
    financial_tables = _financial_statement_blocks(blocks)
    note_rows: list[tuple[Any, dict[str, Any]]] = []
    missing: list[str] = []
    for block in financial_tables:
        structure = (getattr(block, "content", {}) or {}).get("statement_structure") or {}
        for row in structure.get("account_rows", []) or []:
            if not isinstance(row, dict):
                continue
            note_ref = row.get("note_ref")
            if note_ref:
                note_rows.append((block, row))
                if not row.get("note_target_block_id") and not row.get("note_target_section_id"):
                    missing.append(f"{getattr(block, 'id', '')}:row:{row.get('row_index', '')}")
    if not financial_tables or not note_rows:
        return _gate("gate:statement_note_reference", "not_applicable", 1.0, 0.8)
    score = (len(note_rows) - len(missing)) / len(note_rows)
    return _gate(
        "gate:statement_note_reference",
        "pass" if score >= 0.8 else "warn",
        score,
        0.8,
        target_ids=missing,
        details={"note_ref_row_count": len(note_rows), "unlinked_note_refs": missing},
        suggested_action="link_statement_note_references",
    )


def _visual_artifact_coverage_gate(regions: list[Any], blocks: list[Any]) -> dict[str, Any]:
    visual_regions = [
        region
        for region in regions
        if str(getattr(region, "kind", "")) in {"seal", "signature", "figure", "image"}
    ]
    visual_blocks = [
        block
        for block in blocks
        if str(getattr(block, "type", "")) in {"artifact", "figure"} or str(getattr(block, "role", "")) in {"seal", "signature"}
    ]
    if not visual_regions and not visual_blocks:
        return _gate("gate:visual_artifact_coverage", "not_applicable", 1.0, 0.9)
    covered = [block for block in visual_blocks if getattr(block, "evidence_ids", [])]
    score = len(covered) / len(visual_blocks) if visual_blocks else 0.0
    missing = [str(getattr(block, "id", "") or "") for block in visual_blocks if not getattr(block, "evidence_ids", [])]
    return _gate(
        "gate:visual_artifact_coverage",
        "pass" if score >= 0.9 else "warn",
        score,
        0.9,
        target_ids=missing,
        details={"visual_region_count": len(visual_regions), "visual_block_count": len(visual_blocks)},
        suggested_action="review_visual_artifact_evidence",
    )


def _cross_format_projection_consistency_gate(pages: list[Any], blocks: list[Any]) -> dict[str, Any]:
    if not pages:
        return _gate("gate:cross_format_projection_consistency", "not_applicable", 1.0, 1.0)
    page_ids = {str(getattr(page, "page_id", "") or "") for page in pages}
    missing_page = [
        str(getattr(block, "id", "") or "")
        for block in blocks
        if not set(str(page_id) for page_id in getattr(block, "page_ids", []) or []) <= page_ids
    ]
    score = (len(blocks) - len(missing_page)) / len(blocks) if blocks else 1.0
    return _gate(
        "gate:cross_format_projection_consistency",
        "pass" if not missing_page else "warn",
        score,
        1.0,
        target_ids=missing_page,
        details={"invalid_block_page_refs": missing_page},
    )


def _financial_statement_blocks(blocks: list[Any]) -> list[Any]:
    return [
        block
        for block in blocks
        if str(getattr(block, "type", "")) == "table"
        and (
            getattr(block, "role", "") == "financial_statement"
            or (getattr(block, "content", {}) or {}).get("statement_structure")
        )
    ]


def _gate(
    gate_id: str,
    status: str,
    score: float,
    threshold: float,
    *,
    target_ids: list[str] | None = None,
    details: dict[str, Any] | None = None,
    suggested_action: str = "",
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": gate_id,
        "status": status,
        "score": float(score),
        "threshold": float(threshold),
    }
    if target_ids:
        out["target_ids"] = target_ids
    if details:
        out["details"] = details
    if suggested_action:
        out["suggested_action"] = suggested_action
    return out
