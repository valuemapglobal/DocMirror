# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG oracle for scanned micro-grid reconstruction."""

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.report import GateReport
from docmirror.models.mirror.page_access import micro_grids_from_document


def _doc(mirror_or_api: Any) -> dict[str, Any]:
    if hasattr(mirror_or_api, "to_mirror_json_vnext"):
        api = mirror_or_api.to_mirror_json_vnext()
        doc = (api.get("document") or {}) if isinstance(api, dict) else {}
        entities = getattr(mirror_or_api, "entities", None)
        domain_specific = getattr(entities, "domain_specific", None) if entities is not None else None
        if isinstance(domain_specific, dict) and domain_specific.get("credit_repayment_records"):
            doc = dict(doc)
            doc["repayment_records"] = list(domain_specific.get("credit_repayment_records") or [])
        return doc
    elif isinstance(mirror_or_api, dict):
        api = mirror_or_api
    else:
        api = {}
    if isinstance(api.get("document"), dict):
        return api["document"]
    return ((api.get("data") or {}).get("document") or {}) if isinstance(api, dict) else {}


def run_scanned_micro_grid_oracle(
    mirror_or_api: Any,
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "regression",
) -> GateReport:
    report = GateReport(case_id=case_id, track=track, tier=tier)
    doc = _doc(mirror_or_api)
    grids = micro_grids_from_document(doc)
    records = doc.get("repayment_records") or []

    min_grids = int(spec.get("min_micro_grids", 0) or 0)
    if min_grids:
        ok = len(grids) >= min_grids
        report.checks["scanned_micro_grid_min_grids"] = ok
        report.metrics["micro_grid_count"] = len(grids)
        if not ok:
            report.passed = False
            report.failures.append(f"micro_grid_count expected >= {min_grids}, got {len(grids)}")

    max_grids = spec.get("max_micro_grids")
    if max_grids is not None:
        max_grids_int = int(max_grids)
        ok = len(grids) <= max_grids_int
        report.checks["scanned_micro_grid_max_grids"] = ok
        report.metrics["micro_grid_count"] = len(grids)
        if not ok:
            report.passed = False
            report.failures.append(f"micro_grid_count expected <= {max_grids_int}, got {len(grids)}")

    if spec.get("require_row_col_bands"):
        ok = all((grid.get("row_bands") and grid.get("col_bands")) for grid in grids)
        report.checks["scanned_micro_grid_row_col_bands"] = ok
        if not ok:
            report.passed = False
            report.failures.append("expected every micro grid to carry row_bands and col_bands")

    min_cell_bbox_coverage = spec.get("min_cell_bbox_coverage")
    if min_cell_bbox_coverage is not None:
        total = 0
        covered = 0
        for grid in grids:
            for row in grid.get("cells") or []:
                for cell in row or []:
                    if not isinstance(cell, dict) or not str(cell.get("text") or "").strip():
                        continue
                    total += 1
                    if cell.get("bbox"):
                        covered += 1
        ratio = covered / total if total else 1.0
        ok = ratio >= float(min_cell_bbox_coverage)
        report.checks["scanned_micro_grid_cell_bbox_coverage"] = ok
        report.metrics["micro_grid_cell_bbox_coverage"] = ratio
        report.metrics["micro_grid_nonempty_cell_count"] = total
        if not ok:
            report.passed = False
            report.failures.append(
                f"micro-grid cell bbox coverage expected >= {min_cell_bbox_coverage}, got {ratio:.3f}"
            )

    expected_cols = spec.get("expected_col_count")
    if expected_cols is not None:
        ok = all(len(grid.get("col_bands") or []) == int(expected_cols) for grid in grids)
        report.checks["scanned_micro_grid_expected_col_count"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"expected every micro grid to have {expected_cols} columns")

    if spec.get("require_source_cell_refs"):
        ok = all(record.get("source_cell_refs") for record in records)
        report.checks["scanned_micro_grid_source_refs"] = ok
        if not ok:
            report.passed = False
            report.failures.append("expected every repayment record to carry source_cell_refs")

    expected = spec.get("expected_records") or []
    if expected:
        projected = [
            {
                "year": rec.get("year"),
                "month": rec.get("month"),
                "status": rec.get("status"),
                "overdue_amount": rec.get("overdue_amount"),
            }
            for rec in records
        ]
        ok = projected == expected
        report.checks["scanned_micro_grid_expected_records"] = ok
        report.metrics["repayment_record_count"] = len(records)
        if not ok:
            report.passed = False
            report.failures.append(f"repayment records mismatch: expected {expected}, got {projected}")

    if spec.get("forbid_repayment_records"):
        ok = not records
        report.checks["scanned_micro_grid_forbid_repayment_records"] = ok
        report.metrics["repayment_record_count"] = len(records)
        if not ok:
            report.passed = False
            report.failures.append(f"expected no repayment records, got {records}")

    return report
