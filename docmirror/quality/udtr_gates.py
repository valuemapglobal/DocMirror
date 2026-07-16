"""Typed quality gates for UDTR vNext output."""

from __future__ import annotations

from typing import Any

from docmirror.layout.normalization import is_invertible_matrix


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def build_udtr_quality_gates(
    *,
    pages: list[Any],
    regions: list[Any],
    blocks: list[Any],
    evidence_atoms: list[Any] | None = None,
    graph: dict[str, Any] | None = None,
    source_provenance: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    atoms = list(evidence_atoms or [])
    return [
        _page_normalization_confidence_gate(pages),
        _coordinate_transform_invertible_gate(pages),
        _coordinate_roundtrip_gate(pages, atoms),
        _ocr_confidence_gate(pages, atoms),
        _scanned_visual_coverage_gate(pages, atoms),
        _table_structure_coverage_gate(blocks),
        _table_grid_integrity_gate(blocks),
        _physical_table_reference_integrity_gate(blocks, graph or {}, source_provenance or {}),
        _text_source_conservation_gate(blocks, atoms),
        _region_candidate_resolution_gate(regions),
        _ownership_explainability_gate(regions),
        _overlay_relationship_consistency_gate(regions, blocks),
        _financial_header_hierarchy_gate(blocks),
        _financial_statement_formula_gate(blocks),
        _statement_note_reference_gate(blocks),
        _visual_artifact_coverage_gate(regions, blocks),
        _cross_format_projection_consistency_gate(pages, blocks),
    ]


def _coordinate_roundtrip_gate(pages: list[Any], atoms: list[Any]) -> dict[str, Any]:
    page_by_id = {str(_value(page, "page_id", "") or ""): page for page in pages}
    checked = 0
    bad: list[str] = []
    max_error = 0.0
    outside_crop: list[str] = []
    for atom in atoms:
        bbox = _value(atom, "bbox")
        source_bbox = _value(atom, "source_bbox")
        page = page_by_id.get(str(_value(atom, "page_id", "") or ""))
        if page is None or not _bbox(bbox) or not _bbox(source_bbox):
            continue
        transform = _value(atom, "coordinate_transform", {}) or _value(page, "coordinate_transform", {}) or {}
        matrix = transform.get("matrix") if isinstance(transform, dict) else None
        if not _matrix(matrix):
            continue
        projected = _transform_bbox(source_bbox, matrix)
        error = max(abs(float(projected[index]) - float(bbox[index])) for index in range(4))
        max_error = max(max_error, error)
        checked += 1
        atom_id = str(_value(atom, "id", "") or "")
        if error > 0.5:
            bad.append(atom_id)
        crop = transform.get("source_crop_bbox") if isinstance(transform, dict) else None
        if _bbox(crop) and not _bbox_inside(source_bbox, crop, tolerance=1.0):
            outside_crop.append(atom_id)
    if checked == 0:
        return _gate("gate:coordinate_roundtrip", "not_applicable", 1.0, 1.0)
    failures = sorted(set([*bad, *outside_crop]))
    score = max(0.0, (checked - len(failures)) / checked)
    return _gate(
        "gate:coordinate_roundtrip",
        "pass" if not failures else "warn",
        score,
        1.0,
        target_ids=failures,
        details={
            "checked_atom_count": checked,
            "max_roundtrip_error": round(max_error, 6),
            "roundtrip_failure_ids": bad,
            "outside_source_crop_ids": outside_crop,
        },
    )


def _ocr_confidence_gate(pages: list[Any], atoms: list[Any]) -> dict[str, Any]:
    scanned_pages = {
        str(_value(page, "page_id", "") or "")
        for page in pages
        if str(_value(page, "content_mode", "") or "") == "scanned_ocr"
    }
    ocr_atoms = [
        atom
        for atom in atoms
        if str(_value(atom, "page_id", "") or "") in scanned_pages
        and str(_value(atom, "kind", "") or "") in {"text_token", "text_line"}
    ]
    if not ocr_atoms:
        return _gate("gate:ocr_confidence", "not_applicable", 1.0, 0.8)
    weighted = [
        (float(_value(atom, "confidence", 0.0) or 0.0), max(1, len(str(_value(atom, "text", "") or ""))))
        for atom in ocr_atoms
    ]
    total_weight = sum(weight for _confidence, weight in weighted)
    average = sum(confidence * weight for confidence, weight in weighted) / total_weight
    sorted_values = sorted(confidence for confidence, _weight in weighted)
    p10 = sorted_values[max(0, int(len(sorted_values) * 0.10) - 1)]
    median = sorted_values[len(sorted_values) // 2]
    low_ids = [
        str(_value(atom, "id", "") or "") for atom in ocr_atoms if float(_value(atom, "confidence", 0.0) or 0.0) < 0.8
    ]
    return _gate(
        "gate:ocr_confidence",
        "pass" if average >= 0.8 and p10 >= 0.6 else "warn",
        average,
        0.8,
        target_ids=low_ids,
        details={
            "token_count": len(ocr_atoms),
            "character_weighted_average": round(average, 6),
            "minimum": min(sorted_values),
            "p10": p10,
            "p50": median,
            "below_0_8_count": len(low_ids),
        },
    )


def _scanned_visual_coverage_gate(pages: list[Any], atoms: list[Any]) -> dict[str, Any]:
    scanned_ids = {
        str(_value(page, "page_id", "") or "")
        for page in pages
        if str(_value(page, "content_mode", "") or "") == "scanned_ocr"
    }
    if not scanned_ids:
        return _gate("gate:scanned_visual_coverage", "not_applicable", 1.0, 1.0)
    covered_ids = {
        str(_value(atom, "page_id", "") or "")
        for atom in atoms
        if str(_value(atom, "kind", "") or "") in {"rendered_image", "embedded_image"}
        and str((_value(atom, "metadata", {}) or {}).get("role") or "") == "page_background"
    }
    missing = sorted(scanned_ids - covered_ids)
    score = (len(scanned_ids) - len(missing)) / len(scanned_ids)
    return _gate(
        "gate:scanned_visual_coverage",
        "pass" if not missing else "warn",
        score,
        1.0,
        target_ids=missing,
        details={"scanned_page_count": len(scanned_ids), "covered_page_count": len(scanned_ids & covered_ids)},
    )


def _table_structure_coverage_gate(blocks: list[Any]) -> dict[str, Any]:
    tables = [block for block in blocks if str(_value(block, "type", "") or "") == "table"]
    if not tables:
        return _gate("gate:table_structure_coverage", "not_applicable", 1.0, 0.8)
    covered: list[str] = []
    missing: list[str] = []
    assignment_scores: list[float] = []
    for block in tables:
        block_id = str(_value(block, "id", "") or "")
        grid = (_value(block, "content", {}) or {}).get("grid") or {}
        cells = grid.get("cells") or []
        geometry = (_value(block, "content", {}) or {}).get("geometry") or {}
        if not geometry:
            geometry = (_value(block, "provenance", {}) or {}).get("geometry") or {}
        cells_with_bbox = [cell for cell in cells if _bbox(cell.get("bbox"))]
        expected_assignment = [cell for cell in cells if str(cell.get("text") or "").strip()]
        assigned = [cell for cell in expected_assignment if cell.get("evidence_ids") or cell.get("token_ids")]
        if cells and len(cells_with_bbox) == len(cells):
            covered.append(block_id)
        else:
            missing.append(block_id)
        if expected_assignment:
            assignment_scores.append(len(assigned) / len(expected_assignment))
        if geometry.get("geometry_confidence") is not None:
            assignment_scores.append(float(geometry.get("geometry_confidence") or 0.0))
    score = min(assignment_scores or [len(covered) / len(tables)])
    return _gate(
        "gate:table_structure_coverage",
        "pass" if not missing and score >= 0.8 else "warn",
        score,
        0.8,
        target_ids=missing,
        details={
            "table_count": len(tables),
            "tables_with_complete_cell_geometry": len(covered),
            "minimum_geometry_or_assignment_score": round(score, 6),
        },
    )


def _table_grid_integrity_gate(blocks: list[Any]) -> dict[str, Any]:
    tables = [block for block in blocks if str(_value(block, "type", "") or "") == "table"]
    if not tables:
        return _gate("gate:table_grid_integrity", "not_applicable", 1.0, 1.0)
    invalid_ids: list[str] = []
    overlap_count = 0
    out_of_bounds_count = 0
    duplicate_anchor_count = 0
    for block in tables:
        block_id = str(_value(block, "id", "") or "")
        grid = (_value(block, "content", {}) or {}).get("grid") or {}
        row_count = len(grid.get("rows") or [])
        column_count = len(grid.get("columns") or [])
        occupancy: dict[tuple[int, int], str] = {}
        anchors: set[tuple[int, int]] = set()
        invalid = False
        for cell in grid.get("cells") or []:
            row = int(cell.get("row", -1))
            col = int(cell.get("col", -1))
            row_span = max(1, int(cell.get("row_span", 1) or 1))
            col_span = max(1, int(cell.get("col_span", 1) or 1))
            if (row, col) in anchors:
                duplicate_anchor_count += 1
                invalid = True
            anchors.add((row, col))
            if row < 0 or col < 0 or row + row_span > row_count or col + col_span > column_count:
                out_of_bounds_count += 1
                invalid = True
                continue
            for occupied_row in range(row, row + row_span):
                for occupied_col in range(col, col + col_span):
                    slot = (occupied_row, occupied_col)
                    if slot in occupancy:
                        overlap_count += 1
                        invalid = True
                    else:
                        occupancy[slot] = str(cell.get("id") or "")
        if invalid:
            invalid_ids.append(block_id)
    score = (len(tables) - len(invalid_ids)) / len(tables)
    return _gate(
        "gate:table_grid_integrity",
        "pass" if not invalid_ids else "fail",
        score,
        1.0,
        target_ids=invalid_ids,
        details={
            "table_count": len(tables),
            "invalid_table_count": len(invalid_ids),
            "overlap_slot_count": overlap_count,
            "out_of_bounds_span_count": out_of_bounds_count,
            "duplicate_anchor_count": duplicate_anchor_count,
        },
    )


def _physical_table_reference_integrity_gate(
    blocks: list[Any],
    graph: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    physical_ids = [
        str((_value(block, "provenance", {}) or {}).get("source_table_id") or "")
        for block in blocks
        if str(_value(block, "type", "") or "") == "table"
    ]
    physical_ids = [value for value in physical_ids if value]
    logical_refs = provenance.get("logical_table_refs") or provenance.get("logical_tables") or []
    if not physical_ids or not logical_refs:
        return _gate("gate:physical_table_reference_integrity", "not_applicable", 1.0, 1.0)
    referenced = [
        str(source_id)
        for item in logical_refs
        if isinstance(item, dict)
        for source_id in item.get("source_physical_ids", []) or []
    ]
    physical_set = set(physical_ids)
    referenced_set = set(referenced)
    missing = sorted(physical_set - referenced_set)
    unknown = sorted(referenced_set - physical_set)
    duplicate_refs = sorted(source_id for source_id in referenced_set if referenced.count(source_id) > 1)
    self_loops = [
        str(edge.get("id") or "")
        for edge in graph.get("edges", []) or []
        if edge.get("type") in {"same_table", "continues"} and edge.get("from") == edge.get("to")
    ]
    invalid = bool(missing or unknown or duplicate_refs or self_loops or len(physical_ids) != len(physical_set))
    score = len(physical_set & referenced_set) / len(physical_set)
    return _gate(
        "gate:physical_table_reference_integrity",
        "fail" if invalid else "pass",
        score,
        1.0,
        target_ids=[*missing, *unknown, *self_loops],
        details={
            "physical_table_count": len(physical_ids),
            "unique_physical_table_count": len(physical_set),
            "referenced_physical_table_count": len(referenced_set & physical_set),
            "missing_physical_table_ids": missing,
            "unknown_physical_table_ids": unknown,
            "duplicate_source_reference_ids": duplicate_refs,
            "self_loop_edge_ids": self_loops,
        },
    )


def _text_source_conservation_gate(blocks: list[Any], atoms: list[Any]) -> dict[str, Any]:
    text_atoms = [atom for atom in atoms if str(_value(atom, "kind", "") or "") in {"text_token", "text_line"}]
    source_refs = [
        str(source_ref) for atom in text_atoms for source_ref in (_value(atom, "source_refs", []) or []) if source_ref
    ]
    if not source_refs:
        return _gate("gate:text_source_conservation", "not_applicable", 1.0, 1.0)
    duplicate_source_refs = sorted(source_ref for source_ref in set(source_refs) if source_refs.count(source_ref) > 1)
    atom_ids = {str(_value(atom, "id", "") or "") for atom in text_atoms}
    owned_atom_ids = {
        str(evidence_id)
        for block in blocks
        for evidence_id in (_value(block, "evidence_ids", []) or [])
        if str(evidence_id) in atom_ids
    }
    unowned_atom_ids = sorted(atom_ids - owned_atom_ids)
    invalid = bool(duplicate_source_refs or unowned_atom_ids)
    score = len(owned_atom_ids) / len(atom_ids) if atom_ids else 1.0
    return _gate(
        "gate:text_source_conservation",
        "fail" if invalid else "pass",
        score,
        1.0,
        target_ids=unowned_atom_ids,
        details={
            "source_ref_count": len(source_refs),
            "unique_source_ref_count": len(set(source_refs)),
            "duplicate_source_ref_ids": duplicate_source_refs,
            "text_atom_count": len(atom_ids),
            "owned_text_atom_count": len(owned_atom_ids),
            "unowned_text_atom_ids": unowned_atom_ids,
        },
    )


def _bbox(value: Any) -> bool:
    return isinstance(value, list | tuple) and len(value) == 4


def _matrix(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 3 and all(isinstance(row, list) and len(row) == 3 for row in value)


def _transform_bbox(bbox: Any, matrix: list[list[float]]) -> list[float]:
    x0, y0, x1, y1 = [float(item) for item in bbox]
    points = [_apply(matrix, x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _apply(matrix: list[list[float]], x: float, y: float) -> tuple[float, float]:
    return (
        float(matrix[0][0]) * x + float(matrix[0][1]) * y + float(matrix[0][2]),
        float(matrix[1][0]) * x + float(matrix[1][1]) * y + float(matrix[1][2]),
    )


def _bbox_inside(inner: Any, outer: Any, *, tolerance: float) -> bool:
    return (
        float(inner[0]) >= float(outer[0]) - tolerance
        and float(inner[1]) >= float(outer[1]) - tolerance
        and float(inner[2]) <= float(outer[2]) + tolerance
        and float(inner[3]) <= float(outer[3]) + tolerance
    )


def _page_normalization_confidence_gate(pages: list[Any]) -> dict[str, Any]:
    scores: list[float] = []
    target_ids: list[str] = []
    for page in pages:
        transform = _value(page, "coordinate_transform", {}) or {}
        normalization = transform.get("page_normalization") if isinstance(transform, dict) else {}
        if not isinstance(normalization, dict) or not normalization:
            decomposition = transform.get("decomposition") if isinstance(transform, dict) else None
            normalization = decomposition if isinstance(decomposition, dict) else {}
        if not isinstance(normalization, dict):
            continue
        scores.append(float(normalization.get("confidence", normalization.get("orientation_score", 1.0)) or 0.0))
        if _value(page, "page_id", ""):
            target_ids.append(str(_value(page, "page_id", "")))
    if not scores:
        return _gate("gate:page_normalization_confidence", "not_applicable", 1.0, 0.8)
    score = min(1.0, min(scores))
    return _gate(
        "gate:page_normalization_confidence", "pass" if score >= 0.8 else "warn", score, 0.8, target_ids=target_ids
    )


def _coordinate_transform_invertible_gate(pages: list[Any]) -> dict[str, Any]:
    bad: list[str] = []
    for page in pages:
        transform = _value(page, "coordinate_transform", {}) or {}
        matrix = transform.get("matrix") if isinstance(transform, dict) else None
        if not matrix or not is_invertible_matrix(matrix):
            bad.append(str(_value(page, "page_id", "") or ""))
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
        str(_value(region, "id", "") or "")
        for region in regions
        if not (_value(region, "quality", {}) or {}).get("selected_candidate_ids")
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
        str(_value(region, "id", "") or "")
        for region in regions
        if not (_value(region, "quality", {}) or {}).get("ownership_reason")
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
        float(
            ((block.content.get("statement_structure") or {}).get("quality") or {}).get(
                "header_hierarchy_confidence", 0.0
            )
        )
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
        if str(getattr(region, "kind", "")) in {"seal", "signature"}
        or str(getattr(region, "role", "")) in {"seal", "signature"}
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
    missing = [str(getattr(region, "id", "") or "") for region in overlay_regions if region not in explained]
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
        region for region in regions if str(_value(region, "kind", "")) in {"seal", "signature", "figure", "image"}
    ]
    visual_blocks = [
        block
        for block in blocks
        if str(_value(block, "type", "")) in {"artifact", "figure"}
        or str(_value(block, "role", "")) in {"seal", "signature"}
    ]
    if not visual_regions and not visual_blocks:
        return _gate("gate:visual_artifact_coverage", "not_applicable", 1.0, 0.9)
    covered = [block for block in visual_blocks if _value(block, "evidence_ids", [])]
    score = len(covered) / len(visual_blocks) if visual_blocks else 0.0
    missing = [str(_value(block, "id", "") or "") for block in visual_blocks if not _value(block, "evidence_ids", [])]
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
    page_ids = {str(_value(page, "page_id", "") or "") for page in pages}
    missing_page = [
        str(_value(block, "id", "") or "")
        for block in blocks
        if not set(str(page_id) for page_id in _value(block, "page_ids", []) or []) <= page_ids
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
