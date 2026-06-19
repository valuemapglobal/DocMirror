# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG geometry oracles for Mirror layout conservation."""

from __future__ import annotations

from typing import Any

from docmirror.core.geometry.bbox import area, center, contains
from docmirror.eval.tqg.report import GateReport


def _api(mirror_or_api: Any, *, mirror_level: str = "forensic") -> dict[str, Any]:
    if hasattr(mirror_or_api, "to_api_dict"):
        return mirror_or_api.to_api_dict(mirror_level=mirror_level, include_text=True)
    return mirror_or_api if isinstance(mirror_or_api, dict) else {}


def _doc(api: dict[str, Any]) -> dict[str, Any]:
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
        ok = all(((table.get("metadata") or {}).get("geometry") or {}).get("row_bands") and ((table.get("metadata") or {}).get("geometry") or {}).get("col_bands") for table in tables)
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

    if spec.get("require_geometry_loss_reason_for_estimated"):
        estimated = [
            cell for cell in _iter_cells(tables)
            if cell.get("geometry_status") in {"estimated", "missing"}
        ]
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

    return report
