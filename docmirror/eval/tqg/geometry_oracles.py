# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG geometry oracles for Mirror layout conservation."""

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.report import GateReport
from docmirror.geometry.bbox import area, center, contains


def _api(mirror_or_api: Any, *, mirror_level: str = "forensic") -> dict[str, Any]:
    if hasattr(mirror_or_api, "to_mirror_json_vnext"):
        return mirror_or_api.to_mirror_json_vnext()
    return mirror_or_api if isinstance(mirror_or_api, dict) else {}


def _doc(api: dict[str, Any]) -> dict[str, Any]:
    if isinstance(api.get("document"), dict):
        return api["document"]
    data = api.get("data") or {}
    doc = data.get("document") or {}
    return doc if isinstance(doc, dict) else {}


def _tables(api: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in _doc(api).get("pages") or []:
        if not isinstance(page, dict):
            continue
        for table in page.get("tables") or []:
            if isinstance(table, dict):
                out.append(table)
    return out


def _cells(table: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        for cell in row.get("cells") or []:
            if isinstance(cell, dict):
                out.append(cell)
    return out


def _non_empty_cells(table: dict[str, Any]) -> list[dict[str, Any]]:
    return [cell for cell in _cells(table) if str(cell.get("text") or "").strip()]


def _bbox_coverage(tables: list[dict[str, Any]]) -> tuple[int, int, float]:
    total = 0
    covered = 0
    for table in tables:
        for cell in _non_empty_cells(table):
            total += 1
            if cell.get("bbox") and area(cell.get("bbox")) > 0:
                covered += 1
    ratio = covered / total if total else 1.0
    return covered, total, ratio


def _geometry_status_counts(tables: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"exact": 0, "estimated": 0, "missing": 0, "other": 0, "total": 0}
    for table in tables:
        for cell in _non_empty_cells(table):
            counts["total"] += 1
            status = str(cell.get("geometry_status") or "missing")
            if status in ("exact", "estimated", "missing"):
                counts[status] += 1
            else:
                counts["other"] += 1
    return counts


def _row_monotonic(table: dict[str, Any]) -> bool:
    for row in table.get("rows") or []:
        xs: list[float] = []
        for cell in row.get("cells") or []:
            c = center(cell.get("bbox"))
            if c is not None:
                xs.append(c[0])
        if xs != sorted(xs):
            return False
    return True


def _col_monotonic(table: dict[str, Any]) -> bool:
    col_to_ys: dict[int, list[float]] = {}
    for row in table.get("rows") or []:
        for idx, cell in enumerate(row.get("cells") or []):
            cidx = int(cell.get("col_index") if cell.get("col_index") is not None else idx)
            c = center(cell.get("bbox"))
            if c is not None:
                col_to_ys.setdefault(cidx, []).append(c[1])
    return all(ys == sorted(ys) for ys in col_to_ys.values())


def _table_contains_cells(table: dict[str, Any]) -> bool:
    tb = table.get("bbox")
    if not tb:
        return True
    return all(not cell.get("bbox") or contains(tb, cell.get("bbox"), tolerance=2.0) for cell in _cells(table))


def _logical_refs_present(api: dict[str, Any]) -> bool:
    logical = _doc(api).get("logical_tables") or []
    if not logical:
        return True
    for table in logical:
        for row in table.get("rows") or []:
            refs = row.get("source_cell_refs") or []
            if not refs:
                return False
    return True


def _physical_cell_index(api: dict[str, Any]) -> set[tuple[int, str, int, int]]:
    index: set[tuple[int, str, int, int]] = set()
    for table in _tables(api):
        table_id = str(table.get("table_id") or "")
        page = int(table.get("page") or 0)
        if not table_id:
            continue
        for row_idx, row in enumerate(table.get("rows") or []):
            if not isinstance(row, dict):
                continue
            ref_row = row.get("source_row_index")
            try:
                source_row = int(ref_row) if ref_row is not None else row_idx
            except (TypeError, ValueError):
                source_row = row_idx
            for col_idx, cell in enumerate(row.get("cells") or []):
                if isinstance(cell, dict):
                    index.add((page, table_id, row_idx, col_idx))
                    index.add((page, table_id, source_row, col_idx))
    return index


def _ref_candidates(ref: dict[str, Any]) -> list[tuple[int, str, int, int]]:
    table_id = str(ref.get("table_id") or ref.get("source_physical_id") or "")
    try:
        page = int(ref.get("page") or ref.get("source_page") or 0)
    except (TypeError, ValueError):
        page = 0
    try:
        col = int(ref.get("col") if ref.get("col") is not None else ref.get("col_index"))
    except (TypeError, ValueError):
        return []
    rows: list[int] = []
    for key in ("row", "row_index", "source_row_index", "raw_row"):
        if ref.get(key) is None:
            continue
        try:
            rows.append(int(ref.get(key)))
        except (TypeError, ValueError):
            continue
    return [(page, table_id, row, col) for row in dict.fromkeys(rows) if table_id and page > 0]


def _logical_refs_resolve(api: dict[str, Any]) -> bool:
    physical = _physical_cell_index(api)
    if not physical:
        return True
    logical = _doc(api).get("logical_tables") or []
    for table in logical:
        for row in table.get("rows") or []:
            for ref in row.get("source_cell_refs") or []:
                if not isinstance(ref, dict):
                    return False
                candidates = _ref_candidates(ref)
                if not candidates or not any(candidate in physical for candidate in candidates):
                    return False
    return True


def _physical_cell_refs_present(tables: list[dict[str, Any]]) -> bool:
    nonempty = [cell for table in tables for cell in _non_empty_cells(table)]
    if not nonempty:
        return True
    return all(cell.get("source_cell_refs") for cell in nonempty)


def _unique_cell_token_ownership(tables: list[dict[str, Any]]) -> tuple[bool, int]:
    owners: dict[str, tuple[str, int, int]] = {}
    duplicate_count = 0
    for table in tables:
        table_id = str(table.get("table_id") or "")
        for row_idx, row in enumerate(table.get("rows") or []):
            if not isinstance(row, dict):
                continue
            for col_idx, cell in enumerate(row.get("cells") or []):
                if not isinstance(cell, dict):
                    continue
                for token_id in cell.get("token_ids") or []:
                    token = str(token_id)
                    owner = (table_id, row_idx, col_idx)
                    previous = owners.get(token)
                    if previous is not None and previous != owner:
                        duplicate_count += 1
                    else:
                        owners[token] = owner
    return duplicate_count == 0, duplicate_count


def _band_by_index(bands: list[Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for band in bands or []:
        if not isinstance(band, dict):
            continue
        try:
            out[int(band.get("index") or 0)] = band
        except (TypeError, ValueError):
            continue
    return out


def _span_bbox(row_boxes: list[Any], col_boxes: list[Any]) -> list[float] | None:
    rows = [box for box in row_boxes if isinstance(box, list | tuple) and len(box) == 4]
    cols = [box for box in col_boxes if isinstance(box, list | tuple) and len(box) == 4]
    if not rows or not cols:
        return None
    return [
        min(float(box[0]) for box in cols),
        min(float(box[1]) for box in rows),
        max(float(box[2]) for box in cols),
        max(float(box[3]) for box in rows),
    ]


def _merged_cell_bands_consistent(table: dict[str, Any]) -> tuple[bool, int]:
    geometry = ((table.get("metadata") or {}).get("geometry") or {}) if isinstance(table, dict) else {}
    merged_cells = geometry.get("merged_cells") or (table.get("metadata") or {}).get("merged_cells") or []
    if not merged_cells:
        return True, 0
    row_bands = _band_by_index(list(geometry.get("row_bands") or []))
    col_bands = _band_by_index(list(geometry.get("col_bands") or []))
    if not row_bands or not col_bands:
        return False, len(merged_cells)

    for merged in merged_cells:
        if not isinstance(merged, dict):
            return False, len(merged_cells)
        bbox = merged.get("bbox")
        if not (isinstance(bbox, list | tuple) and len(bbox) == 4 and area(bbox) > 0):
            return False, len(merged_cells)
        row = int(merged.get("row") or 0)
        col = int(merged.get("col") or 0)
        rowspan = max(1, int(merged.get("rowspan") or 1))
        colspan = max(1, int(merged.get("colspan") or 1))
        expected = _span_bbox(
            [row_bands[idx].get("bbox") for idx in range(row, row + rowspan) if idx in row_bands],
            [col_bands[idx].get("bbox") for idx in range(col, col + colspan) if idx in col_bands],
        )
        if expected is None:
            return False, len(merged_cells)
        if not contains(expected, bbox, tolerance=3.0) or not contains(bbox, expected, tolerance=3.0):
            return False, len(merged_cells)
    return True, len(merged_cells)


def _iter_cells(tables: list[dict[str, Any]]):
    for table in tables:
        for row in table.get("rows") or []:
            for cell in row.get("cells") or []:
                if isinstance(cell, dict):
                    yield cell


def run_mirror_geometry_oracle(
    mirror_or_api: Any,
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "regression",
) -> GateReport:
    """Validate Mirror geometry conservation from ParseResult or API dict."""
    report = GateReport(case_id=case_id, track=track, tier=tier)
    forensic = _api(mirror_or_api, mirror_level=str(spec.get("mirror_level", "forensic")))
    standard = _api(mirror_or_api, mirror_level="standard")
    tables = _tables(forensic)

    min_tables = spec.get("min_physical_tables")
    if min_tables is not None:
        ok = len(tables) >= int(min_tables)
        report.checks["geometry_min_physical_tables"] = ok
        report.metrics["physical_table_count"] = len(tables)
        if not ok:
            report.passed = False
            report.failures.append(f"physical_table_count expected >= {min_tables}, got {len(tables)}")

    min_coverage = spec.get("min_cell_bbox_coverage")
    if min_coverage is not None:
        covered, total, ratio = _bbox_coverage(tables)
        ok = ratio >= float(min_coverage)
        report.checks["geometry_min_cell_bbox_coverage"] = ok
        report.metrics.update({"cell_bbox_covered": covered, "cell_bbox_total": total, "cell_bbox_coverage": ratio})
        if not ok:
            report.passed = False
            report.failures.append(f"cell bbox coverage expected >= {min_coverage}, got {ratio:.3f}")

    status_counts = _geometry_status_counts(tables)
    if status_counts["total"] > 0:
        exact_ratio = status_counts["exact"] / status_counts["total"]
        estimated_ratio = status_counts["estimated"] / status_counts["total"]
        missing_ratio = status_counts["missing"] / status_counts["total"]
    else:
        exact_ratio = 1.0
        estimated_ratio = 0.0
        missing_ratio = 0.0
    report.metrics.update(
        {
            "exact_geometry_cells": status_counts["exact"],
            "estimated_geometry_cells": status_counts["estimated"],
            "missing_status_geometry_cells": status_counts["missing"],
            "exact_geometry_ratio": exact_ratio,
            "estimated_geometry_ratio": estimated_ratio,
            "missing_status_geometry_ratio": missing_ratio,
        }
    )

    min_exact = spec.get("min_exact_geometry_ratio")
    if min_exact is not None:
        ok = exact_ratio >= float(min_exact)
        report.checks["geometry_min_exact_ratio"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"exact geometry ratio expected >= {min_exact}, got {exact_ratio:.3f}")

    max_estimated = spec.get("max_estimated_geometry_ratio")
    if max_estimated is not None:
        ok = estimated_ratio <= float(max_estimated)
        report.checks["geometry_max_estimated_ratio"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"estimated geometry ratio expected <= {max_estimated}, got {estimated_ratio:.3f}")

    max_missing = spec.get("max_missing_geometry_cells")
    if max_missing is not None:
        covered, total, _ratio = _bbox_coverage(tables)
        missing = max(0, total - covered)
        ok = missing <= int(max_missing)
        report.checks["geometry_max_missing_cells"] = ok
        report.metrics["missing_geometry_cells"] = missing
        if not ok:
            report.passed = False
            report.failures.append(f"missing geometry cells expected <= {max_missing}, got {missing}")

    if spec.get("require_monotonic_rows"):
        ok = all(_row_monotonic(table) for table in tables)
        report.checks["geometry_monotonic_rows"] = ok
        if not ok:
            report.passed = False
            report.failures.append("row cell x-centers are not monotonic")

    if spec.get("require_monotonic_cols"):
        ok = all(_col_monotonic(table) for table in tables)
        report.checks["geometry_monotonic_cols"] = ok
        if not ok:
            report.passed = False
            report.failures.append("column cell y-centers are not monotonic")

    if spec.get("require_table_bbox_contains_cells"):
        ok = all(_table_contains_cells(table) for table in tables)
        report.checks["geometry_table_contains_cells"] = ok
        if not ok:
            report.passed = False
            report.failures.append("at least one cell bbox falls outside its table bbox")

    if spec.get("require_row_col_bands"):
        ok = all(
            ((table.get("metadata") or {}).get("geometry") or {}).get("row_bands")
            and ((table.get("metadata") or {}).get("geometry") or {}).get("col_bands")
            for table in tables
        )
        report.checks["geometry_row_col_bands"] = ok
        if not ok:
            report.passed = False
            report.failures.append("expected row_bands and col_bands for every physical table")

    if spec.get("require_logical_source_cell_refs"):
        ok = _logical_refs_present(standard)
        report.checks["geometry_logical_source_cell_refs"] = ok
        if not ok:
            report.passed = False
            report.failures.append("expected logical rows to carry source_cell_refs")

    if spec.get("require_logical_source_refs_resolve"):
        ok = _logical_refs_resolve(forensic)
        report.checks["geometry_logical_source_refs_resolve"] = ok
        if not ok:
            report.passed = False
            report.failures.append("expected logical source_cell_refs to resolve to physical table cells")

    if spec.get("require_physical_cell_source_refs"):
        ok = _physical_cell_refs_present(tables)
        report.checks["geometry_physical_cell_source_refs"] = ok
        if not ok:
            report.passed = False
            report.failures.append("expected non-empty physical cells to carry source_cell_refs")

    if spec.get("require_geometry_loss_reason_for_estimated"):
        estimated = [cell for cell in _iter_cells(tables) if cell.get("geometry_status") in {"estimated", "missing"}]
        ok = all(cell.get("geometry_loss_reason") for cell in estimated)
        report.checks["geometry_loss_reason_for_estimated"] = ok
        report.metrics["estimated_or_missing_geometry_cells"] = len(estimated)
        if not ok:
            report.passed = False
            report.failures.append("expected estimated/missing geometry cells to carry geometry_loss_reason")

    if spec.get("require_cell_token_ids"):
        nonempty = [cell for cell in _iter_cells(tables) if str(cell.get("text") or "").strip()]
        ok = all(cell.get("token_ids") for cell in nonempty)
        report.checks["geometry_cell_token_ids"] = ok
        report.metrics["nonempty_cell_count"] = len(nonempty)
        if not ok:
            report.passed = False
            report.failures.append("expected non-empty geometry cells to carry token_ids")

    if spec.get("require_unique_cell_token_ownership"):
        ok, duplicate_count = _unique_cell_token_ownership(tables)
        report.checks["geometry_unique_cell_token_ownership"] = ok
        report.metrics["duplicate_cell_token_ownership_count"] = duplicate_count
        if not ok:
            report.passed = False
            report.failures.append(f"expected token_ids to belong to one cell, found {duplicate_count} duplicates")

    if spec.get("require_merged_cell_bbox_consistency"):
        results = [_merged_cell_bands_consistent(table) for table in tables]
        ok = all(result[0] for result in results)
        report.checks["geometry_merged_cell_bbox_consistency"] = ok
        report.metrics["merged_cell_count"] = sum(result[1] for result in results)
        if not ok:
            report.passed = False
            report.failures.append("expected merged cell bbox to match row/col band span")

    return report
