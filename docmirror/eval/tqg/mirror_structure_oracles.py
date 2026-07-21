# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror structure oracles — SPE / SSO regression (Phase 5 / ADR-M13-02)."""

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.report import GateReport


def run_mirror_structure_oracle(
    meta: dict[str, Any],
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "",
) -> GateReport:
    """Validate ``parser_info.structure`` / metadata SPE fields."""
    report = GateReport(case_id=case_id, track=track, tier=tier)
    result = meta.get("result") or meta.get("parse_result")
    if result is None:
        report.passed = False
        report.failures.append("mirror_structure: missing ParseResult")
        return report

    info = getattr(result, "parser_info", None)
    structure = getattr(info, "structure", None) if info else None
    if not isinstance(structure, dict):
        structure = meta.get("structure") if isinstance(meta.get("structure"), dict) else None
    if not isinstance(structure, dict):
        report.passed = False
        report.failures.append("mirror_structure: metadata.structure missing")
        return report

    report.metrics["structure_primary"] = structure.get("primary")
    report.metrics["H_pipe_grid"] = (structure.get("competitors") or {}).get("H_pipe_grid")

    expected_primary = spec.get("primary")
    if expected_primary:
        ok = structure.get("primary") == expected_primary
        report.checks["primary"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"structure.primary expected {expected_primary!r}, got {structure.get('primary')!r}")

    min_pipe = spec.get("min_H_pipe_grid")
    if min_pipe is not None:
        h_pipe = float((structure.get("competitors") or {}).get("H_pipe_grid") or 0)
        ok = h_pipe >= float(min_pipe)
        report.checks["min_H_pipe_grid"] = ok
        report.metrics["H_pipe_grid"] = h_pipe
        if not ok:
            report.passed = False
            report.failures.append(f"H_pipe_grid {h_pipe} < {min_pipe}")

    forbidden_skip = spec.get("forbidden_skip_reasons") or []
    reason = structure.get("table_extraction_skipped_reason")
    for code in forbidden_skip:
        ok = reason != code
        report.checks[f"not_{code}"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"table_extraction_skipped_reason must not be {code!r}")

    require_reason_when_empty = spec.get("require_skip_reason_when_tables_empty")
    if require_reason_when_empty:
        table_count = int(meta.get("table_count") or 0)
        if table_count == 0 and structure.get("table_extraction") != "enrich_only":
            ok = bool(reason)
            report.checks["skip_reason_present"] = ok
            if not ok:
                report.passed = False
                report.failures.append("tables empty but table_extraction_skipped_reason missing")

    expected_extraction = spec.get("table_extraction")
    if expected_extraction:
        ok = structure.get("table_extraction") == expected_extraction
        report.checks["table_extraction"] = ok
        if not ok:
            report.passed = False
            report.failures.append(
                f"table_extraction expected {expected_extraction!r}, got {structure.get('table_extraction')!r}"
            )

    min_physical = spec.get("min_physical_table_count")
    if min_physical is not None:
        actual = int(structure.get("physical_table_count") or meta.get("table_count") or 0)
        ok = actual >= int(min_physical)
        report.checks["min_physical_table_count"] = ok
        report.metrics["physical_table_count"] = actual
        if not ok:
            report.passed = False
            report.failures.append(f"physical_table_count {actual} < {min_physical}")

    ltqg_spec = spec.get("ltqg")
    if isinstance(ltqg_spec, dict):
        require_enabled = ltqg_spec.get("require_enabled")
        if require_enabled:
            ok = bool(structure.get("ltqg_enabled"))
            report.checks["ltqg_enabled"] = ok
            if not ok:
                report.passed = False
                report.failures.append("ltqg_enabled expected True")

        min_expected = ltqg_spec.get("min_expected_data_rows")
        if min_expected is not None:
            expected_rows = int(structure.get("ltqg_expected_data_rows") or 0)
            ok = expected_rows >= int(min_expected)
            report.checks["min_ltqg_expected_data_rows"] = ok
            report.metrics["ltqg_expected_data_rows"] = expected_rows
            if not ok:
                report.passed = False
                report.failures.append(f"ltqg_expected_data_rows {expected_rows} < {min_expected}")

        min_skipped = ltqg_spec.get("min_skipped_tables")
        if min_skipped is not None:
            skipped = int(structure.get("ltqg_skipped_tables") or 0)
            ok = skipped >= int(min_skipped)
            report.checks["min_ltqg_skipped_tables"] = ok
            report.metrics["ltqg_skipped_tables"] = skipped
            if not ok:
                report.passed = False
                report.failures.append(f"ltqg_skipped_tables {skipped} < {min_skipped}")

        require_expected_below_raw = ltqg_spec.get("require_expected_below_raw")
        if require_expected_below_raw:
            expected_rows = int(structure.get("ltqg_expected_data_rows") or 0)
            raw_max = int(structure.get("ltqg_raw_max_rows") or 0)
            ok = raw_max > 0 and expected_rows < raw_max
            report.checks["ltqg_expected_below_raw"] = ok
            report.metrics["ltqg_raw_max_rows"] = raw_max
            if not ok:
                report.passed = False
                report.failures.append(f"ltqg expected {expected_rows} not below raw_max {raw_max}")

        min_export = ltqg_spec.get("min_export_logical_tables")
        if min_export is not None:
            export_count = int(structure.get("ltqg_export_logical_tables") or structure.get("logical_table_count") or 0)
            ok = export_count >= int(min_export)
            report.checks["min_ltqg_export_logical_tables"] = ok
            report.metrics["ltqg_export_logical_tables"] = export_count
            if not ok:
                report.passed = False
                report.failures.append(f"ltqg_export_logical_tables {export_count} < {min_export}")

        max_export = ltqg_spec.get("max_export_logical_tables")
        if max_export is not None:
            export_count = int(structure.get("ltqg_export_logical_tables") or structure.get("logical_table_count") or 0)
            ok = export_count <= int(max_export)
            report.checks["max_ltqg_export_logical_tables"] = ok
            report.metrics["ltqg_export_logical_tables"] = export_count
            if not ok:
                report.passed = False
                report.failures.append(f"ltqg_export_logical_tables {export_count} > {max_export}")

    return report
